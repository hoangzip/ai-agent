"""
collector/storage/layout.py — Folder layout for file-based storage.

Data directory structure:
    data/
    ├── groups/
    │   └── {slug}/                     ← one folder per group
    │       ├── meta.json               ← group metadata
    │       ├── posts/
    │       │   └── {post_id}.json      ← one file per post (includes content + comment refs)
    │       └── actors/
    │           └── {actor_id}.json     ← actors seen in this group
    ├── comments/
    │   └── {post_id}/
    │       └── {comment_id}.json       ← one file per comment/reply
    ├── media/
    │   ├── assets/
    │   │   └── {sha256[:2]}/{sha256[2:4]}/{sha256}.{ext}  ← downloaded files
    │   └── meta/
    │       └── {media_id}.json         ← media metadata
    ├── runs/
    │   └── {run_id}.json               ← crawl run records
    └── checkpoints/
        └── {group_slug}_{mode}.json    ← latest checkpoint per group+mode

All JSON files use UTF-8 encoding and pretty-print formatting (indent=2)
for human readability during development / debugging.

This storage is designed with the SAME data model as the PostgreSQL schema
in DATABASE_STRATEGY.md so migration later is straightforward:
  - Each JSON object maps 1:1 to a DB row
  - Unique keys (facebook_post_id, facebook_comment_id, sha256) are used
    identically for idempotency
"""
from __future__ import annotations

import re
from pathlib import Path


def slugify(text: str) -> str:
    """Convert a group URL or name to a safe folder name."""
    # Extract group ID from URL if possible
    m = re.search(r'/groups/([^/?#]+)', text)
    if m:
        text = m.group(1)
    # Remove unsafe characters
    text = re.sub(r'[^\w\-]', '_', text.lower())
    return text[:80]  # max folder name length


class StorageLayout:
    """
    Computes paths for all data artifacts.
    All paths are relative to `root_dir`.
    """

    def __init__(self, root_dir: str | Path = "data"):
        self.root = Path(root_dir)

    def slugify_group(self, text: str) -> str:
        """Convert a group URL, ID, or name to a safe folder name."""
        return slugify(text)

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def group_dir(self, group_slug: str) -> Path:
        return self.root / "groups" / group_slug

    def group_meta_path(self, group_slug: str) -> Path:
        return self.group_dir(group_slug) / "meta.json"

    def group_posts_dir(self, group_slug: str) -> Path:
        return self.group_dir(group_slug) / "posts"

    def group_actors_dir(self, group_slug: str) -> Path:
        return self.group_dir(group_slug) / "actors"

    def post_path(self, group_slug: str, post_id: str) -> Path:
        return self.group_posts_dir(group_slug) / f"{post_id}.json"

    def actor_path(self, group_slug: str, actor_id: str) -> Path:
        return self.group_actors_dir(group_slug) / f"{actor_id}.json"

    def group_images_dir(self, group_slug: str) -> Path:
        """Dedicated folder for human-inspectable photos and screenshots."""
        return self.group_dir(group_slug) / "images"

    def group_post_image_path(self, group_slug: str, post_id: str, pos: int = 0, ext: str = "jpg") -> Path:
        return self.group_images_dir(group_slug) / "posts" / f"{post_id}_{pos}.{ext}"

    def group_comment_image_path(self, group_slug: str, comment_id: str, pos: int = 0, ext: str = "jpg") -> Path:
        return self.group_images_dir(group_slug) / "comments" / f"{comment_id}_{pos}.{ext}"

    def group_cic_leads_path(self, group_slug: str) -> Path:
        """Central registry of extracted CIC customer profiles for quick inspection."""
        return self.group_dir(group_slug) / "cic_customers.json"

    # ------------------------------------------------------------------
    # Comments (outside group dir for easy cross-post access)
    # ------------------------------------------------------------------

    def comments_dir(self, post_id: str) -> Path:
        return self.root / "comments" / post_id

    def comment_path(self, post_id: str, comment_id: str) -> Path:
        return self.comments_dir(post_id) / f"{comment_id}.json"

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def media_assets_dir(self) -> Path:
        return self.root / "media" / "assets"

    def media_meta_dir(self) -> Path:
        return self.root / "media" / "meta"

    def media_file_path(self, sha256: str, ext: str = "bin") -> Path:
        """Sharded by first 4 hex chars to avoid huge flat directories."""
        shard1 = sha256[:2]
        shard2 = sha256[2:4]
        return self.media_assets_dir() / shard1 / shard2 / f"{sha256}.{ext}"

    def media_meta_path(self, media_id: str) -> Path:
        return self.media_meta_dir() / f"{media_id}.json"

    # ------------------------------------------------------------------
    # Runs & Checkpoints
    # ------------------------------------------------------------------

    def runs_dir(self) -> Path:
        return self.root / "runs"

    def run_path(self, run_id: str) -> Path:
        return self.runs_dir() / f"{run_id}.json"

    def checkpoints_dir(self) -> Path:
        return self.root / "checkpoints"

    def checkpoint_path(self, group_slug: str, mode: str) -> Path:
        return self.checkpoints_dir() / f"{group_slug}_{mode}.json"

    # ------------------------------------------------------------------
    # Indexes (in-memory lookup files)
    # ------------------------------------------------------------------

    def index_dir(self) -> Path:
        return self.root / "index"

    def post_index_path(self, group_slug: str) -> Path:
        """Maps facebook_post_id -> internal post_id for fast dedup."""
        return self.index_dir() / f"posts_{group_slug}.json"

    def comment_index_path(self, post_id: str) -> Path:
        """Maps facebook_comment_id -> internal comment_id for fast dedup."""
        return self.index_dir() / f"comments_{post_id}.json"

    def actor_index_path(self, group_slug: str) -> Path:
        """Maps profile_url -> internal actor_id for fast dedup."""
        return self.index_dir() / f"actors_{group_slug}.json"

    def media_sha256_index_path(self) -> Path:
        """Maps sha256 -> media_id for file dedup."""
        return self.index_dir() / "media_sha256.json"

    # ------------------------------------------------------------------
    # Ensure directories exist
    # ------------------------------------------------------------------

    def ensure_dirs(self, group_slug: str) -> None:
        """Create all required directories for a group crawl."""
        dirs = [
            self.group_dir(group_slug),
            self.group_posts_dir(group_slug),
            self.group_actors_dir(group_slug),
            self.group_images_dir(group_slug) / "posts",
            self.group_images_dir(group_slug) / "comments",
            self.media_assets_dir(),
            self.media_meta_dir(),
            self.runs_dir(),
            self.checkpoints_dir(),
            self.index_dir(),
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
