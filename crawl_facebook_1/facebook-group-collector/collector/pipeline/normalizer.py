"""
collector/pipeline/normalizer.py — Transforms raw DOM data into typed PostDiscoveredItem.

Responsibilities:
- Extract and clean Facebook Post ID and canonical permalink
- Parse author metadata (display name, profile URL, user ID)
- Parse timestamps (Unix utime or relative text)
- Parse reaction and comment counts
- Clean tracking query params from URLs (__cft__, __tn__, etc.)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from collector.pipeline.items import PostDiscoveredItem

logger = logging.getLogger(__name__)


def clean_facebook_url(url: Optional[str]) -> Optional[str]:
    """Remove tracking parameters (__cft__, __tn__, ref, etc.) from Facebook URLs."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        if any(cdn in netloc for cdn in ("fbcdn.net", "cdninstagram.com", "fbsbx.com")):
            # Remove only tracking parameters from CDN media URLs, preserving auth tokens (oh, oe, _nc_*, stp)
            query_dict = parse_qs(parsed.query, keep_blank_values=True)
            tracking_keys = {"__cft__", "__cft__[0]", "__tn__", "ref", "fbclid", "__xts__"}
            clean_query = {k: v for k, v in query_dict.items() if k not in tracking_keys}
            query_parts = []
            for k, vals in clean_query.items():
                for v in vals:
                    if v:
                        query_parts.append(f"{k}={v}")
                    else:
                        query_parts.append(k)
            query_str = "&".join(query_parts)
            return urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                query_str,
                "",
            ))

        # Keep only essential query params (e.g. id, story_fbid)
        query_dict = parse_qs(parsed.query)
        allowed_params = {"id", "story_fbid", "fbid", "post_id"}
        clean_query = {k: v for k, v in query_dict.items() if k in allowed_params}
        query_string = "&".join(f"{k}={v[0]}" for k, v in clean_query.items())

        # Clean trailing slashes
        path = parsed.path.rstrip("/")
        if not path and not query_string:
            return None

        cleaned = urlunparse((
            parsed.scheme or "https",
            parsed.netloc or "www.facebook.com",
            path,
            "",
            query_string,
            "",
        ))
        return cleaned
    except Exception:
        return url


def is_anonymous_user(
    display_name: Optional[str] = None,
    profile_url: Optional[str] = None,
    facebook_user_id: Optional[str] = None,
) -> bool:
    """
    Detect whether a Facebook user/author is anonymous or a real account.
    Handles:
    - Standard anonymous names (EN: 'Anonymous participant', 'Group member'; VI: 'Người tham gia ẩn danh', 'Thành viên ẩn danh')
    - Auto-generated Facebook aliases (e.g. 'StunningDachshund8945', 'ArticulateFrog1260', 'PositiveHummingbird3334')
    - Absence of valid profile link or user ID
    """
    name = (display_name or "").strip()
    if not name and not profile_url:
        return False

    name_lower = name.lower()

    # 1. Direct keyword check
    anon_keywords = [
        "anonymous",
        "ẩn danh",
        "group member",
        "thành viên nhóm",
    ]
    if any(kw in name_lower for kw in anon_keywords):
        return True

    # 2. Check generated animal/adjective pattern like 'StunningDachshund8945', 'ArticulateFrog1260'
    if name and re.match(r"^[A-Z][a-z]+[A-Z][a-z]+\d+$", name):
        return True

    # 3. If explicit dummy anonymous profile placeholder
    if profile_url and any(profile_url.lower().endswith(x) for x in ("/user/0/", "/user/-1/", "profile.php?id=0")):
        return True

    return False


def extract_post_id(url: Optional[str]) -> Optional[str]:
    """
    Extract Facebook post ID from permalink URL.
    Examples:
      '/groups/123/posts/456789/' -> '456789'
      '/groups/123/permalink/456789/' -> '456789'
      'permalink.php?story_fbid=456789&id=123' -> '456789'
    """
    if not url:
        return None

    # Pattern 1: /posts/<id> or /permalink/<id>
    match = re.search(r"/(?:posts|permalink)/(\d+)", url)
    if match:
        return match.group(1)

    # Pattern 2: story_fbid=<id> or fbid=<id>
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for param in ("story_fbid", "fbid", "post_id"):
            if param in query and query[param]:
                val = query[param][0]
                if val.isdigit():
                    return val
    except Exception:
        pass

    return None


def extract_user_id(url: Optional[str]) -> Optional[str]:
    """Extract Facebook user ID from profile URL if present."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "id" in query and query["id"] and query["id"][0].isdigit():
            return query["id"][0]
        # Match /user/<id>
        match = re.search(r"/user/(\d+)", parsed.path)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def parse_count(text: Optional[str]) -> Optional[int]:
    """
    Parse comment or reaction count string.
    Examples:
      '45 bình luận' -> 45
      '1,2K comments' -> 1200
      '500' -> 500
    """
    if not text:
        return None
    clean = text.lower().replace("bình luận", "").replace("comments", "").replace("lượt thích", "").strip()
    match = re.search(r"([\d\.,]+)\s*([kmb])?", clean)
    if not match:
        return None

    num_str, unit = match.groups()
    num_str = num_str.replace(" ", "")

    if unit:
        num_str = num_str.replace(",", ".")
        try:
            val = float(num_str)
            mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(unit, 1)
            return int(val * mult)
        except ValueError:
            return None
    else:
        digits_only = re.sub(r"[^\d]", "", num_str)
        return int(digits_only) if digits_only else None


def parse_timestamp(utime_str: Optional[str], text_str: Optional[str] = None) -> Optional[datetime]:
    """Parse Unix timestamp string (data-utime) or relative/absolute Facebook date string."""
    if utime_str and utime_str.strip().isdigit():
        try:
            return datetime.fromtimestamp(int(utime_str.strip()), tz=timezone.utc)
        except (ValueError, OverflowError):
            pass

    if not text_str:
        return None

    t = text_str.lower().strip()
    now = datetime.now(timezone.utc)

    # 1. Relative minutes
    match = re.search(r"(\d+)\s*(?:phút|mins?|m|minutes?)\b", t)
    if match:
        return now - timedelta(minutes=int(match.group(1)))

    # 2. Relative hours
    match = re.search(r"(\d+)\s*(?:giờ|hrs?|h|hours?)\b", t)
    if match:
        return now - timedelta(hours=int(match.group(1)))

    # 3. Relative days
    match = re.search(r"(\d+)\s*(?:ngày|days?|d)\b", t)
    if match:
        return now - timedelta(days=int(match.group(1)))

    # 3b. Relative weeks
    match = re.search(r"(\d+)\s*(?:tuần|weeks?|w)\b", t)
    if match:
        return now - timedelta(weeks=int(match.group(1)))

    # 4. Yesterday
    if "hôm qua" in t or "yesterday" in t:
        return now - timedelta(days=1)

    # 5. Date with Vietnamese month or separator: "25 tháng 12, 2025", "25 thg 12 lúc 14:00", "25/12/2025"
    m = re.search(r"(\d{1,2})\s*(?:tháng|thg|\/|-)\s*(\d{1,2})(?:[,\s]+(?:năm\s*)?(\d{4}))?", t)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

    # 6. Date with English month: "28 July", "28 July at 13:30", "July 28, 2024"
    en_months = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12
    }
    month_names_re = "|".join(en_months.keys())
    # Format: "28 July 2024" or "28 July at 13:30" or "28 July"
    m_en = re.search(rf"(\d{{1,2}})\s+({month_names_re})(?:[,\s]+(\d{{4}}))?", t)
    if m_en:
        day = int(m_en.group(1))
        month = en_months[m_en.group(2)]
        year = int(m_en.group(3)) if m_en.group(3) else now.year
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

    # Format: "July 28, 2024" or "July 28"
    m_en2 = re.search(rf"({month_names_re})\s+(\d{{1,2}})(?:[,\s]+(\d{{4}}))?", t)
    if m_en2:
        month = en_months[m_en2.group(1)]
        day = int(m_en2.group(2))
        year = int(m_en2.group(3)) if m_en2.group(3) else now.year
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


class PostNormalizer:
    """Normalizes raw post data extracted from feed card into PostDiscoveredItem."""

    @staticmethod
    def normalize_feed_card(
        raw: dict,
        run_id: str,
        group_id: Optional[str] = None,
    ) -> Optional[PostDiscoveredItem]:
        """
        Build PostDiscoveredItem from raw card extraction.
        Returns None if neither facebook_post_id nor post_url could be extracted.
        """
        raw_url = raw.get("post_url")
        cleaned_url = clean_facebook_url(raw_url)
        post_id = raw.get("facebook_post_id") or extract_post_id(cleaned_url)

        if not post_id and not cleaned_url:
            logger.debug("Post card missing both post_id and permalink URL — skipping")
            return None

        # Author info
        author_name = raw.get("author_display_name")
        raw_author_url = raw.get("author_profile_url")
        clean_author_url = clean_facebook_url(raw_author_url)
        author_uid = raw.get("author_facebook_user_id") or extract_user_id(clean_author_url)

        # Content & title
        content = raw.get("content_preview")
        title = raw.get("title")
        title_source = "facebook" if title else None
        if not title and content:
            # Derive title from first line of content (up to 100 chars)
            first_line = content.split("\n")[0].strip()
            title = first_line[:100] + ("..." if len(first_line) > 100 else "")
            title_source = "derived"

        # Timestamp
        posted_at = parse_timestamp(
            utime_str=raw.get("utime"),
            text_str=raw.get("timestamp_text"),
        )

        # Comment count
        comment_count = parse_count(raw.get("comment_count_text"))

        # Media preview URLs
        media_urls = [clean_facebook_url(u) for u in raw.get("media_urls", []) if u]

        # Author anonymous check
        is_anon = is_anonymous_user(
            display_name=author_name,
            profile_url=clean_author_url,
            facebook_user_id=author_uid,
        )

        item = PostDiscoveredItem(
            discovery_run_id=run_id,
            discovered_at=datetime.now(timezone.utc),
            facebook_post_id=post_id,
            post_url=cleaned_url,
            facebook_group_id=group_id or raw.get("facebook_group_id"),
            author_display_name=author_name,
            author_profile_url=clean_author_url,
            author_facebook_user_id=author_uid,
            author_is_anonymous=is_anon,
            title=title,
            title_source=title_source,
            content_preview=content,
            posted_at=posted_at,
            source_comment_count=comment_count,
            media_urls_preview=media_urls,
            action="FULL_CRAWL",
        )
        return item
