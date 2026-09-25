"""
tests/unit/test_comment_writer.py — Tests for CommentWriterWorker.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest

from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import CommentItem
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, CommentRepo, PostRepo
from collector.writers.comment_writer import CommentWriterWorker


@pytest.mark.asyncio
async def test_comment_writer_persists_comment_and_increments_count(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    # First create a post
    post_repo = PostRepo(layout, group_slug)
    post_rec, _ = await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "p100",
        "post_url": "https://facebook.com/groups/test_group/posts/p100/",
    })
    post_id = post_rec["id"]

    queue = asyncio.Queue()
    counters = MetricsCounters()

    worker = CommentWriterWorker(
        name="test-comment-writer",
        queue=queue,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
    )

    comment = CommentItem(
        post_internal_id=post_id,
        facebook_comment_id="c999",
        author_display_name="Commenter A",
        author_profile_url="https://facebook.com/profile.php?id=user999",
        author_facebook_user_id="user999",
        content="Great discussion here!",
        depth=0,
    )

    # Process item
    await worker.process_item(comment)

    assert counters.comments_new == 1

    # Verify comment stored
    comment_repo = CommentRepo(layout, post_id)
    assert await comment_repo.exists("c999")

    # Verify post known_comment_count incremented
    updated_post = await post_repo.get(post_id)
    assert updated_post["known_comment_count"] == 1

    # Verify actor created
    actor_repo = ActorRepo(layout, group_slug)
    actor_id = await actor_repo.get_by_fb_id("user999")
    assert actor_id is not None

    # Idempotent second write
    await worker.process_item(comment)
    assert counters.comments_skipped == 1
    assert counters.comments_new == 1
