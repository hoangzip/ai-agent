"""
tests/unit/test_post_writer.py — Tests for PostWriterWorker.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest

from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import PostDiscoveredItem, SENTINEL
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, PostRepo
from collector.writers.post_writer import PostWriterWorker


@pytest.mark.asyncio
async def test_post_writer_persists_item(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    queue = asyncio.Queue()
    counters = MetricsCounters()

    worker = PostWriterWorker(
        name="test-writer",
        queue=queue,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
    )

    item = PostDiscoveredItem(
        discovery_run_id="run-1",
        discovered_at=datetime.now(timezone.utc),
        facebook_post_id="post_999",
        post_url="https://www.facebook.com/groups/test_group/posts/post_999/",
        author_display_name="Test Author",
        author_profile_url="https://www.facebook.com/profile.php?id=888",
        author_facebook_user_id="888",
        title="Sample Title",
        content_preview="Sample Content",
    )

    # Process item
    await worker.process_item(item)

    assert counters.posts_new == 1

    # Verify post exists in PostRepo
    post_repo = PostRepo(layout, group_slug)
    assert await post_repo.exists("post_999")

    # Verify actor exists in ActorRepo
    actor_repo = ActorRepo(layout, group_slug)
    actor_id = await actor_repo.get_by_fb_id("888")
    assert actor_id is not None
