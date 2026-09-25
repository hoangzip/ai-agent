"""
collector/writers/post_writer.py — Consumer worker for post_queue.

Persists discovered posts and actors to storage (file-based JSON).
"""
from __future__ import annotations

import logging
from typing import Optional

from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import PostDiscoveredItem
from collector.pipeline.worker import BaseWorker
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, PostRepo

logger = logging.getLogger(__name__)


class PostWriterWorker(BaseWorker):
    """Worker that consumes PostDiscoveredItem from post_queue and writes to storage."""

    def __init__(
        self,
        name: str,
        queue,
        counters: MetricsCounters,
        layout: StorageLayout,
        group_slug: str,
        group_id: Optional[str] = None,
        media_queue=None,
        comment_job_queue=None,
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
        self.group_id = group_id
        self.media_queue = media_queue
        self.comment_job_queue = comment_job_queue
        self.post_repo = PostRepo(layout, group_slug)
        self.actor_repo = ActorRepo(layout, group_slug)

    async def process_item(self, item: PostDiscoveredItem) -> None:
        """Upsert author and post to storage."""
        if not isinstance(item, PostDiscoveredItem):
            logger.warning("PostWriterWorker received unknown item type: %s", type(item))
            return

        actor_internal_id = None
        # 1. Upsert Actor if available
        if item.author_display_name or item.author_profile_url or item.author_facebook_user_id or item.author_is_anonymous:
            actor_record, _ = await self.actor_repo.upsert({
                "facebook_user_id": item.author_facebook_user_id,
                "profile_url": item.author_profile_url,
                "display_name": item.author_display_name,
                "is_anonymous": item.author_is_anonymous,
                "anonymous_scope_post_id": item.facebook_post_id or item.post_url,
            })
            actor_internal_id = actor_record["id"]

        # 2. Upsert Post
        from collector.pipeline.revisit import compute_next_check_at, CrawlStatus
        next_check = compute_next_check_at(item.posted_at)

        from collector.metrics.timer import time_block_async
        async with time_block_async("storage.flush_posts"):
            post_record, is_new = await self.post_repo.upsert({
                "group_slug": self.group_slug,
                "group_id": self.group_id,
                "facebook_post_id": item.facebook_post_id,
                "post_url": item.post_url,
                "author_id": actor_internal_id,
                "author_display_name": item.author_display_name,
                "author_is_anonymous": item.author_is_anonymous,
                "title": item.title,
                "title_source": item.title_source,
                "content": item.content_preview,
                "posted_at": item.posted_at.isoformat() if item.posted_at else None,
                "source_comment_count": item.source_comment_count,
                "crawl_status": CrawlStatus.DISCOVERED,
                "next_check_at": next_check.isoformat(),
            })

        if is_new:
            self._counters.posts_new += 1
            logger.info("Persisted NEW post: fb_id=%s url=%s", item.facebook_post_id, item.post_url)
        else:
            self._counters.posts_skipped += 1
            logger.debug("Updated existing post: fb_id=%s", item.facebook_post_id)

        # 3. Queue media download jobs
        if self.media_queue and item.media_urls_preview:
            from collector.pipeline.items import MediaJobItem
            for pos, url in enumerate(item.media_urls_preview):
                await self.media_queue.put(MediaJobItem(
                    owner_type="post",
                    owner_id=post_record["id"],
                    post_id=post_record["id"],
                    source_url=url,
                    position=pos,
                    media_type="image",
                ))
                self._counters.media_discovered += 1

        # 4. Queue comment extraction job
        if self.comment_job_queue is not None:
            await self.comment_job_queue.put(item)
