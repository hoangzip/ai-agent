"""
collector/facebook/media_gallery.py — Media Gallery Crawler.

Navigates to https://www.facebook.com/groups/{id}/media and:
1. Scrolls through the photo grid to discover all photo links
2. For each photo link → navigates to the original post
3. If post already exists in data → patches missing fields (posted_at, etc.)
4. If post is new → adds to post_queue for full crawl

This is a complement to the feed crawler for groups where posts are
image-heavy and feed crawling misses older items.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Callable, Optional, Set
from urllib.parse import urlparse

from collector.pipeline.normalizer import PostNormalizer, clean_facebook_url

logger = logging.getLogger(__name__)

# Regex to extract Facebook post ID from group post URLs
_POST_ID_RE = re.compile(r"/(?:posts|permalink)/(\d+)")
_SET_POST_RE = re.compile(r"set=(?:gm|pcb)\.(\d+)")
_PHOTO_POST_RE = re.compile(r"[?&](?:story_fbid|fbid|post_id)=(\d+)")


def _extract_post_id_from_url(url: str) -> Optional[str]:
    """Extract Facebook numeric post ID from various URL formats."""
    if not url:
        return None
    # /groups/{id}/posts/{post_id} or /groups/{id}/permalink/{post_id}
    m = _POST_ID_RE.search(url)
    if m:
        return m.group(1)
    # set=gm.{post_id} or set=pcb.{post_id}
    m = _SET_POST_RE.search(url)
    if m:
        return m.group(1)
    # ?story_fbid=...&id=...
    m = _PHOTO_POST_RE.search(url)
    if m:
        return m.group(1)
    return None


class MediaGalleryCrawler:
    """
    Scrolls the group /media page and collects post-level info from each photo.

    Strategy:
    - Navigate to /media grid
    - Scroll down to load more images
    - Collect unique photo/post links
    - For each link: open post page → extract posted_at + content
    - If post known → patch missing fields in existing JSON
    - If post new → emit PostDiscoveredItem to post_queue
    """

    GALLERY_PHOTO_SELECTORS = (
        # Media gallery grid items — direct photo links
        "a[href*='/photo?fbid='], "
        "a[href*='/photo/?fbid='], "
        "a[href*='fbid=']"
    )

    # Selectors for the media grid container to wait for
    GALLERY_CONTAINER_SELECTORS = (
        "div[data-pagelet='GroupMediaPhotos'], "
        "div[role='main'] div[style*='flex-wrap']"
    )

    def __init__(
        self,
        page,
        group_url: str,
        group_slug: str,
        is_known_post_fn: Callable[[str], bool],
        patch_post_fn: Callable[[str, dict], None],
        post_queue: asyncio.Queue,
        run_id: str,
        shutdown_event: asyncio.Event,
        max_scrolls: int = 300,
        scroll_delay_ms: tuple[int, int] = (800, 2000),
    ):
        self.page = page
        self.group_url = group_url.rstrip("/")
        self.group_slug = group_slug
        self.is_known_post_fn = is_known_post_fn
        self.patch_post_fn = patch_post_fn
        self.post_queue = post_queue
        self.run_id = run_id
        self.shutdown_event = shutdown_event
        self.max_scrolls = max_scrolls
        self.scroll_delay_ms = scroll_delay_ms

        self._seen_photo_links: Set[str] = set()
        self._seen_post_ids: Set[str] = set()
        self._new_posts = 0
        self._patched_posts = 0
        self._skipped_posts = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """
        Main entry point. Navigates to /media, scrolls, processes each photo.
        Returns summary dict.
        """
        media_url = f"{self.group_url}/media/photos"
        logger.info("MediaGalleryCrawler: navigating to %s", media_url)
        try:
            await self.page.goto(media_url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            logger.warning("Navigation to media/photos hit: %s; falling back to /media", e)
            try:
                await self.page.goto(f"{self.group_url}/media", wait_until="domcontentloaded", timeout=30_000)
            except Exception as e2:
                logger.warning("Navigation to /media hit: %s; continuing", e2)
        await asyncio.sleep(4)

        # Collect all photo links by scrolling
        all_photo_links = await self._scroll_and_collect()
        logger.info("MediaGalleryCrawler: collected %d unique photo links", len(all_photo_links))

        # Process each photo link
        for i, photo_link in enumerate(all_photo_links):
            if self.shutdown_event.is_set():
                break
            logger.info(
                "MediaGalleryCrawler: processing photo %d/%d — %s",
                i + 1, len(all_photo_links), photo_link[:80],
            )
            await self._process_photo_link(photo_link)
            # Small delay between photo opens
            await asyncio.sleep(random.uniform(0.5, 1.5))

        summary = {
            "total_photos_found": len(all_photo_links),
            "new_posts_queued": self._new_posts,
            "existing_posts_patched": self._patched_posts,
            "skipped_already_complete": self._skipped_posts,
        }
        logger.info("MediaGalleryCrawler finished: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Scrolling & Link Collection
    # ------------------------------------------------------------------

    async def _scroll_and_collect(self) -> list[str]:
        """Scroll media grid and collect all unique photo links."""
        collected: list[str] = []
        no_new_count = 0
        max_no_new = 15  # allow up to 15 scrolls with no new photos before stopping

        # Wait for any photo links to appear
        try:
            await self.page.wait_for_selector(
                "a[href*='fbid='], a[href*='/photo/']",
                timeout=15_000,
            )
        except Exception:
            logger.warning("Media gallery: grid did not appear within 15s")

        for scroll_i in range(self.max_scrolls):
            if self.shutdown_event.is_set():
                break

            # Collect links currently visible
            new_this_round = await self._collect_visible_photo_links()
            added = 0
            for link in new_this_round:
                if link not in self._seen_photo_links:
                    self._seen_photo_links.add(link)
                    collected.append(link)
                    added += 1

            if added == 0:
                no_new_count += 1
                logger.debug("Scroll %d: no new photos (consecutive=%d)", scroll_i, no_new_count)
                if no_new_count >= max_no_new:
                    logger.info("MediaGalleryCrawler: end of gallery reached after %d scrolls (total photos=%d)", scroll_i, len(collected))
                    break
            else:
                no_new_count = 0
                logger.info("Scroll %d: +%d new photos (total=%d)", scroll_i, added, len(collected))

            # Scroll down — Facebook desktop uses internal scrollable containers
            await self.page.evaluate("""() => {
                const scrollables = Array.from(document.querySelectorAll('*'))
                    .filter(el => el.scrollHeight > el.clientHeight + 50 && el.clientHeight > 200);
                for (let el of scrollables) {
                    el.scrollTop = el.scrollHeight;
                }
                window.scrollBy(0, window.innerHeight * 2);
                if (document.documentElement) document.documentElement.scrollTop += 1000;
                if (document.body) document.body.scrollTop += 1000;
            }""")
            try:
                await self.page.mouse.wheel(0, 2000)
            except Exception:
                pass

            delay_ms = random.randint(*self.scroll_delay_ms)
            await asyncio.sleep(delay_ms / 1000)
            await asyncio.sleep(0.5)

        return collected

    async def _collect_visible_photo_links(self) -> list[str]:
        """Extract all photo href links from current viewport."""
        links = []
        try:
            elements = await self.page.query_selector_all(
                "a[href*='fbid='], a[href*='/photo/'], a[href*='/photo.php']"
            )
            for el in elements:
                href = await el.get_attribute("href")
                if href and ("fbid=" in href or "/photo/" in href or "/photo.php" in href):
                    # Skip navigation/tab links
                    if any(skip in href for skip in ["/media/photos", "/media/videos", "/media/albums", "/media/?", "/media#"]):
                        continue
                    if href.startswith("/"):
                        href = "https://www.facebook.com" + href
                    clean = clean_facebook_url(href)
                    if clean:
                        links.append(clean)
        except Exception as e:
            logger.debug("Error collecting photo links: %s", e)
        return links

    # ------------------------------------------------------------------
    # Per-photo processing
    # ------------------------------------------------------------------

    async def _process_photo_link(self, photo_url: str) -> None:
        """
        Navigate to photo → extract post URL → check if known → patch or queue.
        """
        try:
            # Open photo in same page
            await self.page.goto(photo_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(1.5)

            # Try to get the original post URL from the page
            post_url = await self._extract_post_url_from_photo_page()
            if not post_url:
                # Fallback: treat the photo URL itself as post URL if it's a /posts/ link
                if "/posts/" in photo_url:
                    post_url = photo_url
                else:
                    logger.debug("Could not extract post URL from %s", photo_url)
                    return

            post_id = _extract_post_id_from_url(post_url)
            if not post_id:
                logger.debug("Could not extract post ID from %s", post_url)
                return

            # Deduplicate
            if post_id in self._seen_post_ids:
                return
            self._seen_post_ids.add(post_id)

            # Navigate to the actual post page to extract full info
            await self._navigate_to_post_and_process(post_url, post_id)

        except Exception as e:
            logger.warning("Error processing photo %s: %s", photo_url[:80], e)

    async def _extract_post_url_from_photo_page(self) -> Optional[str]:
        """
        On a Facebook photo page, find the link back to the original post.
        Facebook photo pages often have a 'View Post' or permalink link.
        """
        try:
            # Strategy 1: look for a link containing /posts/ or /permalink/ in the page
            links = await self.page.query_selector_all("a[href*='/posts/'], a[href*='/permalink/']")
            for link in links:
                href = await link.get_attribute("href")
                if href and "/groups/" in href and ("/posts/" in href or "/permalink/" in href):
                    if href.startswith("/"):
                        href = "https://www.facebook.com" + href
                    return clean_facebook_url(href)

            # Strategy 2: check current URL — maybe it redirected to the post
            current_url = self.page.url
            if "/posts/" in current_url or "/permalink/" in current_url:
                return clean_facebook_url(current_url)

        except Exception as e:
            logger.debug("Error extracting post URL: %s", e)
        return None

    async def _navigate_to_post_and_process(self, post_url: str, fb_post_id: str) -> None:
        """Navigate to the post page and extract/patch data."""
        try:
            if post_url not in self.page.url:
                await self.page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(2)

            # Check if post is already known
            is_known = self.is_known_post_fn(fb_post_id) or self.is_known_post_fn(post_url)

            # Extract post data from DOM
            post_data = await self._extract_post_data_from_page(post_url, fb_post_id)

            if is_known:
                # Patch missing fields only (exclude internal _dt fields)
                patch = {k: v for k, v in post_data.items() if v is not None and not k.endswith("_dt")}
                if patch:
                    self.patch_post_fn(fb_post_id, patch)
                    self._patched_posts += 1
                    logger.info("Patched existing post %s: %s", fb_post_id, list(patch.keys()))
                else:
                    self._skipped_posts += 1
            else:
                # New post → queue for full crawl
                from collector.pipeline.items import PostDiscoveredItem
                from datetime import datetime, timezone
                item = PostDiscoveredItem(
                    discovery_run_id=self.run_id,
                    discovered_at=datetime.now(tz=timezone.utc),
                    facebook_post_id=fb_post_id,
                    post_url=post_url,
                    facebook_group_id=self.group_slug,
                    posted_at=post_data.get("posted_at_dt"),
                    author_display_name=post_data.get("author_display_name"),
                    author_profile_url=post_data.get("author_profile_url"),
                    content_preview=post_data.get("content"),
                    media_urls_preview=post_data.get("media_urls", []),
                    action=post_data.get("action", "FULL_CRAWL"),
                )
                await self.post_queue.put(item)
                self._new_posts += 1
                logger.info("Queued NEW post %s from media gallery", fb_post_id)

        except Exception as e:
            logger.warning("Error processing post %s: %s", fb_post_id, e)

    async def _extract_post_data_from_page(self, post_url: str, fb_post_id: str) -> dict:
        """Extract available metadata from current post page."""
        from collector.facebook.selectors import FeedSelectors
        from collector.pipeline.normalizer import parse_timestamp

        data: dict = {}

        try:
            # 1. Extract timestamp (utime or relative text)
            utime = None
            timestamp_el = await self.page.query_selector(
                "abbr[data-utime], span[data-utime], a[href*='/posts/'] abbr[data-utime], a[href*='/permalink/'] abbr[data-utime]"
            )
            if timestamp_el:
                utime = await timestamp_el.get_attribute("data-utime")

            timestamp_text = None
            if not utime:
                time_candidates = await self.page.query_selector_all(
                    "abbr, a[role='link'] abbr, a[href*='/posts/'], a[href*='/permalink/'], a[role='link']"
                )
                for el in time_candidates:
                    aria = await el.get_attribute("aria-label")
                    txt = (await el.inner_text()).strip()
                    cand = aria or txt
                    if cand:
                        parsed = parse_timestamp(None, cand)
                        if parsed:
                            timestamp_text = cand
                            break

            parsed_ts = parse_timestamp(utime, timestamp_text)
            if parsed_ts:
                data["posted_at"] = parsed_ts.isoformat()
                data["posted_at_dt"] = parsed_ts

            # 2. Extract author
            author_el = await self.page.query_selector(
                FeedSelectors.AUTHOR_NAME + ", h3 > span > a, h2 > span > a, strong > span > a, a[role='link'] strong"
            )
            if author_el:
                name = (await author_el.inner_text()).strip()
                if name:
                    data["author_display_name"] = name

            author_link_el = await self.page.query_selector(
                FeedSelectors.AUTHOR_PROFILE_LINK + ", a[href*='/user/'], a[href*='profile.php']"
            )
            if author_link_el:
                href = await author_link_el.get_attribute("href")
                if href:
                    data["author_profile_url"] = clean_facebook_url(href)

            # 3. Extract content text
            content_el = await self.page.query_selector(
                "div[data-ad-comet-preview='message'], "
                "div[data-ad-preview='message'], "
                "div[class*='userContent']"
            )
            if content_el:
                text = await content_el.inner_text()
                if text:
                    data["content"] = text.strip()[:2000]

            # 4. Extract post media
            from collector.facebook.media import MediaDetector
            post_media = await MediaDetector.extract_post_media(self.page)
            if post_media:
                data["media_urls"] = [m["source_url"] for m in post_media if m.get("source_url")]

        except Exception as e:
            logger.debug("Error extracting post data from %s: %s", post_url, e)

        return data
