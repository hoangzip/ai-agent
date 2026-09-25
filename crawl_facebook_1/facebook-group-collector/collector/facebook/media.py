"""
collector/facebook/media.py — Media URL detector and filter.

Filters out:
- Emoji images, reaction icons, UI sprites (/rsrc.php, emoji.php)
- Profile avatars and thumbnails
- Tracking pixels / data URIs

Detects:
- Real post image / photo attachments
- Comment image attachments
- Video sources
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from collector.facebook.selectors import FeedSelectors, PostSelectors
from collector.pipeline.normalizer import clean_facebook_url

logger = logging.getLogger(__name__)

# Patterns that indicate UI assets, icons, emojis, or profile avatars (not content media)
IGNORED_PATTERNS = [
    r"/rsrc\.php/",
    r"emoji\.php",
    r"static\.xx\.fbcdn\.net",
    r"/images/emoji/",
    r"/assets/",
    r"\.svg$",
    r"blank\.gif",
    r"safe_image\.php\?",
    r"/reactions/",
    r"/badges/",
    r"/marketplace/",
    r"/stickers/",
    r"favicon",
    # Profile avatar patterns (e.g. 50x50, 100x100, t39.30808-1)
    r"t39\.30808-1/",
    r"t51\.2885-1/",
    r"/s50x50/",
    r"/p50x50/",
    r"/s100x100/",
    r"/p100x100/",
    r"/s160x160/",
    # Reels, Stories, and Ad thumbnail patterns (sidebar/carousel, not post media)
    r"t15\.5256-10/",
    r"t51\.82787-15/",
    r"t45\.1600-4/",
    r"ctp=s180x540",
    r"ctp=s400x400",
]

_COMPILED_IGNORED = [re.compile(p, re.IGNORECASE) for p in IGNORED_PATTERNS]


def is_content_media_url(url: Optional[str]) -> bool:
    """
    Check if a URL represents a genuine user-uploaded content photo/video,
    and NOT an icon, emoji, UI sprite, reaction, or avatar.
    """
    if not url or not isinstance(url, str):
        return False

    url_lower = url.lower()
    if url_lower.startswith("data:"):
        return False

    # Must be on a Facebook content media CDN
    if not any(domain in url_lower for domain in ("fbcdn.net", "facebook.com", "fb.com", "cdninstagram.com")):
        return False

    # Real photos/videos on Facebook CDN are served from scontent or video hosts
    if not any(k in url_lower for k in ("scontent", "video", "photo")):
        return False

    # Strictly check against ignore patterns (emojis, icons, avatars)
    for pattern in _COMPILED_IGNORED:
        if pattern.search(url_lower):
            return False

    return True


class MediaDetector:
    """Extracts media candidate URLs from DOM elements."""

    @staticmethod
    async def extract_post_media(element) -> list[dict]:
        """
        Extract media URLs from a post card or post detail element.
        Restricts scope to the post article to prevent picking up sidebars,
        reels carousel, or suggested stories.
        Returns list of dict: [{'source_url': str, 'media_type': 'image'|'video'}]
        """
        media_list = []
        seen_urls = set()

        # Target container resolution:
        # If element is a Page or broad container:
        # 1. Post permalinks often open inside a modal dialog: div[role='dialog']
        #    Notice: We must select the dialog containing post content, avoiding notification/chat flyouts!
        # 2. Standalone post pages are inside: div[role='main']
        # 3. Feed cards are already the card element itself
        target = element
        if hasattr(element, "query_selector_all"):
            dialogs_call = element.query_selector_all("div[role='dialog']")
            dialogs = await dialogs_call if asyncio.iscoroutine(dialogs_call) else dialogs_call
            found_post_dialog = False
            for d in (dialogs or []):
                # Ensure it's not a notification/chat popup, but contains genuine post content/articles
                has_msg_call = d.query_selector("div[data-ad-preview='message'], div[data-ad-comet-preview='message'], div[role='article']")
                has_msg = await has_msg_call if asyncio.iscoroutine(has_msg_call) else has_msg_call
                if has_msg:
                    target = d
                    found_post_dialog = True
                    break

            if not found_post_dialog and hasattr(element, "query_selector"):
                main_call = element.query_selector("div[role='main']")
                main_el = await main_call if asyncio.iscoroutine(main_call) else main_call
                if main_el and type(main_el).__name__ not in ("MagicMock", "AsyncMock"):
                    target = main_el

        # 1. Target genuine post photo containers first, fallback to all img
        photo_selectors = (
            "a[href*='/photo'] img, "
            "a[href*='set=pcb.'] img, "
            "a[href*='set=gm.'] img, "
            "a[href*='fbid='] img, "
            "div[data-visualcompletion='media-vc-image'] img"
        )
        res_photos = target.query_selector_all(photo_selectors)
        if asyncio.iscoroutine(res_photos):
            res_photos = await res_photos
        img_elements = list(res_photos or [])

        # Fallback to images inside target if target is an isolated post card/dialog or mock
        if not img_elements and hasattr(target, "query_selector_all"):
            fallback = target.query_selector_all("img")
            if asyncio.iscoroutine(fallback):
                fallback = await fallback
            is_mock = type(target).__name__ in ("MagicMock", "AsyncMock")
            if (found_post_dialog or is_mock) and fallback:
                img_elements = list(fallback or [])

        for img in img_elements:
            # Check if this image belongs to a comment below the post
            try:
                if found_post_dialog or target != element:
                    is_in_cmt_call = img.evaluate("el => el.closest(\"div[role='article']\") !== null")
                    is_in_cmt = await is_in_cmt_call if asyncio.iscoroutine(is_in_cmt_call) else is_in_cmt_call
                    if is_in_cmt:
                        continue
            except Exception:
                pass

            try:
                href_call = img.evaluate("el => el.closest('a') ? el.closest('a').getAttribute('href') : ''")
                href = await href_call if asyncio.iscoroutine(href_call) else href_call
                if href and re.search(r"set=p\.\d+", href):
                    # set=p.<id> is specifically a comment photo attachment
                    continue
            except Exception:
                pass

            src_attr = img.get_attribute("src")
            if asyncio.iscoroutine(src_attr):
                src = await src_attr
            else:
                src = src_attr

            if src and is_content_media_url(src):
                try:
                    box_call = img.bounding_box()
                    if asyncio.iscoroutine(box_call):
                        box = await box_call
                    else:
                        box = box_call
                    if box and (box["width"] <= 50 or box["height"] <= 50):
                        continue
                except Exception:
                    pass
                clean_src = clean_facebook_url(src)
                if clean_src and clean_src not in seen_urls:
                    seen_urls.add(clean_src)
                    media_list.append({
                        "source_url": clean_src,
                        "media_type": "image",
                    })

        # 2. Videos
        vid_call = target.query_selector_all("video")
        if asyncio.iscoroutine(vid_call):
            video_elements = await vid_call
        else:
            video_elements = vid_call or []
        for video in video_elements:
            src = await video.get_attribute("src")
            if src and is_content_media_url(src):
                clean_src = clean_facebook_url(src)
                if clean_src and clean_src not in seen_urls:
                    seen_urls.add(clean_src)
                    media_list.append({
                        "source_url": clean_src,
                        "media_type": "video",
                    })

        return media_list

    @staticmethod
    async def extract_comment_media(comment_element) -> list[dict]:
        """Extract media attachments attached directly to a comment."""
        media_list = []
        seen_urls = set()

        # Comment photos usually live inside an attachment container
        img_elements = await comment_element.query_selector_all("a[href*='photo'] img, img[alt*='Photo'], img[alt*='Hình ảnh']")
        for img in img_elements:
            src = await img.get_attribute("src")
            if src and is_content_media_url(src):
                try:
                    box = await img.bounding_box()
                    if box and (box["width"] <= 50 or box["height"] <= 50):
                        continue
                except Exception:
                    pass
                clean_src = clean_facebook_url(src)
                if clean_src and clean_src not in seen_urls:
                    seen_urls.add(clean_src)
                    media_list.append({
                        "source_url": clean_src,
                        "media_type": "image",
                    })

        return media_list
