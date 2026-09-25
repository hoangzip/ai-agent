"""
collector/facebook/feed.py — Browser Feed Producer.

Responsibilities:
- Scroll group feed progressively with randomized human-like jitter
- Extract post cards from feed DOM
- Normalize into PostDiscoveredItem via PostNormalizer
- Backpressure awareness: pauses when ProducerGate is closed
- Honors stop conditions:
  * limits.max_posts reached
  * consecutive known posts limit reached (incremental mode)
  * End of feed reached
  * Shutdown event signaled
- Pushes discovered posts to post_queue
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional, Set

from collector.config import CrawlerConfig
from collector.facebook.selectors import FeedSelectors
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.backpressure import ProducerGate
from collector.pipeline.items import PostDiscoveredItem
from collector.pipeline.normalizer import PostNormalizer

logger = logging.getLogger(__name__)


class FeedProducer:
    """
    Browser-based Feed Producer that scrolls Facebook group feed
    and publishes PostDiscoveredItem into the pipeline.
    """

    def __init__(
        self,
        page,
        config: CrawlerConfig,
        post_queue: asyncio.Queue,
        producer_gate: ProducerGate,
        counters: MetricsCounters,
        run_id: str,
        group_id: Optional[str] = None,
        is_known_post_fn=None,
        on_post_fn=None,
        initial_consecutive_known: int = 0,
    ):
        self.page = page
        self.config = config
        self.post_queue = post_queue
        self.producer_gate = producer_gate
        self.counters = counters
        self.run_id = run_id
        self.group_id = group_id
        # is_known_post_fn(post_id_or_url) -> bool (for incremental stop condition and dedupe)
        self.is_known_post_fn = is_known_post_fn or (lambda x: False)
        self.on_post_fn = on_post_fn

        self._seen_ids: Set[str] = set()
        self._consecutive_known: int = initial_consecutive_known
        self._total_discovered: int = 0

    async def run(self, group_url: str, shutdown_event: asyncio.Event) -> int:
        """
        Main producer loop.
        Navigates to group feed and continuously scrolls, extracts and queues posts.
        Returns total posts discovered.
        """
        logger.info("FeedProducer starting on %s (mode=%s)", group_url, self.config.mode)

        # Navigate to group if not already on the page
        if group_url not in self.page.url:
            await self.page.goto(group_url, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

        # Wait for feed container to appear
        try:
            await self.page.wait_for_selector(FeedSelectors.FEED_CONTAINER, timeout=15_000)
        except Exception:
            logger.warning("Feed container not found within timeout; attempting extraction anyway")

        consecutive_empty_scrolls = 0
        max_empty_scrolls = 5

        while not shutdown_event.is_set():
            # 1. Backpressure check: wait if pipeline is congested
            await self.producer_gate.wait()

            # 2. Extract currently visible post cards
            from collector.metrics.timer import time_block_async
            async with time_block_async("browser.feed_scroll_per_post"):
                new_posts = await self._extract_visible_cards()

            if new_posts:
                consecutive_empty_scrolls = 0
                for item in new_posts:
                    if shutdown_event.is_set():
                        break

                    # Check limits
                    if (
                        self.config.limits.max_posts is not None
                        and self._total_discovered >= self.config.limits.max_posts
                    ):
                        logger.info("Reached max_posts limit (%d) — stopping feed producer", self.config.limits.max_posts)
                        return self._total_discovered

                    # Check year cutoff limit (e.g. crawl year 2026 and stop on 2025)
                    if (
                        item.posted_at
                        and getattr(self.config.limits, "since_year", None)
                        and item.posted_at.year < self.config.limits.since_year
                    ):
                        logger.info(
                            "Reached post dated %s (year %d < target year %d) — stopping feed producer",
                            item.posted_at.isoformat(),
                            item.posted_at.year,
                            self.config.limits.since_year,
                        )
                        return self._total_discovered

                    # Check if post is already known in storage
                    is_known = False
                    for key in (item.facebook_post_id, item.post_url):
                        if key:
                            check_res = self.is_known_post_fn(key)
                            if asyncio.iscoroutine(check_res):
                                check_res = await check_res
                            if check_res:
                                is_known = True
                                break

                    # Set appropriate action for known items
                    if is_known:
                        if self.config.mode == "refresh":
                            item.action = "REFRESH_COMMENTS"
                        else:
                            item.action = "SKIP"

                    # Push to post_queue (blocking if queue full)
                    await self.post_queue.put(item)
                    self._total_discovered += 1
                    self.counters.posts_discovered += 1

                    if is_known:
                        self._consecutive_known += 1
                        if (
                            self.config.mode == "incremental"
                            and self._consecutive_known >= self.config.incremental.stop_after_consecutive_known_posts
                        ):
                            logger.info(
                                "Incremental mode: reached %d consecutive known posts — stopping",
                                self._consecutive_known,
                            )
                            return self._total_discovered
                    else:
                        self._consecutive_known = 0

                    # Notify callback (e.g. checkpoint manager)
                    if self.on_post_fn:
                        post_time = item.posted_at.isoformat() if item.posted_at else None
                        cb_res = self.on_post_fn(
                            post_id=item.facebook_post_id or item.post_url,
                            post_time=post_time,
                            consecutive_known=self._consecutive_known,
                        )
                        if asyncio.iscoroutine(cb_res):
                            await cb_res

            else:
                consecutive_empty_scrolls += 1
                if consecutive_empty_scrolls >= max_empty_scrolls:
                    logger.info("No new posts discovered after %d consecutive scrolls — end of feed reached", max_empty_scrolls)
                    break

            # 3. Scroll down with human jitter
            await self._scroll_down()

        logger.info("FeedProducer finished. Total posts discovered: %d", self._total_discovered)
        return self._total_discovered

    async def _extract_visible_cards(self) -> list[PostDiscoveredItem]:
        """Scrape all visible post cards currently in DOM."""
        cards = await self.page.query_selector_all(FeedSelectors.POST_ITEMS)
        items: list[PostDiscoveredItem] = []

        for card in cards:
            try:
                raw_data = await self._scrape_card_element(card)
                if not raw_data:
                    continue

                item = PostNormalizer.normalize_feed_card(
                    raw=raw_data,
                    run_id=self.run_id,
                    group_id=self.group_id,
                )
                if not item:
                    continue

                ident = item.facebook_post_id or item.post_url
                if ident and ident in self._seen_ids:
                    continue

                if ident:
                    self._seen_ids.add(ident)

                items.append(item)
            except Exception as e:
                logger.debug("Failed extracting post card: %s", e)

        return items

    async def _scrape_card_element(self, card) -> Optional[dict]:
        """Extract raw attributes from a single post card element."""
        # Find post permalink
        post_link_el = await card.query_selector(FeedSelectors.POST_LINK)
        post_url = None
        if post_link_el:
            post_url = await post_link_el.get_attribute("href")

        # Author info
        author_name = None
        author_name_el = await card.query_selector(FeedSelectors.AUTHOR_NAME)
        if author_name_el:
            author_name = (await author_name_el.inner_text()).strip()

        author_url = None
        author_link_el = await card.query_selector(FeedSelectors.AUTHOR_PROFILE_LINK)
        if author_link_el:
            author_url = await author_link_el.get_attribute("href")

        # Content preview
        content_preview = None
        content_el = await card.query_selector(FeedSelectors.CONTENT_PREVIEW)
        if content_el:
            content_preview = (await content_el.inner_text()).strip()

        # Timestamp
        utime = None
        timestamp_text = None
        ts_el = await card.query_selector(FeedSelectors.TIMESTAMP)
        if ts_el:
            utime = await ts_el.get_attribute("data-utime")
            timestamp_text = (await ts_el.get_attribute("aria-label")) or (await ts_el.inner_text()).strip()

        # Fallback: check all permalink anchors for timestamp text / aria-label
        if not timestamp_text and not utime:
            links = await card.query_selector_all("a[href*='/posts/'], a[href*='/permalink/']")
            for a in links:
                aria = await a.get_attribute("aria-label")
                txt = (await a.inner_text()).strip()
                if aria and any(w in aria.lower() for w in ("giờ", "ngày", "phút", "tháng", "hôm qua", "yesterday")):
                    timestamp_text = aria
                    break
                elif txt and any(w in txt.lower() for w in ("giờ", "ngày", "phút", "tháng", "hôm qua", "yesterday")):
                    timestamp_text = txt
                    break

        # Comment count
        comment_count_text = None
        cmt_el = await card.query_selector(FeedSelectors.COMMENT_COUNT)
        if cmt_el:
            comment_count_text = (await cmt_el.inner_text()).strip()

        # Media preview images (genuine content photos only, no icons or avatars)
        media_urls = []
        from collector.facebook.media import is_content_media_url
        img_els = await card.query_selector_all(FeedSelectors.FEED_IMAGES)
        for img in img_els[:5]:  # limit to 5 previews
            src = await img.get_attribute("src")
            if src and is_content_media_url(src):
                try:
                    box = await img.bounding_box()
                    if box and (box["width"] <= 50 or box["height"] <= 50):
                        continue
                except Exception:
                    pass
                media_urls.append(src)

        if not post_url and not content_preview and not author_name:
            return None

        return {
            "post_url": post_url,
            "author_display_name": author_name,
            "author_profile_url": author_url,
            "content_preview": content_preview,
            "utime": utime,
            "timestamp_text": timestamp_text,
            "comment_count_text": comment_count_text,
            "media_urls": media_urls,
        }

    async def _scroll_down(self) -> None:
        """Perform smooth scroll with human jitter delay."""
        delay_ms = random.randint(
            self.config.browser.scroll_delay_min_ms,
            self.config.browser.scroll_delay_max_ms,
        )
        scroll_step = random.randint(600, 900)

        # Scroll via javascript
        await self.page.evaluate(f"window.scrollBy(0, {scroll_step});")
        await asyncio.sleep(delay_ms / 1000.0)
