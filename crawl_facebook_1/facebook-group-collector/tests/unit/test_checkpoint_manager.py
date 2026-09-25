"""
tests/unit/test_checkpoint_manager.py — Unit tests for CheckpointManager (Phase 09).
"""
import asyncio
from pathlib import Path
import pytest

from collector.checkpoints.checkpoint_manager import CheckpointManager
from collector.config import CheckpointConfig
from collector.metrics.emitter import MetricsCounters
from collector.storage.layout import StorageLayout
from collector.storage.repository import CheckpointRepo


@pytest.fixture
def tmp_layout(tmp_path: Path) -> StorageLayout:
    return StorageLayout(root_dir=tmp_path / "data")


@pytest.fixture
def checkpoint_repo(tmp_layout: StorageLayout) -> CheckpointRepo:
    return CheckpointRepo(tmp_layout)


@pytest.mark.asyncio
async def test_record_post_and_count_trigger(checkpoint_repo: CheckpointRepo):
    """Test checkpoint save triggers after every_posts threshold."""
    config = CheckpointConfig(every_posts=3, every_seconds=60)
    counters = MetricsCounters()

    mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="test-group",
        group_id="1001",
        mode="full",
        run_id="run-1",
        config=config,
        counters=counters,
    )

    # Post 1
    counters.posts_discovered = 1
    triggered = await mgr.record_post(post_id="post-1", post_time="2026-09-24T10:00:00Z")
    assert not triggered
    assert mgr.last_post_id == "post-1"

    # Post 2
    counters.posts_discovered = 2
    triggered = await mgr.record_post(post_id="post-2")
    assert not triggered

    # Post 3 (threshold reached: 3 - 0 >= 3)
    counters.posts_discovered = 3
    triggered = await mgr.record_post(post_id="post-3", consecutive_known=2)
    assert triggered
    assert mgr.last_post_id == "post-3"
    assert mgr.consecutive_known_posts == 2

    # Checkpoint was persisted
    loaded = await checkpoint_repo.load("test-group", "full")
    assert loaded is not None
    assert loaded["last_post_id"] == "post-3"
    assert loaded["consecutive_known_posts"] == 2
    assert loaded["progress_snapshot"]["posts_discovered"] == 3


@pytest.mark.asyncio
async def test_save_now_and_load(checkpoint_repo: CheckpointRepo):
    """Test explicit save_now and restoring counters on load."""
    config = CheckpointConfig(every_posts=20, every_seconds=15)
    counters = MetricsCounters()
    counters.posts_discovered = 42
    counters.posts_new = 40
    counters.posts_skipped = 2
    counters.comments_new = 15
    counters.media_downloaded = 8

    mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="tech-group",
        group_id="999",
        mode="incremental",
        run_id="run-abc",
        config=config,
        counters=counters,
    )
    mgr.last_post_id = "fb-post-42"
    mgr.consecutive_known_posts = 5

    saved = await mgr.save_now(status="in_progress")
    assert saved["run_id"] == "run-abc"
    assert saved["status"] == "in_progress"

    # Fresh manager restoring state
    new_counters = MetricsCounters()
    resumed_mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="tech-group",
        group_id="999",
        mode="incremental",
        run_id="run-new",
        config=config,
        counters=new_counters,
    )

    loaded = await resumed_mgr.load()
    assert loaded is not None
    assert resumed_mgr.last_post_id == "fb-post-42"
    assert resumed_mgr.consecutive_known_posts == 5
    assert new_counters.posts_discovered == 42
    assert new_counters.posts_new == 40
    assert new_counters.posts_skipped == 2
    assert new_counters.comments_new == 15
    assert new_counters.media_downloaded == 8


@pytest.mark.asyncio
async def test_clear_checkpoint(checkpoint_repo: CheckpointRepo):
    """Test clearing checkpoint file on successful completion."""
    config = CheckpointConfig()
    mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="clear-group",
        group_id="888",
        mode="full",
        run_id="run-clear",
        config=config,
    )

    await mgr.save_now()
    assert (await checkpoint_repo.load("clear-group", "full")) is not None

    await mgr.clear()
    assert (await checkpoint_repo.load("clear-group", "full")) is None


@pytest.mark.asyncio
async def test_background_periodic_saving(checkpoint_repo: CheckpointRepo):
    """Test background task periodically saves checkpoints."""
    config = CheckpointConfig(every_posts=100, every_seconds=0.1)  # 100ms interval
    counters = MetricsCounters()
    counters.posts_discovered = 10

    mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="periodic-group",
        group_id="777",
        mode="full",
        run_id="run-periodic",
        config=config,
        counters=counters,
    )

    task = asyncio.create_task(mgr.run())
    await asyncio.sleep(0.25)
    mgr.stop()
    await task

    loaded = await checkpoint_repo.load("periodic-group", "full")
    assert loaded is not None
    assert loaded["progress_snapshot"]["posts_discovered"] == 10


@pytest.mark.asyncio
async def test_fast_shutdown_save(checkpoint_repo: CheckpointRepo):
    """Test fast shutdown saves with 'interrupted' status."""
    config = CheckpointConfig()
    mgr = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug="shutdown-group",
        group_id="666",
        mode="full",
        run_id="run-sigterm",
        config=config,
    )
    mgr.last_post_id = "post-99"

    saved = await mgr.save_now(status="interrupted")
    assert saved["status"] == "interrupted"

    loaded = await checkpoint_repo.load("shutdown-group", "full")
    assert loaded["status"] == "interrupted"
    assert loaded["last_post_id"] == "post-99"


@pytest.mark.asyncio
async def test_resume_deduplication_flow(tmp_layout: StorageLayout, checkpoint_repo: CheckpointRepo):
    """
    Test resume flow:
    - Run 1 persists 5 posts and saves checkpoint, then stops
    - Run 2 resumes: loads checkpoint, dedupe engine marks existing posts as SKIP
    - New posts are processed as NEW; old posts skipped without duplicate count
    """
    from collector.pipeline.dedupe import DedupeManager
    from collector.pipeline.items import PostDiscoveredItem, SENTINEL
    from collector.writers.post_writer import PostWriterWorker

    group_slug = "resume-flow-group"
    group_id = "555"

    # --- Run 1 ---
    post_queue_1 = asyncio.Queue()
    counters_1 = MetricsCounters()
    writer_1 = PostWriterWorker(
        name="writer-1",
        queue=post_queue_1,
        counters=counters_1,
        layout=tmp_layout,
        group_slug=group_slug,
        group_id=group_id,
    )
    task_w1 = asyncio.create_task(writer_1.run())

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # Feed discovered 3 posts
    for i in range(1, 4):
        item = PostDiscoveredItem(
            discovery_run_id="run-1",
            discovered_at=now,
            facebook_post_id=f"post-{i}",
            post_url=f"https://fb.com/groups/555/posts/{i}",
            title=f"Post {i}",
        )
        counters_1.posts_discovered += 1
        await post_queue_1.put(item)

    await post_queue_1.put(SENTINEL)
    await task_w1

    assert counters_1.posts_new == 3

    # Run 1 writes checkpoint and exits
    mgr_1 = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug=group_slug,
        group_id=group_id,
        mode="full",
        run_id="run-1",
        config=CheckpointConfig(),
        counters=counters_1,
    )
    mgr_1.last_post_id = "post-3"
    await mgr_1.save_now(status="interrupted")

    # --- Run 2: Resume ---
    counters_2 = MetricsCounters()
    mgr_2 = CheckpointManager(
        checkpoint_repo=checkpoint_repo,
        group_slug=group_slug,
        group_id=group_id,
        mode="full",
        run_id="run-2",
        config=CheckpointConfig(),
        counters=counters_2,
    )
    cp = await mgr_2.load()
    assert cp is not None
    assert mgr_2.last_post_id == "post-3"
    # Note: snapshot restored posts_discovered=3, posts_new=3
    assert counters_2.posts_discovered == 3
    assert counters_2.posts_new == 3

    # DedupeManager warms up from storage
    dedupe_mgr = DedupeManager(tmp_layout, group_slug)
    await dedupe_mgr.warm_up()
    assert await dedupe_mgr.is_post_known("post-1")
    assert await dedupe_mgr.is_post_known("post-2")
    assert await dedupe_mgr.is_post_known("post-3")
    assert not await dedupe_mgr.is_post_known("post-4")

    # Run 2 writer
    post_queue_2 = asyncio.Queue()
    writer_2 = PostWriterWorker(
        name="writer-2",
        queue=post_queue_2,
        counters=counters_2,
        layout=tmp_layout,
        group_slug=group_slug,
        group_id=group_id,
    )
    task_w2 = asyncio.create_task(writer_2.run())

    # Feed rescans post 2 and 3, then discovers new post 4
    for pid in ["post-2", "post-3", "post-4"]:
        is_known = await dedupe_mgr.is_post_known(pid)
        item = PostDiscoveredItem(
            discovery_run_id="run-2",
            discovered_at=now,
            facebook_post_id=pid,
            post_url=f"https://fb.com/groups/555/posts/{pid}",
            title=f"Post {pid}",
            action="SKIP" if is_known else "FULL_CRAWL",
        )
        if not is_known:
            counters_2.posts_discovered += 1
        await post_queue_2.put(item)

    await post_queue_2.put(SENTINEL)
    await task_w2

    # Verify: exactly 1 new post (post-4) added, 2 skipped, total posts_new = 3 + 1 = 4
    assert counters_2.posts_new == 4
    assert counters_2.posts_skipped == 2
    assert counters_2.posts_discovered == 4

