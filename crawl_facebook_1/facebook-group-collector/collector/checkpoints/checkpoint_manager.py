"""
collector/checkpoints/checkpoint_manager.py — Checkpoint and Resume Coordinator.

Responsibilities:
- Periodically persists crawler state every checkpoint.every_seconds (default 15s)
- Persists crawler state every checkpoint.every_posts (default 20 posts)
- Immediate state persistence on shutdown / SIGTERM (< 2s)
- Loads previous checkpoint state on crawler startup with --resume
- Restores counters, last_post_id, last_post_time, and consecutive_known_posts
- Clears checkpoint upon successful run completion (COMPLETED)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from collector.config import CheckpointConfig
from collector.metrics.emitter import MetricsCounters
from collector.storage.repository import CheckpointRepo

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointManager:
    """Manages periodic, count-based, and shutdown checkpoints for a crawl run."""

    def __init__(
        self,
        checkpoint_repo: CheckpointRepo,
        group_slug: str,
        group_id: str,
        mode: str,
        run_id: str,
        config: CheckpointConfig,
        counters: Optional[MetricsCounters] = None,
    ):
        self.checkpoint_repo = checkpoint_repo
        self.group_slug = group_slug
        self.group_id = group_id
        self.mode = mode
        self.run_id = run_id
        self.config = config
        self.counters = counters or MetricsCounters()

        self.last_post_id: Optional[str] = None
        self.last_post_time: Optional[str] = None
        self.consecutive_known_posts: int = 0

        self._last_saved_posts: int = 0
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # State Recording
    # ------------------------------------------------------------------

    async def record_post(
        self,
        post_id: Optional[str] = None,
        post_time: Optional[str] = None,
        consecutive_known: int = 0,
        auto_save: bool = True,
    ) -> bool:
        """
        Record a newly processed or discovered post.
        Triggers checkpoint save if count threshold (every_posts) is exceeded.
        """
        if post_id:
            self.last_post_id = post_id
        if post_time:
            self.last_post_time = post_time
        self.consecutive_known_posts = consecutive_known

        current_posts = self.counters.posts_discovered
        if auto_save and (current_posts - self._last_saved_posts) >= self.config.every_posts:
            logger.info(
                "Checkpoint count trigger: %d posts since last checkpoint (threshold=%d)",
                current_posts - self._last_saved_posts,
                self.config.every_posts,
            )
            await self.save_now()
            return True
        return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def save_now(self, status: str = "in_progress") -> dict:
        """Immediately save the current progress snapshot to storage."""
        async with self._lock:
            snapshot = {
                "posts_discovered": self.counters.posts_discovered,
                "posts_new": self.counters.posts_new,
                "posts_skipped": self.counters.posts_skipped,
                "comments_discovered": self.counters.comments_discovered,
                "comments_new": self.counters.comments_new,
                "comments_skipped": self.counters.comments_skipped,
                "media_discovered": self.counters.media_discovered,
                "media_downloaded": self.counters.media_downloaded,
                "media_deduped": self.counters.media_deduped,
            }

            checkpoint_data = {
                "run_id": self.run_id,
                "group_slug": self.group_slug,
                "group_id": self.group_id,
                "mode": self.mode,
                "last_post_id": self.last_post_id,
                "last_post_time": self.last_post_time,
                "consecutive_known_posts": self.consecutive_known_posts,
                "progress_snapshot": snapshot,
                "status": status,
                "updated_at": _now(),
            }

            await self.checkpoint_repo.save(self.group_slug, self.mode, checkpoint_data)
            self._last_saved_posts = self.counters.posts_discovered
            logger.debug(
                "Checkpoint saved: group=%s mode=%s posts=%d last_post=%s",
                self.group_slug, self.mode, self._last_saved_posts, self.last_post_id,
            )
            return checkpoint_data

    async def load(self) -> Optional[dict]:
        """Load the latest checkpoint for this group and mode."""
        data = await self.checkpoint_repo.load(self.group_slug, self.mode)
        if data:
            self.last_post_id = data.get("last_post_id")
            self.last_post_time = data.get("last_post_time")
            self.consecutive_known_posts = data.get("consecutive_known_posts", 0)

            # Restore snapshot into counters if provided
            snapshot = data.get("progress_snapshot", {})
            if snapshot and self.counters:
                self.counters.posts_discovered = snapshot.get("posts_discovered", 0)
                self.counters.posts_new = snapshot.get("posts_new", 0)
                self.counters.posts_skipped = snapshot.get("posts_skipped", 0)
                self.counters.comments_discovered = snapshot.get("comments_discovered", 0)
                self.counters.comments_new = snapshot.get("comments_new", 0)
                self.counters.comments_skipped = snapshot.get("comments_skipped", 0)
                self.counters.media_discovered = snapshot.get("media_discovered", 0)
                self.counters.media_downloaded = snapshot.get("media_downloaded", 0)
                self.counters.media_deduped = snapshot.get("media_deduped", 0)
                self._last_saved_posts = self.counters.posts_discovered

            logger.info(
                "Restored from checkpoint: last_post=%s, consecutive_known=%d, posts_discovered=%d",
                self.last_post_id, self.consecutive_known_posts, self.counters.posts_discovered,
            )
        return data

    async def clear(self) -> None:
        """Clear existing checkpoint upon clean completion."""
        await self.checkpoint_repo.clear(self.group_slug, self.mode)
        logger.info("Cleared checkpoint for group=%s mode=%s", self.group_slug, self.mode)

    # ------------------------------------------------------------------
    # Background Periodic Loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Background loop that writes a checkpoint every checkpoint.every_seconds."""
        logger.debug(
            "CheckpointManager loop started (interval=%ds)",
            self.config.every_seconds,
        )
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(self.config.every_seconds),
                    )
                    break  # Stop signaled
                except asyncio.TimeoutError:
                    pass  # Timeout elapsed -> save checkpoint

                if not self._stop_event.is_set():
                    await self.save_now()
        except asyncio.CancelledError:
            pass
        finally:
            logger.debug("CheckpointManager background loop stopped")

    def stop(self) -> None:
        """Signal background loop to stop."""
        self._stop_event.set()
