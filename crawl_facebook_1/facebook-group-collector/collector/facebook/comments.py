"""
collector/facebook/comments.py — Comment and reply tree extractor.

Responsibilities:
- Expand comment threads (load more comments & view replies)
- Extract top-level comments (depth=0)
- Extract replies (depth=1+) and link with parent_comment_id
- Delta comment extraction support (stop after N consecutive known comments)
- Return strongly-typed CommentItem list
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from collector.facebook.selectors import CommentSelectors
from collector.pipeline.items import CommentItem
from collector.pipeline.normalizer import (
    clean_facebook_url,
    extract_user_id,
    parse_timestamp,
)

logger = logging.getLogger(__name__)


def extract_comment_id_from_url(url: Optional[str]) -> Optional[str]:
    """
    Extract comment ID from Facebook URL query or path.
    Examples:
      '?comment_id=123456789' -> '123456789'
      '&reply_comment_id=987654321' -> '987654321'
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "reply_comment_id" in query and query["reply_comment_id"]:
            return query["reply_comment_id"][0]
        if "comment_id" in query and query["comment_id"]:
            return query["comment_id"][0]
    except Exception:
        pass

    match = re.search(r"comment_id[=/](\d+)", url)
    if match:
        return match.group(1)
    return None


class CommentExtractor:
    """Extracts comments and hierarchical replies from a post page."""

    def __init__(
        self,
        page,
        max_expand_clicks: int = 5,
        max_replies_clicks_per_comment: int = 3,
        known_comment_threshold: int = 5,
    ):
        self.page = page
        self.max_expand_clicks = max_expand_clicks
        self.max_replies_clicks_per_comment = max_replies_clicks_per_comment
        self.known_comment_threshold = known_comment_threshold

    async def extract_comments_tree(
        self,
        post_internal_id: str,
        is_known_comment_fn: Optional[Callable[[str], bool]] = None,
    ) -> list[CommentItem]:
        """
        Extract complete comments and reply tree for the loaded post page.

        Args:
            post_internal_id: UUID of the post record in storage
            is_known_comment_fn: Optional callback returning True if comment ID is known (for delta crawl)

        Returns:
            List of CommentItem items (top-level and replies).
        """
        # 1. Expand "View more comments" buttons
        await self._expand_more_comments()

        # 2. Query all comment elements
        comment_elements = await self.page.query_selector_all(CommentSelectors.TOP_LEVEL_COMMENTS)
        logger.debug("Found %d comment candidate elements in post %s", len(comment_elements), post_internal_id)

        all_comments: list[CommentItem] = []
        consecutive_known = 0
        seen_comment_ids: set[str] = set()

        for el in comment_elements:
            try:
                top_comment = await self._parse_single_comment(
                    el,
                    post_internal_id=post_internal_id,
                    depth=0,
                    parent_comment_id=None,
                )
                if not top_comment:
                    continue

                cid = top_comment.facebook_comment_id
                if cid and cid in seen_comment_ids:
                    continue
                if cid:
                    seen_comment_ids.add(cid)

                all_comments.append(top_comment)

                # Delta check
                if is_known_comment_fn and cid:
                    check_res = is_known_comment_fn(cid)
                    if asyncio.iscoroutine(check_res):
                        check_res = await check_res
                    if check_res:
                        consecutive_known += 1
                        if consecutive_known >= self.known_comment_threshold:
                            logger.info("Delta comments: reached %d consecutive known comments — stopping", consecutive_known)
                            break
                    else:
                        consecutive_known = 0
                else:
                    consecutive_known = 0

                # 3. Expand & extract replies for this top-level comment
                replies = await self._extract_replies_for_comment(
                    el,
                    post_internal_id=post_internal_id,
                    parent_id=cid,
                    seen_ids=seen_comment_ids,
                )
                all_comments.extend(replies)

            except Exception as e:
                logger.debug("Error extracting comment element: %s", e)

        logger.info("Extracted %d comments/replies for post %s", len(all_comments), post_internal_id)
        return all_comments

    async def _parse_single_comment(
        self,
        el,
        post_internal_id: str,
        depth: int = 0,
        parent_comment_id: Optional[str] = None,
    ) -> Optional[CommentItem]:
        """Parse DOM elements into CommentItem."""
        # Author name
        author_name = None
        author_el = await el.query_selector(CommentSelectors.COMMENT_AUTHOR)
        if author_el:
            author_name = (await author_el.inner_text()).strip()

        # Author link
        author_url = None
        author_link_el = await el.query_selector(CommentSelectors.COMMENT_AUTHOR_LINK)
        if author_link_el:
            author_url = clean_facebook_url(await author_link_el.get_attribute("href"))
            if not author_name:
                cand_text = (await author_link_el.inner_text()).strip()
                if cand_text:
                    author_name = cand_text
                else:
                    aria = await author_link_el.get_attribute("aria-label")
                    if aria:
                        author_name = aria.strip()
        author_uid = extract_user_id(author_url)

        # Content
        content = None
        content_el = await el.query_selector(CommentSelectors.COMMENT_TEXT)
        if content_el:
            content = (await content_el.inner_text()).strip()

        # Timestamp & Comment ID
        comment_id = None
        commented_at = None
        ts_el = await el.query_selector(CommentSelectors.COMMENT_TIMESTAMP)
        if ts_el:
            href = await ts_el.get_attribute("href")
            comment_id = extract_comment_id_from_url(href)
            utime = await ts_el.get_attribute("data-utime")
            ts_text = (await ts_el.inner_text()).strip()
            commented_at = parse_timestamp(utime, ts_text)

        # Must have at least some identifiable information
        if not content and not author_name and not comment_id:
            return None

        # Anonymous check
        from collector.pipeline.normalizer import is_anonymous_user
        is_anon = is_anonymous_user(
            display_name=author_name,
            profile_url=author_url,
            facebook_user_id=author_uid,
        )

        # Comment image attachments (excluding avatars and emojis)
        media_urls = []
        from collector.facebook.media import is_content_media_url
        img_elements = await el.query_selector_all("a[href*='photo'] img, img[alt*='Photo'], img[alt*='Hình ảnh'], div[data-visualcompletion='media-vc-image'] img, img")
        for img in img_elements:
            src = await img.get_attribute("src")
            if src and is_content_media_url(src):
                try:
                    box = await img.bounding_box()
                    if box and (box["width"] <= 50 or box["height"] <= 50):
                        continue
                except Exception:
                    pass
                if src not in media_urls:
                    media_urls.append(src)

        return CommentItem(
            post_internal_id=post_internal_id,
            facebook_comment_id=comment_id,
            parent_comment_id=parent_comment_id,
            author_display_name=author_name,
            author_profile_url=author_url,
            author_facebook_user_id=author_uid,
            author_is_anonymous=is_anon,
            content=content,
            commented_at=commented_at,
            depth=depth,
            media_urls=media_urls,
            discovered_at=datetime.now(timezone.utc),
        )

    async def _extract_replies_for_comment(
        self,
        comment_el,
        post_internal_id: str,
        parent_id: Optional[str],
        seen_ids: set[str],
    ) -> list[CommentItem]:
        """Expand replies button if present, then extract reply items."""
        replies: list[CommentItem] = []

        # Find reply expand button
        try:
            view_replies_btns = await comment_el.query_selector_all(CommentSelectors.VIEW_REPLIES_BUTTON)
            for btn in view_replies_btns[: self.max_replies_clicks_per_comment]:
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1.0)
        except Exception:
            pass

        # Query reply containers inside comment element
        reply_elements = await comment_el.query_selector_all(CommentSelectors.REPLY_ITEMS)
        for rel in reply_elements:
            try:
                reply_item = await self._parse_single_comment(
                    rel,
                    post_internal_id=post_internal_id,
                    depth=1,
                    parent_comment_id=parent_id,
                )
                if not reply_item:
                    continue

                rcid = reply_item.facebook_comment_id
                if rcid and rcid in seen_ids:
                    continue
                if rcid:
                    seen_ids.add(rcid)

                replies.append(reply_item)
            except Exception as e:
                logger.debug("Error parsing reply element: %s", e)

        return replies

    async def _expand_more_comments(self) -> None:
        """Click 'View more comments' buttons up to max_expand_clicks times."""
        for _ in range(self.max_expand_clicks):
            try:
                more_btn = await self.page.query_selector(CommentSelectors.LOAD_MORE_COMMENTS)
                if more_btn and await more_btn.is_visible():
                    logger.debug("Clicking 'View more comments'...")
                    await more_btn.click()
                    await asyncio.sleep(1.5)
                else:
                    break
            except Exception:
                break
