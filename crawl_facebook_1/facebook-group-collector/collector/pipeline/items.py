"""
collector/pipeline/items.py — Internal item/message schemas.

These dataclasses are the contracts between producers and consumers.
All fields that may not be extractable from Facebook DOM are Optional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Post discovery item — pushed by Browser Producer into post_queue
# ---------------------------------------------------------------------------

@dataclass
class PostDiscoveredItem:
    """Represents a post card discovered during feed scrolling."""

    # Run context
    discovery_run_id: str          # UUID of crawl_run
    discovered_at: datetime

    # Facebook-sourced identifiers (nullable — FB DOM may not expose)
    facebook_post_id: Optional[str] = None
    post_url: Optional[str] = None
    facebook_group_id: Optional[str] = None

    # Author info (nullable)
    author_display_name: Optional[str] = None
    author_profile_url: Optional[str] = None
    author_facebook_user_id: Optional[str] = None
    author_is_anonymous: bool = False

    # Post content from feed card (may be truncated)
    title: Optional[str] = None
    title_source: Optional[str] = None    # 'facebook' | 'derived'
    content_preview: Optional[str] = None
    posted_at: Optional[datetime] = None

    # Signals for action decision
    source_comment_count: Optional[int] = None
    media_urls_preview: list[str] = field(default_factory=list)

    # Action set by scheduler/decision logic
    # 'FULL_CRAWL' | 'REFRESH_COMMENTS' | 'SKIP' | 'DISCOVER_ONLY'
    action: str = "FULL_CRAWL"

    def has_identifier(self) -> bool:
        """True if we have at least one way to identify this post."""
        return bool(self.facebook_post_id or self.post_url)


# ---------------------------------------------------------------------------
# Comment item — pushed by Comment Workers into comment_queue
# ---------------------------------------------------------------------------

@dataclass
class CommentItem:
    """Represents a single comment or reply extracted from a post page."""

    post_internal_id: str          # UUID of facebook_posts row

    # Facebook-sourced (nullable)
    facebook_comment_id: Optional[str] = None
    parent_comment_id: Optional[str] = None   # facebook_comment_id of parent
    parent_internal_id: Optional[str] = None  # UUID of parent comment if known

    # Author
    author_display_name: Optional[str] = None
    author_profile_url: Optional[str] = None
    author_facebook_user_id: Optional[str] = None
    author_is_anonymous: bool = False

    # Content
    content: Optional[str] = None
    commented_at: Optional[datetime] = None
    depth: int = 0                 # 0 = top-level; 1+ = reply

    # Media attachments in comment
    media_urls: list[str] = field(default_factory=list)

    # Reply signals
    known_reply_count: Optional[int] = None
    last_reply_at: Optional[datetime] = None

    # Metadata
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    raw_payload: Optional[dict] = None


# ---------------------------------------------------------------------------
# Media job item — pushed by Browser/Comment Workers into media_queue
# ---------------------------------------------------------------------------

@dataclass
class MediaJobItem:
    """Represents a media URL to be downloaded asynchronously."""

    owner_type: str                # 'post' | 'comment'
    owner_id: str                  # UUID of post or comment
    source_url: str                # Original URL
    position: int                  # Order in content (0-indexed)
    media_type: str = "image"      # 'image' | 'video'
    post_id: Optional[str] = None  # UUID of post (for both post & comment attachments)
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    run_id: str = ""


# ---------------------------------------------------------------------------
# Sentinel — used to signal workers to shut down
# ---------------------------------------------------------------------------

class _Sentinel:
    """Poison pill: put into queue to signal consumer shutdown."""
    pass


SENTINEL = _Sentinel()
