"""
collector/workers/comment_worker.py — Independent Comment Worker.

Consumes PostDiscoveredItem from post_queue, navigates to post permalink
in an independent browser page, extracts full or delta comments tree,
and pushes CommentItem instances into comment_queue.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from playwright.async_api import BrowserContext

from collector.config import CrawlerConfig
from collector.facebook.comments import CommentExtractor
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import PostDiscoveredItem
from collector.pipeline.worker import BaseWorker
from collector.storage.layout import StorageLayout
from collector.storage.repository import CommentRepo, PostRepo

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommentWorker(BaseWorker):
    """
    Worker that consumes posts from post_queue, extracts comment/reply trees,
    and publishes CommentItem to comment_queue.
    """

    def __init__(
        self,
        name: str,
        queue: asyncio.Queue,
        comment_queue: asyncio.Queue,
        counters: MetricsCounters,
        context: BrowserContext,
        layout: StorageLayout,
        group_slug: str,
        config: CrawlerConfig,
        media_queue: Optional[asyncio.Queue] = None,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            queue=queue,
            counters=counters,
            max_retries=max_retries,
        )
        self.comment_queue = comment_queue
        self.media_queue = media_queue
        self.context = context
        self.layout = layout
        self.group_slug = group_slug
        self.config = config
        self.post_repo = PostRepo(layout, group_slug)
        self._page = None

    async def _get_or_create_page(self):
        """Get existing open page or create a new one with optional resource blocking."""
        if self._page is None or (hasattr(self._page, "is_closed") and self._page.is_closed()):
            self._page = await self.context.new_page()
            if getattr(self.config.browser, "block_resources", False):
                async def _block_route(route):
                    if route.request.resource_type in ("image", "media", "font"):
                        await route.abort()
                    else:
                        await route.continue_()
                await self._page.route("**/*", _block_route)
        return self._page

    def stop(self) -> None:
        super().stop()
        if self._page and hasattr(self._page, "is_closed") and not self._page.is_closed():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._page.close())
            except Exception:
                pass

    async def process_item(self, item: PostDiscoveredItem) -> None:
        """Process a single post item: decide action, open page, extract comments."""
        if not isinstance(item, PostDiscoveredItem):
            logger.warning("%s received unexpected item: %s", self.name, type(item))
            return

        # 1. Action decision: SKIP
        if item.action == "SKIP":
            logger.debug("%s skipping post %s per action=SKIP", self.name, item.facebook_post_id)
            self._counters.posts_skipped += 1
            return

        if not item.post_url:
            logger.debug("%s post has no URL — cannot crawl comments", self.name)
            return

        # 2. Resolve post internal ID from storage
        post_record = None
        if item.facebook_post_id:
            post_record = await self.post_repo.get_by_facebook_id(item.facebook_post_id)
        if not post_record and item.post_url:
            post_record = await self.post_repo.get_by_url(item.post_url)

        if not post_record:
            # If PostWriterWorker hasn't persisted it yet, upsert it now
            post_record, _ = await self.post_repo.upsert({
                "group_slug": self.group_slug,
                "facebook_post_id": item.facebook_post_id,
                "post_url": item.post_url,
                "title": item.title,
                "content": item.content_preview,
                "source_comment_count": item.source_comment_count,
                "crawl_status": "PROCESSING_COMMENTS",
            })

        post_id = post_record["id"]
        comment_repo = CommentRepo(self.layout, post_id)

        # 3. Delta extraction callback if REFRESH_COMMENTS
        is_known_fn = None
        if item.action == "REFRESH_COMMENTS":
            async def _check_comment_known(cid: str) -> bool:
                idx = await comment_repo.read_index() if hasattr(comment_repo, "read_index") else {}
                return f"fb_cid:{cid}" in idx
            is_known_fn = _check_comment_known

        # 4. Open independent page and extract comments
        from collector.pipeline.revisit import compute_next_check_at, CrawlStatus
        await self.post_repo.update_status(post_id, CrawlStatus.CRAWLING)

        logger.info("%s opening post URL: %s (action=%s)", self.name, item.post_url, item.action)
        page = None
        try:
            from collector.metrics.timer import time_block_async
            page = await self._get_or_create_page()
            async with time_block_async("browser.post_page_open"):
                await page.goto(item.post_url, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

            extractor = CommentExtractor(page)
            async with time_block_async("browser.comment_extraction"):
                comments = await extractor.extract_comments_tree(
                    post_internal_id=post_id,
                    is_known_comment_fn=is_known_fn,
                )

            # 4b. Extract media from post detail page if media_queue provided
            if self.media_queue:
                try:
                    from collector.facebook.media import MediaDetector
                    from collector.pipeline.items import MediaJobItem
                    post_media = await MediaDetector.extract_post_media(page)
                    for pos, m in enumerate(post_media):
                        await self.media_queue.put(MediaJobItem(
                            owner_type="post",
                            owner_id=post_id,
                            post_id=post_id,
                            source_url=m["source_url"],
                            position=pos,
                            media_type=m.get("media_type", "image"),
                        ))
                        self._counters.media_discovered += 1
                except Exception as e:
                    logger.debug("%s failed extracting post media: %s", self.name, e)

            # 5. Push to comment_queue
            for comment in comments:
                await self.comment_queue.put(comment)
                self._counters.comments_discovered += 1

            # 6. Update post completion status and revisit schedule
            revisit_cfg = getattr(self.config, "revisit", None)
            next_check = compute_next_check_at(item.posted_at, config=revisit_cfg)

            await self.post_repo.update(post_id, {
                "crawl_status": CrawlStatus.COMPLETE,
                "last_comments_crawled_at": _now(),
                "comments_complete": True,
                "next_check_at": next_check.isoformat(),
            })

            logger.info(
                "%s successfully extracted %d comments for post %s",
                self.name, len(comments), item.facebook_post_id,
            )

        except Exception as e:
            logger.error("%s failed crawling comments for post %s: %s", self.name, item.post_url, e)
            self._counters.partial_posts += 1
            await self.post_repo.update_status(post_id, CrawlStatus.PARTIAL)
            if self._page and hasattr(self._page, "is_closed") and not self._page.is_closed():
                try:
                    await self._page.close()
                except Exception:
                    pass
                self._page = None
            raise
