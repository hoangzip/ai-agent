"""
collector/pipeline/dedupe.py — Multi-tier deduplication engine.

Provides:
- In-memory fast cache (O(1) set lookup) to eliminate disk I/O for hot items
- Storage-backed fallback (checks persistent indices for cold items)
- Automatic promotion: items found in persistent storage are cached in-memory
- Pre-warming: loads existing group indices into memory at crawl startup
"""
from __future__ import annotations

import logging
from typing import Optional, Set

from collector.storage.json_store import read_index
from collector.storage.layout import StorageLayout
from collector.storage.repository import CommentRepo, MediaRepo, PostRepo

logger = logging.getLogger(__name__)


class DedupeManager:
    """
    Two-tier deduplication manager:
      Tier 1: In-memory set (instant O(1), zero I/O)
      Tier 2: Storage index files (reads index/posts_*.json, comments_*.json, etc.)
    """

    def __init__(self, layout: StorageLayout, group_slug: str):
        self.layout = layout
        self.group_slug = group_slug
        self.post_repo = PostRepo(layout, group_slug)
        self.media_repo = MediaRepo(layout)

        # In-memory caches
        self._seen_post_ids: Set[str] = set()
        self._seen_post_urls: Set[str] = set()
        self._seen_comment_ids: Set[str] = set()
        self._seen_comment_dedupes: Set[str] = set()
        self._seen_media_sha256: Set[str] = set()

    async def warm_up(self) -> None:
        """Pre-populate in-memory cache from persistent indices."""
        try:
            # 1. Warm up posts
            post_index = await read_index(self.layout.post_index_path(self.group_slug))
            for k in post_index.keys():
                if k.startswith("fb_pid:"):
                    self._seen_post_ids.add(k[7:])
                elif k.startswith("url:"):
                    self._seen_post_urls.add(k[4:])

            # 2. Warm up media SHA-256
            media_index = await read_index(self.layout.media_sha256_index_path())
            self._seen_media_sha256.update(media_index.keys())

            logger.info(
                "DedupeManager warmed up: %d post IDs, %d post URLs, %d media hashes",
                len(self._seen_post_ids), len(self._seen_post_urls), len(self._seen_media_sha256),
            )
        except Exception as e:
            logger.debug("DedupeManager warm_up error: %s", e)

    # ------------------------------------------------------------------
    # Post Deduplication
    # ------------------------------------------------------------------

    async def is_post_known(self, facebook_post_id: Optional[str] = None, post_url: Optional[str] = None) -> bool:
        """
        Check if post is known.
        Tier 1: Check in-memory set
        Tier 2: Check PostRepo storage index
        """
        # Tier 1: In-memory
        if facebook_post_id and facebook_post_id in self._seen_post_ids:
            return True
        if post_url and post_url in self._seen_post_urls:
            return True

        # Tier 2: Storage index
        if await self.post_repo.exists(facebook_post_id=facebook_post_id, post_url=post_url):
            # Promote to Tier 1
            if facebook_post_id:
                self._seen_post_ids.add(facebook_post_id)
            if post_url:
                self._seen_post_urls.add(post_url)
            return True

        return False

    def mark_post_seen(self, facebook_post_id: Optional[str] = None, post_url: Optional[str] = None) -> None:
        """Add post identifiers to in-memory cache."""
        if facebook_post_id:
            self._seen_post_ids.add(facebook_post_id)
        if post_url:
            self._seen_post_urls.add(post_url)

    # ------------------------------------------------------------------
    # Comment Deduplication
    # ------------------------------------------------------------------

    async def is_comment_known(
        self,
        post_id: str,
        facebook_comment_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ) -> bool:
        """Check if comment is known in memory or in post's CommentRepo index."""
        if facebook_comment_id and facebook_comment_id in self._seen_comment_ids:
            return True
        if dedupe_key and dedupe_key in self._seen_comment_dedupes:
            return True

        comment_repo = CommentRepo(self.layout, post_id)
        if await comment_repo.exists(facebook_comment_id=facebook_comment_id, dedupe_key=dedupe_key):
            if facebook_comment_id:
                self._seen_comment_ids.add(facebook_comment_id)
            if dedupe_key:
                self._seen_comment_dedupes.add(dedupe_key)
            return True

        return False

    def mark_comment_seen(
        self,
        facebook_comment_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ) -> None:
        """Add comment to in-memory cache."""
        if facebook_comment_id:
            self._seen_comment_ids.add(facebook_comment_id)
        if dedupe_key:
            self._seen_comment_dedupes.add(dedupe_key)

    # ------------------------------------------------------------------
    # Media Deduplication
    # ------------------------------------------------------------------

    async def is_media_sha_known(self, sha256: str) -> bool:
        """Check if binary file with this SHA-256 has already been saved."""
        if sha256 in self._seen_media_sha256:
            return True

        # Check storage index
        media_index = await read_index(self.layout.media_sha256_index_path())
        if sha256 in media_index:
            self._seen_media_sha256.add(sha256)
            return True

        return False

    def mark_media_sha_seen(self, sha256: str) -> None:
        """Add SHA-256 to in-memory cache."""
        self._seen_media_sha256.add(sha256)
