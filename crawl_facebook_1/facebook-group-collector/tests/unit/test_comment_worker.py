"""
tests/unit/test_comment_worker.py — Tests for CommentWorker consuming posts and crawling comments.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from collector.config import CrawlerConfig
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import CommentItem, PostDiscoveredItem
from collector.storage.layout import StorageLayout
from collector.storage.repository import PostRepo
from collector.workers.comment_worker import CommentWorker


@pytest.mark.asyncio
async def test_comment_worker_skips_when_action_is_skip(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    post_q = asyncio.Queue()
    comment_q = asyncio.Queue()
    counters = MetricsCounters()
    mock_context = MagicMock()

    worker = CommentWorker(
        name="test-worker",
        queue=post_q,
        comment_queue=comment_q,
        counters=counters,
        context=mock_context,
        layout=layout,
        group_slug=group_slug,
        config=CrawlerConfig(),
    )

    item = PostDiscoveredItem(
        discovery_run_id="run-1",
        discovered_at=datetime.now(timezone.utc),
        facebook_post_id="post_skip",
        post_url="https://facebook.com/groups/1/posts/skip/",
        action="SKIP",
    )

    await worker.process_item(item)

    assert counters.posts_skipped == 1
    assert comment_q.empty()
    # Context should not open a page for skipped post
    mock_context.new_page.assert_not_called()


@pytest.mark.asyncio
async def test_comment_worker_extracts_and_pushes_comments(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    post_q = asyncio.Queue()
    comment_q = asyncio.Queue()
    counters = MetricsCounters()

    # Mock Page and BrowserContext
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    worker = CommentWorker(
        name="test-worker",
        queue=post_q,
        comment_queue=comment_q,
        counters=counters,
        context=mock_context,
        layout=layout,
        group_slug=group_slug,
        config=CrawlerConfig(),
    )

    item = PostDiscoveredItem(
        discovery_run_id="run-1",
        discovered_at=datetime.now(timezone.utc),
        facebook_post_id="post_live",
        post_url="https://facebook.com/groups/1/posts/live/",
        action="FULL_CRAWL",
    )

    sample_comments = [
        CommentItem(
            post_internal_id="dummy",
            facebook_comment_id="c1",
            content="Hello",
            depth=0,
        ),
        CommentItem(
            post_internal_id="dummy",
            facebook_comment_id="c2",
            content="Reply",
            depth=1,
            parent_comment_id="c1",
        ),
    ]

    with patch(
        "collector.workers.comment_worker.CommentExtractor.extract_comments_tree",
        new=AsyncMock(return_value=sample_comments),
    ):
        await worker.process_item(item)

    assert counters.comments_discovered == 2
    assert comment_q.qsize() == 2

    # Verify post status updated to COMPLETE per crawl_status state machine
    post_repo = PostRepo(layout, group_slug)
    post_record = await post_repo.get_by_facebook_id("post_live")
    assert post_record is not None
    assert post_record["crawl_status"] == "COMPLETE"
