"""
collector/facebook/group.py — Group metadata extractor.

Extracts:
- Group Name
- Facebook Group ID & canonical URL
- Member count
- Privacy status (PUBLIC / PRIVATE)
- Description
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from collector.facebook.selectors import GroupSelectors
from collector.storage.layout import slugify

logger = logging.getLogger(__name__)


def parse_member_count(text: str) -> Optional[int]:
    """
    Parse member count strings in English or Vietnamese.
    Examples:
      '12,5K thành viên' -> 12500
      '1.2M members'     -> 1200000
      '350 người'        -> 350
      '1.450 thành viên' -> 1450
    """
    if not text:
        return None

    clean = text.lower().replace("thành viên", "").replace("members", "").replace("người", "").strip()

    # Match numeric with optional multiplier K/M/B
    match = re.search(r"([\d\.,]+)\s*([kmb])?", clean)
    if not match:
        return None

    num_str, unit = match.groups()
    num_str = num_str.replace(" ", "")

    # Handle comma/dot decimal vs thousand separator
    if unit:
        # e.g. 12,5k or 12.5k -> float 12.5
        num_str = num_str.replace(",", ".")
        try:
            val = float(num_str)
            mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(unit, 1)
            return int(val * mult)
        except ValueError:
            return None
    else:
        # Standard integer with dots/commas as thousand separators
        digits_only = re.sub(r"[^\d]", "", num_str)
        return int(digits_only) if digits_only else None


def extract_group_id_from_url(url: str) -> Optional[str]:
    """
    Extract group identifier from Facebook group URL.
    Examples:
      'https://www.facebook.com/groups/123456789/' -> '123456789'
      'https://www.facebook.com/groups/my-group-slug/' -> 'my-group-slug'
    """
    if not url:
        return None
    path = urlparse(url).path
    match = re.search(r"/groups/([^/?#]+)", path)
    if match:
        return match.group(1)
    return None


class GroupExtractor:
    """Extracts group information from the group home page."""

    @staticmethod
    async def extract_metadata(page, group_url: str) -> dict:
        """
        Extract group metadata from current page.
        Does not raise; returns partial dictionary if some selectors fail.
        """
        group_id_from_url = extract_group_id_from_url(group_url) or extract_group_id_from_url(page.url)
        slug = slugify(group_id_from_url or group_url)

        meta = {
            "slug": slug,
            "group_url": group_url,
            "facebook_group_id": group_id_from_url if group_id_from_url and group_id_from_url.isdigit() else None,
            "group_name": None,
            "privacy": "UNKNOWN",
            "member_count": None,
            "description": None,
        }

        # 1. Group Name
        try:
            name_el = await page.query_selector(GroupSelectors.GROUP_NAME)
            if name_el:
                meta["group_name"] = (await name_el.inner_text()).strip()
        except Exception as e:
            logger.debug("Failed to extract group name: %s", e)

        if not meta["group_name"]:
            meta["group_name"] = slug

        # 2. Member count & Privacy from Header
        try:
            # Check membership link first
            members_el = await page.query_selector(GroupSelectors.MEMBERS_LINK)
            if members_el:
                member_text = await members_el.inner_text()
                meta["member_count"] = parse_member_count(member_text)

            # Check header spans for privacy & member count fallback
            header_spans = await page.query_selector_all(GroupSelectors.HEADER_INFO)
            for span in header_spans:
                text = (await span.inner_text()).strip()
                lower = text.lower()
                if "công khai" in lower or "public" in lower:
                    meta["privacy"] = "PUBLIC"
                elif "riêng tư" in lower or "private" in lower:
                    meta["privacy"] = "PRIVATE"

                if meta["member_count"] is None and any(w in lower for w in ("thành viên", "members", "người")):
                    meta["member_count"] = parse_member_count(text)
        except Exception as e:
            logger.debug("Failed to extract header privacy/members: %s", e)

        # 3. Description
        try:
            desc_el = await page.query_selector(GroupSelectors.DESCRIPTION)
            if desc_el:
                meta["description"] = (await desc_el.inner_text()).strip()
        except Exception as e:
            logger.debug("Failed to extract group description: %s", e)

        logger.info(
            "Extracted group metadata: slug=%s name='%s' privacy=%s members=%s",
            meta["slug"], meta["group_name"], meta["privacy"], meta["member_count"],
        )
        return meta
