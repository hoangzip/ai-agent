"""
tests/unit/test_incremental_and_revisit.py — Unit tests for Phase 10: Incremental Crawl & Revisit Policy.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from collector.config import CrawlerConfig, IncrementalConfig, RevisitConfig
from collector.facebook.comments import CommentExtractor
from collector.facebook.feed import FeedProducer
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.backpressure import ProducerGate
from collector.pipeline.items import CommentItem, PostDiscoveredItem, SENTINEL
from collector.pipeline.revisit import (
    compute_next_check_at,
    is_refresh_due,
    CrawlStatus,
)
from collector.storage.layout import StorageLayout
from collector.storage.repository import CommentRepo, PostRepo
from collector.writers.comment_writer import CommentWriterWorker


def test_revisit_schedule_buckets():
    """Verify revisit intervals match policy across all age buckets."""
    cfg = RevisitConfig(
        interval_under_1d_hours=1,
        interval_1_to_3d_hours=6,
        interval_3_to_7d_hours=12,
        interval_7_to_30d_hours=24,
        interval_30_to_90d_hours=72,
        interval_over_90d_days=7,
    )
    ref = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    # 1. < 1 day old (3 hours ago) -> +1h
    p1 = ref - timedelta(hours=3)
    nxt1 = compute_next_check_at(p1, cfg, reference_time=ref)
    assert nxt1 == ref + timedelta(hours=1)

    # 2. 1 to 3 days old (2 days ago) -> +6h
    p2 = ref - timedelta(days=2)
    nxt2 = compute_next_check_at(p2, cfg, reference_time=ref)
    assert nxt2 == ref + timedelta(hours=6)

    # 3. 3 to 7 days old (5 days ago) -> +12h
    p3 = ref - timedelta(days=5)
    nxt3 = compute_next_check_at(p3, cfg, reference_time=ref)
    assert nxt3 == ref + timedelta(hours=12)

    # 4. 7 to 30 days old (20 days ago) -> +24h
    p4 = ref - timedelta(days=20)
    nxt4 = compute_next_check_at(p4, cfg, reference_time=ref)
    assert nxt4 == ref + timedelta(hours=24)

    # 5. 30 to 90 days old (60 days ago) -> +72h
    p5 = ref - timedelta(days=60)
    nxt5 = compute_next_check_at(p5, cfg, reference_time=ref)
    assert nxt5 == ref + timedelta(hours=72)

    # 6. > 90 days old (120 days ago) -> +7 days
    p6 = ref - timedelta(days=120)
    nxt6 = compute_next_check_at(p6, cfg, reference_time=ref)
    assert nxt6 == ref + timedelta(days=7)


def test_is_refresh_due():
    """Verify refresh due detection for posts."""
    ref = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    # Explicit REFRESH_DUE status
    assert is_refresh_due({"crawl_status": CrawlStatus.REFRESH_DUE}, reference_time=ref)

    # Overdue next_check_at
    overdue = (ref - timedelta(minutes=5)).isoformat()
    assert is_refresh_due({"crawl_status": CrawlStatus.COMPLETE, "next_check_at": overdue}, reference_time=ref)

    # Future next_check_at
    future = (ref + timedelta(hours=2)).isoformat()
    assert not is_refresh_due({"crawl_status": CrawlStatus.COMPLETE, "next_check_at": future}, reference_time=ref)

    # Missing next_check_at
    assert not is_refresh_due({"crawl_status": CrawlStatus.COMPLETE}, reference_time=ref)


def test_crawl_status_state_machine():
    """Verify state machine valid and invalid transitions."""
    # Valid transitions
    assert CrawlStatus.can_transition(CrawlStatus.DISCOVERED, CrawlStatus.CRAWLING)
    assert CrawlStatus.can_transition(CrawlStatus.CRAWLING, CrawlStatus.COMPLETE)
    assert CrawlStatus.can_transition(CrawlStatus.CRAWLING, CrawlStatus.PARTIAL)
    assert CrawlStatus.can_transition(CrawlStatus.COMPLETE, CrawlStatus.REFRESH_DUE)
    assert CrawlStatus.can_transition(CrawlStatus.REFRESH_DUE, CrawlStatus.CRAWLING)

    # Invalid transitions
    assert not CrawlStatus.can_transition(CrawlStatus.DISCOVERED, CrawlStatus.COMPLETE)
    assert not CrawlStatus.can_transition(CrawlStatus.COMPLETE, CrawlStatus.DISCOVERED)

    with pytest.raises(ValueError):
        CrawlStatus.validate_transition(CrawlStatus.DISCOVERED, CrawlStatus.COMPLETE)


@pytest.mark.asyncio
async def test_incremental_mode_stop_condition():
    """Verify feed producer stops after consecutive known posts threshold and resets on new content."""
    config = CrawlerConfig(
        mode="incremental",
        incremental=IncrementalConfig(stop_after_consecutive_known_posts=3),
    )

    known_db = {"p1", "p2", "p3", "p5", "p6", "p7"}

    async def is_known(pid: str) -> bool:
        return pid in known_db

    post_queue = asyncio.Queue()
    counters = MetricsCounters()
    gate = ProducerGate()

    class MockCard:
        def __init__(self, pid: str):
            self.pid = pid

    class MockPage:
        url = "https://www.facebook.com/groups/test"

        async def query_selector_all(self, sel):
            return []

        async def evaluate(self, script):
            pass

    feed_producer = FeedProducer(
        page=MockPage(),
        config=config,
        post_queue=post_queue,
        producer_gate=gate,
        counters=counters,
        run_id="run-inc",
        is_known_post_fn=is_known,
    )

    # Feed sequence:
    # 1. p1 (known) -> consecutive = 1
    # 2. p2 (known) -> consecutive = 2
    # 3. p_new (new!) -> consecutive resets to 0!
    # 4. p5 (known) -> consecutive = 1
    # 5. p6 (known) -> consecutive = 2
    # 6. p7 (known) -> consecutive = 3 -> STOP!
    # 7. p8 (should never be processed)

    items_sequence = [
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p1"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p2"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p_new"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p5"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p6"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p7"),
        PostDiscoveredItem("run-inc", datetime.now(timezone.utc), facebook_post_id="p8"),
    ]

    feed_producer._extract_visible_cards = lambda: asyncio.sleep(0, result=items_sequence)
    feed_producer._scroll_down = lambda: asyncio.sleep(0)

    shutdown_event = asyncio.Event()
    discovered = await feed_producer.run("https://www.facebook.com/groups/test", shutdown_event)

    # Stopped at p7! Discovered exactly 6 posts (p1, p2, p_new, p5, p6, p7)
    assert discovered == 6
    assert feed_producer._consecutive_known == 3


@pytest.mark.asyncio
async def test_delta_comment_extraction_and_writer(tmp_path: Path):
    """
    Verify REFRESH_COMMENTS / Delta comments extraction:
    - Initial comments: c1, c2, c3 saved
    - Refresh run: delta check stops after threshold known comments
    - Writer inserts only new comments and increments comment count accurately
    """
    layout = StorageLayout(root_dir=tmp_path / "data")
    group_slug = "delta-group"
    post_id = "post-delta-1"

    post_repo = PostRepo(layout, group_slug)
    post_rec, _ = await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "fb-p1",
        "post_url": "https://fb.com/p1",
        "title": "Delta Post",
    })
    post_id = post_rec["id"]

    comment_repo = CommentRepo(layout, post_id)
    comment_queue = asyncio.Queue()
    counters = MetricsCounters()

    writer = CommentWriterWorker(
        name="comment-writer",
        queue=comment_queue,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
    )
    task_w = asyncio.create_task(writer.run())

    now = datetime.now(timezone.utc)

    # Initial crawl: c1, c2, c3
    for cid in ["c1", "c2", "c3"]:
        await comment_queue.put(CommentItem(
            post_internal_id=post_id,
            facebook_comment_id=cid,
            content=f"Comment {cid}",
            commented_at=now,
        ))

    await comment_queue.put(SENTINEL)
    await task_w

    assert counters.comments_new == 3
    post_rec = await post_repo.get(post_id)
    assert post_rec["known_comment_count"] == 3

    # Now simulate Refresh: new comment c4 appears on top, followed by known c1, c2
    # Known callback:
    known_cids = {"c1", "c2", "c3"}
    consecutive_known = 0
    extracted = []

    comments_on_page = [
        CommentItem(post_internal_id=post_id, facebook_comment_id="c4", content="New c4"),
        CommentItem(post_internal_id=post_id, facebook_comment_id="c1", content="Comment c1"),
        CommentItem(post_internal_id=post_id, facebook_comment_id="c2", content="Comment c2"),
        CommentItem(post_internal_id=post_id, facebook_comment_id="c0_old", content="Old c0"),
    ]

    threshold = 2
    for c in comments_on_page:
        extracted.append(c)
        if c.facebook_comment_id in known_cids:
            consecutive_known += 1
            if consecutive_known >= threshold:
                break
        else:
            consecutive_known = 0

    # Delta stopped at c2, before reaching c0_old
    assert len(extracted) == 3
    assert [c.facebook_comment_id for c in extracted] == ["c4", "c1", "c2"]

    # Write refresh comments
    comment_queue_2 = asyncio.Queue()
    writer_2 = CommentWriterWorker(
        name="comment-writer-2",
        queue=comment_queue_2,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
    )
    task_w2 = asyncio.create_task(writer_2.run())

    for c in extracted:
        await comment_queue_2.put(c)

    await comment_queue_2.put(SENTINEL)
    await task_w2

    # Exactly 1 new comment (c4), 2 skipped
    assert counters.comments_new == 4  # 3 + 1
    assert counters.comments_skipped == 2
    post_rec2 = await post_repo.get(post_id)
    assert post_rec2["known_comment_count"] == 4
