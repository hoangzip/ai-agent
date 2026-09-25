"""
tests/unit/test_dedupe.py — Tests for DedupeManager and complete multi-tier idempotency.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.config import MediaConfig
from collector.downloaders.media_downloader import DownloadResult
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.dedupe import DedupeManager
from collector.pipeline.items import CommentItem, MediaJobItem, PostDiscoveredItem
from collector.storage.layout import StorageLayout
from collector.storage.repository import CommentRepo, MediaRepo, PostRepo
from collector.workers.media_worker import MediaWorker
from collector.writers.comment_writer import CommentWriterWorker
from collector.writers.post_writer import PostWriterWorker


@pytest.mark.asyncio
async def test_dedupe_manager_post_memory_and_storage(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "tech_group"
    layout.ensure_dirs(group_slug)

    mgr = DedupeManager(layout, group_slug)

    # 1. Unknown post
    assert not await mgr.is_post_known(facebook_post_id="p101")
    assert not await mgr.is_post_known(post_url="https://fb.com/posts/p101")

    # 2. Mark seen in-memory
    mgr.mark_post_seen(facebook_post_id="p101", post_url="https://fb.com/posts/p101")
    assert await mgr.is_post_known(facebook_post_id="p101")
    assert await mgr.is_post_known(post_url="https://fb.com/posts/p101")

    # 3. Storage fallback and promotion for a new manager instance
    post_repo = PostRepo(layout, group_slug)
    await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "p202",
        "post_url": "https://fb.com/posts/p202",
    })

    fresh_mgr = DedupeManager(layout, group_slug)
    # Cache is empty initially
    assert "p202" not in fresh_mgr._seen_post_ids

    # Storage check finds it and promotes to in-memory
    assert await fresh_mgr.is_post_known(facebook_post_id="p202")
    assert "p202" in fresh_mgr._seen_post_ids


@pytest.mark.asyncio
async def test_dedupe_manager_warm_up(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "warm_group"
    layout.ensure_dirs(group_slug)

    # Pre-populate posts in storage
    post_repo = PostRepo(layout, group_slug)
    await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "post_a",
        "post_url": "https://fb.com/posts/a",
    })
    await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "post_b",
        "post_url": "https://fb.com/posts/b",
    })

    # Pre-populate media SHA
    media_repo = MediaRepo(layout)
    pending, _ = await media_repo.upsert_by_url({"source_url": "https://cdn.fb.com/img1.jpg"})
    await media_repo.mark_downloaded(
        media_id=pending["id"],
        sha256="sha256_mock_hash_12345",
        storage_uri="media/assets/sh/a2/sha256_mock_hash_12345.jpg",
    )

    mgr = DedupeManager(layout, group_slug)
    await mgr.warm_up()

    # In-memory sets are populated
    assert "post_a" in mgr._seen_post_ids
    assert "post_b" in mgr._seen_post_ids
    assert "sha256_mock_hash_12345" in mgr._seen_media_sha256

    # Instant check without disk queries
    assert await mgr.is_post_known("post_a")
    assert await mgr.is_media_sha_known("sha256_mock_hash_12345")


@pytest.mark.asyncio
async def test_end_to_end_re_run_idempotency_zero_new_items(tmp_path: Path):
    """
    PASS CRITERIA FOR PHASE 08:
    Re-running same items results in:
      0 new posts
      0 new comments
      0 new media (media_deduped increments)
    """
    layout = StorageLayout(str(tmp_path))
    group_slug = "re_run_test_group"
    layout.ensure_dirs(group_slug)

    post_q = asyncio.Queue()
    comment_q = asyncio.Queue()
    media_q = asyncio.Queue()
    counters = MetricsCounters()

    # --- Workers ---
    post_writer = PostWriterWorker(
        name="post-writer",
        queue=post_q,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
        media_queue=media_q,
    )
    comment_writer = CommentWriterWorker(
        name="comment-writer",
        queue=comment_q,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
    )

    # Mock downloader
    raw_img = b"identical image bytes"
    img_sha = hashlib.sha256(raw_img).hexdigest()
    mock_downloader = AsyncMock()
    mock_downloader.download = AsyncMock(return_value=DownloadResult(
        content=raw_img,
        sha256=img_sha,
        file_size=len(raw_img),
        mime_type="image/jpeg",
        ext="jpg",
    ))

    media_worker = MediaWorker(
        name="media-worker",
        queue=media_q,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
        config=MediaConfig(),
        downloader=mock_downloader,
    )

    # Sample items
    sample_post = PostDiscoveredItem(
        discovery_run_id="run-1",
        discovered_at=datetime.now(timezone.utc),
        facebook_post_id="fb_post_001",
        post_url="https://facebook.com/groups/re_run_test_group/posts/001/",
        title="Post 1",
        content_preview="Hello world",
        media_urls_preview=["https://cdn.fb.com/image1.jpg"],
    )

    # === RUN 1: First Insertion ===
    await post_writer.process_item(sample_post)
    assert counters.posts_new == 1
    assert counters.posts_skipped == 0
    assert counters.media_discovered == 1

    # Get post internal UUID
    post_repo = PostRepo(layout, group_slug)
    post_rec = await post_repo.get_by_facebook_id("fb_post_001")
    post_id = post_rec["id"]

    sample_comment = CommentItem(
        post_internal_id=post_id,
        facebook_comment_id="comment_001",
        content="First comment",
        depth=0,
    )
    await comment_writer.process_item(sample_comment)
    assert counters.comments_new == 1
    assert counters.comments_skipped == 0

    media_job = await media_q.get()
    await media_worker.process_item(media_job)
    assert counters.media_downloaded == 1
    assert counters.media_deduped == 0

    # === RUN 2: Re-run with identical items ===
    # Reset counters for run 2
    counters_run2 = MetricsCounters()
    post_writer._counters = counters_run2
    comment_writer._counters = counters_run2
    media_worker._counters = counters_run2

    # Process same post
    await post_writer.process_item(sample_post)
    # Process same comment
    await comment_writer.process_item(sample_comment)
    # Process same media job
    await media_worker.process_item(media_job)

    # VERIFY PASS CRITERIA:
    # 0 new posts, 0 new comments
    assert counters_run2.posts_new == 0
    assert counters_run2.posts_skipped == 1

    assert counters_run2.comments_new == 0
    assert counters_run2.comments_skipped == 1

    assert counters_run2.media_downloaded == 0
    assert counters_run2.media_deduped == 1
