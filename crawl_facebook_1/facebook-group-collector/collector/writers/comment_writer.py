"""
collector/writers/comment_writer.py — Consumer worker for comment_queue.

Persists extracted comments and comment authors to storage.
"""
from __future__ import annotations

import logging

from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import CommentItem
from collector.pipeline.worker import BaseWorker
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, CommentRepo, PostRepo

logger = logging.getLogger(__name__)


class CommentWriterWorker(BaseWorker):
    """Worker that consumes CommentItem from comment_queue and writes to storage."""

    def __init__(
        self,
        name: str,
        queue,
        counters: MetricsCounters,
        layout: StorageLayout,
        group_slug: str,
        media_queue=None,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            queue=queue,
            counters=counters,
            max_retries=max_retries,
        )
        self.layout = layout
        self.group_slug = group_slug
        self.media_queue = media_queue
        self.actor_repo = ActorRepo(layout, group_slug)
        self.post_repo = PostRepo(layout, group_slug)

    async def process_item(self, item: CommentItem) -> None:
        """Upsert author and comment into storage."""
        if not isinstance(item, CommentItem):
            logger.warning("CommentWriterWorker received unknown item type: %s", type(item))
            return

        actor_internal_id = None
        # 1. Upsert Actor if available
        if item.author_display_name or item.author_profile_url or item.author_facebook_user_id or item.author_is_anonymous:
            actor_record, _ = await self.actor_repo.upsert({
                "facebook_user_id": item.author_facebook_user_id,
                "profile_url": item.author_profile_url,
                "display_name": item.author_display_name,
                "is_anonymous": item.author_is_anonymous,
                "anonymous_scope_post_id": item.post_internal_id,
            })
            actor_internal_id = actor_record["id"]

        # 2. Upsert Comment
        comment_repo = CommentRepo(self.layout, item.post_internal_id)
        from collector.metrics.timer import time_block_async
        async with time_block_async("storage.flush_comments"):
            comment_record, is_new = await comment_repo.upsert({
                "facebook_comment_id": item.facebook_comment_id,
                "parent_comment_id": item.parent_comment_id,
                "parent_internal_id": item.parent_internal_id,
                "author_id": actor_internal_id,
                "author_display_name": item.author_display_name,
                "author_profile_url": item.author_profile_url,
                "author_is_anonymous": item.author_is_anonymous,
                "content": item.content,
                "commented_at": item.commented_at.isoformat() if item.commented_at else None,
                "depth": item.depth,
                "media_urls": item.media_urls,
            })

        if is_new:
            self._counters.comments_new += 1
            # Update post's known comment count
            await self.post_repo.increment_comment_count(item.post_internal_id, delta=1)
            logger.debug(
                "Persisted NEW comment: cid=%s post=%s depth=%d",
                item.facebook_comment_id, item.post_internal_id, item.depth,
            )
        else:
            self._counters.comments_skipped += 1
            logger.debug("Updated existing comment: cid=%s", item.facebook_comment_id)

        # 3. Queue comment media download jobs
        if self.media_queue and item.media_urls:
            from collector.pipeline.items import MediaJobItem
            for pos, url in enumerate(item.media_urls):
                await self.media_queue.put(MediaJobItem(
                    owner_type="comment",
                    owner_id=comment_record["id"],
                    post_id=item.post_internal_id,
                    source_url=url,
                    position=pos,
                    media_type="image",
                ))
                self._counters.media_discovered += 1
