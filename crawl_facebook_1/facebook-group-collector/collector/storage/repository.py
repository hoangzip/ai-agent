"""
collector/storage/repository.py — High-level data access layer.

Provides UPSERT semantics identical to the PostgreSQL spec:
  - Idempotency by facebook_*_id as primary key, fallback to URL/dedupe_key
  - Returns (record, is_new) for dedup tracking
  - Batch writes via list of items

Each entity follows the same field names as DATA_MODEL.md so migration
to PostgreSQL is a matter of replacing these calls with SQL UPSERT.

Entities:
  GroupRepo   → data/groups/{slug}/meta.json
  ActorRepo   → data/groups/{slug}/actors/{actor_id}.json
  PostRepo    → data/groups/{slug}/posts/{post_id}.json
  CommentRepo → data/comments/{post_id}/{comment_id}.json
  MediaRepo   → data/media/meta/{media_id}.json
  RunRepo     → data/runs/{run_id}.json
  CheckpointRepo → data/checkpoints/{group_slug}_{mode}.json
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from collector.storage.json_store import (
    file_exists,
    list_json_files,
    read_index,
    read_json,
    update_index,
    write_json,
)
from collector.storage.layout import StorageLayout

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# GroupRepo
# ---------------------------------------------------------------------------

class GroupRepo:
    def __init__(self, layout: StorageLayout):
        self._layout = layout

    async def upsert(self, data: dict) -> tuple[dict, bool]:
        """
        Upsert a group record.
        Primary key: facebook_group_id, fallback: group_url slug.
        Returns (record, is_new).
        """
        slug = data.get("slug") or self._layout.slugify_group(
            data.get("facebook_group_id") or data.get("group_url", "unknown")
        )
        self._layout.ensure_dirs(slug)
        path = self._layout.group_meta_path(slug)
        existing = await read_json(path)

        if existing:
            existing["last_seen_at"] = _now()
            existing["updated_at"] = _now()
            # Update mutable fields
            for field in ("group_name", "description", "member_count"):
                if data.get(field) is not None:
                    existing[field] = data[field]
            await write_json(path, existing)
            return existing, False
        else:
            record = {
                "id": _new_id(),
                "slug": slug,
                "facebook_group_id": data.get("facebook_group_id"),
                "group_name": data.get("group_name", ""),
                "group_url": data.get("group_url", ""),
                "description": data.get("description"),
                "member_count": data.get("member_count"),
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "created_at": _now(),
                "updated_at": _now(),
            }
            await write_json(path, record)
            return record, True

    async def get_by_slug(self, slug: str) -> Optional[dict]:
        return await read_json(self._layout.group_meta_path(slug))


# ---------------------------------------------------------------------------
# ActorRepo
# ---------------------------------------------------------------------------

class ActorRepo:
    def __init__(self, layout: StorageLayout, group_slug: str):
        self._layout = layout
        self._slug = group_slug
        self._index_path = layout.actor_index_path(group_slug)

    async def upsert(self, data: dict) -> tuple[dict, bool]:
        """
        Upsert an actor.
        Primary key: facebook_user_id → fallback: profile_url → username.
        Returns (record, is_new).
        """
        index = await read_index(self._index_path)

        is_anonymous = bool(data.get("is_anonymous", False))
        anonymous_scope_post_id = data.get("anonymous_scope_post_id")
        alias = (data.get("display_name") or "anonymous").strip()
        anon_key = f"anon:{anonymous_scope_post_id}:{alias}" if anonymous_scope_post_id else f"anon:{_new_id()}"

        # Look up existing actor
        actor_id = None
        if is_anonymous:
            # Anonymous users are scoped to post to prevent cross-post collision
            actor_id = index.get(anon_key)
        else:
            if data.get("facebook_user_id"):
                actor_id = index.get(f"fb_uid:{data['facebook_user_id']}")
            if not actor_id and data.get("profile_url"):
                actor_id = index.get(f"profile_url:{data['profile_url']}")

        path = self._layout.actor_path(self._slug, actor_id) if actor_id else None

        if actor_id and path and path.exists():
            existing = await read_json(path)
            existing["last_seen_at"] = _now()
            existing["updated_at"] = _now()
            for field in ("display_name", "username", "profile_url", "facebook_user_id"):
                if data.get(field) is not None:
                    existing[field] = data[field]
            existing["anonymous_scope_post_id"] = anonymous_scope_post_id if is_anonymous else None
            await write_json(path, existing)
            return existing, False
        else:
            actor_id = _new_id()
            record = {
                "id": actor_id,
                "facebook_user_id": data.get("facebook_user_id"),
                "username": data.get("username"),
                "display_name": data.get("display_name"),
                "profile_url": data.get("profile_url"),
                "is_anonymous": is_anonymous,
                "anonymous_scope_post_id": anonymous_scope_post_id if is_anonymous else None,
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "created_at": _now(),
                "updated_at": _now(),
            }
            await write_json(self._layout.actor_path(self._slug, actor_id), record)
            # Update index with all available keys
            idx_updates: dict[str, str] = {}
            if is_anonymous:
                idx_updates[anon_key] = actor_id
            else:
                if data.get("facebook_user_id"):
                    idx_updates[f"fb_uid:{data['facebook_user_id']}"] = actor_id
                if data.get("profile_url"):
                    idx_updates[f"profile_url:{data['profile_url']}"] = actor_id
            if idx_updates:
                await update_index(self._index_path, idx_updates)
            return record, True

    async def get(self, actor_id: str) -> Optional[dict]:
        return await read_json(self._layout.actor_path(self._slug, actor_id))

    async def get_by_fb_id(self, facebook_user_id: str) -> Optional[dict]:
        index = await read_index(self._index_path)
        actor_id = index.get(f"fb_uid:{facebook_user_id}")
        if not actor_id:
            return None
        return await self.get(actor_id)


# ---------------------------------------------------------------------------
# PostRepo
# ---------------------------------------------------------------------------

class PostRepo:
    def __init__(self, layout: StorageLayout, group_slug: str):
        self._layout = layout
        self._slug = group_slug
        self._index_path = layout.post_index_path(group_slug)

    async def upsert(self, data: dict) -> tuple[dict, bool]:
        """
        Upsert a post.
        Primary key: facebook_post_id → fallback: post_url.
        Returns (record, is_new).
        """
        index = await read_index(self._index_path)

        post_id = None
        if data.get("facebook_post_id"):
            post_id = index.get(f"fb_pid:{data['facebook_post_id']}")
        if not post_id and data.get("post_url"):
            post_id = index.get(f"url:{data['post_url']}")

        path = self._layout.post_path(self._slug, post_id) if post_id else None

        if post_id and path and path.exists():
            existing = await read_json(path)
            existing["last_seen_at"] = _now()
            existing["updated_at"] = _now()
            # Update observable fields
            for field in ("source_comment_count", "content", "title", "author_id", "author_display_name", "author_is_anonymous"):
                if data.get(field) is not None:
                    existing[field] = data[field]
            if data.get("crawl_status"):
                existing["crawl_status"] = data["crawl_status"]
            if data.get("last_crawled_at"):
                existing["last_crawled_at"] = data["last_crawled_at"]
            if data.get("last_comments_crawled_at"):
                existing["last_comments_crawled_at"] = data["last_comments_crawled_at"]
            if data.get("comments_complete") is not None:
                existing["comments_complete"] = data["comments_complete"]
            if data.get("next_check_at"):
                existing["next_check_at"] = data["next_check_at"]
            if data.get("known_comment_count") is not None:
                existing["known_comment_count"] = data["known_comment_count"]
            await write_json(path, existing)
            return existing, False
        else:
            post_id = _new_id()
            record = {
                "id": post_id,
                "facebook_post_id": data.get("facebook_post_id"),
                "group_id": data.get("group_id"),
                "group_slug": self._slug,
                "author_id": data.get("author_id"),
                "author_display_name": data.get("author_display_name"),
                "author_is_anonymous": bool(data.get("author_is_anonymous", False)),
                "post_url": data.get("post_url"),
                "title": data.get("title"),
                "title_source": data.get("title_source"),
                "content": data.get("content"),
                "posted_at": data.get("posted_at"),
                "content_hash": data.get("content_hash"),
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "last_crawled_at": data.get("last_crawled_at"),
                "last_comments_crawled_at": None,
                "known_comment_count": 0,
                "source_comment_count": data.get("source_comment_count"),
                "last_comment_at": None,
                "last_seen_comment_id": None,
                "comments_complete": False,
                "next_check_at": data.get("next_check_at"),
                "crawl_status": data.get("crawl_status", "DISCOVERED"),
                "media_ids": [],
                "raw_payload": data.get("raw_payload"),
                "created_at": _now(),
                "updated_at": _now(),
            }
            await write_json(self._layout.post_path(self._slug, post_id), record)
            # Update index
            idx_updates: dict[str, str] = {}
            if data.get("facebook_post_id"):
                idx_updates[f"fb_pid:{data['facebook_post_id']}"] = post_id
            if data.get("post_url"):
                idx_updates[f"url:{data['post_url']}"] = post_id
            if idx_updates:
                await update_index(self._index_path, idx_updates)
            return record, True

    async def get(self, post_id: str) -> Optional[dict]:
        return await read_json(self._layout.post_path(self._slug, post_id))

    async def get_by_facebook_id(self, facebook_post_id: str) -> Optional[dict]:
        index = await read_index(self._index_path)
        post_id = index.get(f"fb_pid:{facebook_post_id}")
        if not post_id:
            return None
        return await self.get(post_id)

    async def get_by_url(self, post_url: str) -> Optional[dict]:
        index = await read_index(self._index_path)
        post_id = index.get(f"url:{post_url}")
        if not post_id:
            return None
        return await self.get(post_id)

    async def list_all(self) -> list[dict]:
        """Return all post records for this group."""
        posts_dir = self._layout.group_posts_dir(self._slug)
        files = await list_json_files(posts_dir)
        records = []
        for f in files:
            data = await read_json(f)
            if data:
                records.append(data)
        return records

    async def update(self, post_id: str, updates: dict) -> Optional[dict]:
        """Update arbitrary fields on a post record."""
        path = self._layout.post_path(self._slug, post_id)
        data = await read_json(path)
        if data:
            data.update(updates)
            data["updated_at"] = _now()
            await write_json(path, data)
            return data
        return None

    async def update_status(self, post_id: str, status: str) -> None:
        await self.update(post_id, {"crawl_status": status})

    async def increment_comment_count(self, post_id: str, delta: int = 1) -> None:
        path = self._layout.post_path(self._slug, post_id)
        data = await read_json(path)
        if data:
            data["known_comment_count"] = data.get("known_comment_count", 0) + delta
            data["updated_at"] = _now()
            await write_json(path, data)

    async def exists(self, facebook_post_id: str | None = None, post_url: str | None = None) -> bool:
        index = await read_index(self._index_path)
        if facebook_post_id and f"fb_pid:{facebook_post_id}" in index:
            return True
        if post_url and f"url:{post_url}" in index:
            return True
        return False


# ---------------------------------------------------------------------------
# CommentRepo
# ---------------------------------------------------------------------------

def _make_dedupe_key(post_id: str, profile_url: str | None, content: str | None, commented_at: str | None) -> str:
    """Fallback dedup key when facebook_comment_id is unavailable."""
    raw = f"{post_id}|{profile_url or ''}|{(content or '').strip()[:200]}|{commented_at or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class CommentRepo:
    def __init__(self, layout: StorageLayout, post_id: str):
        self._layout = layout
        self._post_id = post_id
        self._index_path = layout.comment_index_path(post_id)

    async def upsert(self, data: dict) -> tuple[dict, bool]:
        """
        Upsert a comment.
        Primary key: facebook_comment_id → fallback: dedupe_key.

        IMPORTANT: dedupe_key is an internal fallback hash.
        It is NEVER stored in facebook_comment_id.
        """
        index = await read_index(self._index_path)

        comment_id = None
        if data.get("facebook_comment_id"):
            comment_id = index.get(f"fb_cid:{data['facebook_comment_id']}")

        # Compute dedupe_key for fallback (even if not needed, store it)
        dedupe_key = data.get("dedupe_key") or _make_dedupe_key(
            self._post_id,
            data.get("author_profile_url"),
            data.get("content"),
            data.get("commented_at"),
        )

        if not comment_id:
            comment_id = index.get(f"dedupe:{dedupe_key}")

        path = self._layout.comment_path(self._post_id, comment_id) if comment_id else None

        if comment_id and path and path.exists():
            existing = await read_json(path)
            existing["last_seen_at"] = _now()
            existing["updated_at"] = _now()
            if data.get("known_reply_count") is not None:
                existing["known_reply_count"] = data["known_reply_count"]
            await write_json(path, existing)
            return existing, False
        else:
            comment_id = _new_id()
            record = {
                "id": comment_id,
                "facebook_comment_id": data.get("facebook_comment_id"),  # nullable, never set to dedupe_key
                "post_id": self._post_id,
                "parent_comment_id": data.get("parent_comment_id"),
                "parent_internal_id": data.get("parent_internal_id"),
                "author_id": data.get("author_id"),
                "author_display_name": data.get("author_display_name"),
                "author_profile_url": data.get("author_profile_url"),
                "author_is_anonymous": data.get("author_is_anonymous", False),
                "comment_url": data.get("comment_url"),
                "content": data.get("content"),
                "commented_at": data.get("commented_at"),
                "depth": data.get("depth", 0),
                "media_urls": data.get("media_urls", []),
                "media_ids": data.get("media_ids", []),
                "dedupe_key": dedupe_key,
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "known_reply_count": data.get("known_reply_count"),
                "last_reply_at": data.get("last_reply_at"),
                "raw_payload": data.get("raw_payload"),
                "created_at": _now(),
                "updated_at": _now(),
            }
            await write_json(self._layout.comment_path(self._post_id, comment_id), record)

            # Update index
            idx_updates: dict[str, str] = {}
            if data.get("facebook_comment_id"):
                idx_updates[f"fb_cid:{data['facebook_comment_id']}"] = comment_id
            idx_updates[f"dedupe:{dedupe_key}"] = comment_id
            await update_index(self._index_path, idx_updates)

            return record, True

    async def list_all(self, depth: int | None = None) -> list[dict]:
        """List all comments for this post, optionally filtered by depth."""
        files = await list_json_files(self._layout.comments_dir(self._post_id))
        records = []
        for f in files:
            data = await read_json(f)
            if data:
                if depth is None or data.get("depth") == depth:
                    records.append(data)
        return records

    async def count(self) -> int:
        return len(await list_json_files(self._layout.comments_dir(self._post_id)))

    async def get(self, comment_id: str) -> Optional[dict]:
        path = self._layout.comment_path(self._post_id, comment_id)
        if path.exists():
            return await read_json(path)
        return None

    async def exists(self, facebook_comment_id: str | None = None, dedupe_key: str | None = None) -> bool:
        """Check if a comment already exists in storage."""
        index = await read_index(self._index_path)
        if facebook_comment_id and f"fb_cid:{facebook_comment_id}" in index:
            return True
        if dedupe_key and f"dedupe:{dedupe_key}" in index:
            return True
        return False


# ---------------------------------------------------------------------------
# MediaRepo
# ---------------------------------------------------------------------------

class MediaRepo:
    def __init__(self, layout: StorageLayout):
        self._layout = layout
        self._sha256_index_path = layout.media_sha256_index_path()

    async def upsert_by_url(self, data: dict) -> tuple[dict, bool]:
        """
        Create a pending media record (before download).
        Key: source_url (SHA-256 not yet known).
        """
        media_id = _new_id()
        record = {
            "id": media_id,
            "media_type": data.get("media_type", "image"),
            "source_url": data["source_url"],
            "owner_type": data.get("owner_type"),
            "owner_id": data.get("owner_id"),
            "position": data.get("position", 0),
            "storage_uri": None,
            "sha256": None,
            "mime_type": None,
            "file_size": None,
            "width": None,
            "height": None,
            "download_status": "pending",
            "ocr_status": "pending",
            "ocr_text": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await write_json(self._layout.media_meta_path(media_id), record)
        return record, True

    async def mark_downloaded(
        self,
        media_id: str,
        sha256: str,
        storage_uri: str,
        mime_type: str | None = None,
        file_size: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Optional[str]:
        """
        After download: set sha256, storage_uri, download_status=downloaded.
        Returns existing media_id if sha256 already exists (dedup), else None.
        """
        # Check SHA-256 dedup
        sha256_index = await read_index(self._sha256_index_path)
        if sha256 in sha256_index:
            existing_id = sha256_index[sha256]
            logger.debug("Media SHA-256 dedup: %s already exists as %s", sha256[:16], existing_id)
            return existing_id  # caller should link to this existing asset

        path = self._layout.media_meta_path(media_id)
        data = await read_json(path)
        if not data:
            return None

        data.update({
            "sha256": sha256,
            "storage_uri": storage_uri,
            "mime_type": mime_type,
            "file_size": file_size,
            "width": width,
            "height": height,
            "download_status": "downloaded",
            "ocr_status": "pending",
            "updated_at": _now(),
        })
        await write_json(path, data)
        await update_index(self._sha256_index_path, {sha256: media_id})
        return None  # no dedup, newly stored

    async def mark_error(self, media_id: str, error: str) -> None:
        path = self._layout.media_meta_path(media_id)
        data = await read_json(path)
        if data:
            data["download_status"] = "error"
            data["last_error"] = error
            data["updated_at"] = _now()
            await write_json(path, data)

    async def update_cic_data(self, media_id: str, cic_data: dict) -> None:
        """Record structured CIC extraction data and mark OCR status completed."""
        path = self._layout.media_meta_path(media_id)
        data = await read_json(path)
        if data:
            data["cic_data"] = cic_data
            data["ocr_status"] = "completed"
            data["updated_at"] = _now()
            await write_json(path, data)

    async def list_pending(self) -> list[dict]:
        """List all media records with download_status=pending."""
        meta_dir = self._layout.media_meta_dir()
        files = await list_json_files(meta_dir)
        pending = []
        for f in files:
            data = await read_json(f)
            if data and data.get("download_status") == "pending":
                pending.append(data)
        return pending


# ---------------------------------------------------------------------------
# RunRepo
# ---------------------------------------------------------------------------

class RunRepo:
    def __init__(self, layout: StorageLayout):
        self._layout = layout

    async def create(self, run_id: str, group_slug: str, group_id: str, mode: str) -> dict:
        record = {
            "id": run_id,
            "group_id": group_id,
            "group_slug": group_slug,
            "mode": mode,
            "started_at": _now(),
            "finished_at": None,
            "status": "running",
            "posts_found": 0,
            "posts_new": 0,
            "comments_found": 0,
            "comments_new": 0,
            "media_found": 0,
            "media_downloaded": 0,
            "error_message": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._layout.runs_dir().mkdir(parents=True, exist_ok=True)
        await write_json(self._layout.run_path(run_id), record)
        return record

    async def update(self, run_id: str, updates: dict) -> None:
        path = self._layout.run_path(run_id)
        data = await read_json(path)
        if data:
            data.update(updates)
            data["updated_at"] = _now()
            await write_json(path, data)

    async def finish(self, run_id: str, status: str, error: str | None = None) -> None:
        await self.update(run_id, {
            "status": status,
            "finished_at": _now(),
            "error_message": error,
        })

    async def get(self, run_id: str) -> Optional[dict]:
        return await read_json(self._layout.run_path(run_id))


# ---------------------------------------------------------------------------
# CheckpointRepo
# ---------------------------------------------------------------------------

class CheckpointRepo:
    def __init__(self, layout: StorageLayout):
        self._layout = layout

    async def save(self, group_slug: str, mode: str, checkpoint: dict) -> None:
        self._layout.checkpoints_dir().mkdir(parents=True, exist_ok=True)
        path = self._layout.checkpoint_path(group_slug, mode)
        await write_json(path, {
            **checkpoint,
            "updated_at": _now(),
        })
        logger.debug("Checkpoint saved: group=%s mode=%s", group_slug, mode)

    async def load(self, group_slug: str, mode: str) -> Optional[dict]:
        path = self._layout.checkpoint_path(group_slug, mode)
        data = await read_json(path)
        if data:
            logger.info("Checkpoint loaded: group=%s mode=%s last_post=%s",
                        group_slug, mode, data.get("last_post_id", "none"))
        return data

    async def clear(self, group_slug: str, mode: str) -> None:
        path = self._layout.checkpoint_path(group_slug, mode)
        if path.exists():
            path.unlink()
            logger.info("Checkpoint cleared: group=%s mode=%s", group_slug, mode)
