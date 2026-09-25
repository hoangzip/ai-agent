"""
collector/metrics/emitter.py — Structured metrics emitter.

No external dashboard in MVP. Emits structured log lines to stdout
every N seconds showing throughput, queue depths, errors, and memory.

Output format (human-readable):
    [METRICS] posts_discovered=100 posts_new=42 posts_per_sec=3.8 ...

All counters are thread-safe via asyncio (single event loop).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import psutil

logger = logging.getLogger(__name__)


@dataclass
class MetricsCounters:
    """Mutable counters incremented by workers during a crawl run."""
    # Posts
    posts_discovered: int = 0
    posts_new: int = 0
    posts_skipped: int = 0
    posts_refreshed: int = 0

    # Comments
    comments_discovered: int = 0
    comments_new: int = 0
    comments_skipped: int = 0

    # Media
    media_discovered: int = 0
    media_downloaded: int = 0
    media_deduped: int = 0

    # Errors & retries
    errors: int = 0
    retries: int = 0
    partial_posts: int = 0
    failed_posts: int = 0

    # Timing
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    def elapsed_sec(self) -> float:
        return time.monotonic() - self._start_time

    def elapsed_str(self) -> str:
        secs = int(self.elapsed_sec())
        h, remainder = divmod(secs, 3600)
        m, s = divmod(remainder, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def posts_per_sec(self) -> float:
        elapsed = self.elapsed_sec()
        if elapsed < 1:
            return 0.0
        return round(self.posts_discovered / elapsed, 1)

    def comments_per_sec(self) -> float:
        elapsed = self.elapsed_sec()
        if elapsed < 1:
            return 0.0
        return round(self.comments_discovered / elapsed, 1)

    def media_per_sec(self) -> float:
        elapsed = self.elapsed_sec()
        if elapsed < 1:
            return 0.0
        return round(self.media_downloaded / elapsed, 1)

    def to_dict(self, queue_snapshots: list[dict] | None = None) -> dict:
        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)

        d = {
            "posts_discovered": self.posts_discovered,
            "posts_new": self.posts_new,
            "posts_skipped": self.posts_skipped,
            "posts_refreshed": self.posts_refreshed,
            "posts_per_sec": self.posts_per_sec(),
            "comments_discovered": self.comments_discovered,
            "comments_new": self.comments_new,
            "comments_per_sec": self.comments_per_sec(),
            "media_discovered": self.media_discovered,
            "media_downloaded": self.media_downloaded,
            "media_per_sec": self.media_per_sec(),
            "errors": self.errors,
            "retries": self.retries,
            "partial_posts": self.partial_posts,
            "failed_posts": self.failed_posts,
            "memory_mb": mem_mb,
            "elapsed": self.elapsed_str(),
        }
        if queue_snapshots:
            for snap in queue_snapshots:
                name = snap["name"]
                d[f"{name}_depth"] = snap["size"]
                d[f"{name}_pct"] = snap["fill_pct"]
        return d

    def log_summary(self, queue_snapshots: list[dict] | None = None) -> None:
        """Emit a human-readable metrics line to the log."""
        d = self.to_dict(queue_snapshots)

        queue_str = ""
        if queue_snapshots:
            parts = []
            for snap in queue_snapshots:
                parts.append(f"{snap['name']}={snap['size']}/{snap['maxsize']}({snap['fill_pct']}%)")
            queue_str = " | ".join(parts)

        logger.info(
            "[METRICS] "
            "posts=%d(new=%d, %.1f/s) "
            "comments=%d(new=%d, %.1f/s) "
            "media=%d(dl=%d, %.1f/s) "
            "errors=%d retries=%d mem=%sMB elapsed=%s"
            "%s",
            d["posts_discovered"], d["posts_new"], d["posts_per_sec"],
            d["comments_discovered"], d["comments_new"], d["comments_per_sec"],
            d["media_discovered"], d["media_downloaded"], d["media_per_sec"],
            d["errors"], d["retries"], d["memory_mb"], d["elapsed"],
            f" | queues: {queue_str}" if queue_str else "",
        )

        # Warn on high error rate
        total = self.posts_discovered + self.comments_discovered
        if total > 100 and self.errors / total > 0.05:
            logger.warning(
                "[METRICS] ERROR RATE HIGH: %d errors / %d items (%.1f%%)",
                self.errors, total, self.errors / total * 100,
            )

        # Warn on memory
        if d["memory_mb"] > 3000:
            logger.warning("[METRICS] MEMORY HIGH: %.1f MB — possible leak", d["memory_mb"])


class MetricsEmitter:
    """
    Background task that periodically calls MetricsCounters.log_summary().
    """

    def __init__(
        self,
        counters: MetricsCounters,
        emit_every_sec: int = 10,
        queue_snapshot_fn: Callable[[], list[dict]] | None = None,
    ):
        self._counters = counters
        self._interval = emit_every_sec
        self._snapshot_fn = queue_snapshot_fn
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.debug("MetricsEmitter started (interval=%ds)", self._interval)
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                snapshots = self._snapshot_fn() if self._snapshot_fn else None
                self._counters.log_summary(snapshots)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("MetricsEmitter error: %s", e)
        logger.debug("MetricsEmitter stopped")

    def stop(self) -> None:
        self._running = False

    def emit_now(self) -> None:
        """Emit a metrics snapshot immediately (e.g., on shutdown)."""
        snapshots = self._snapshot_fn() if self._snapshot_fn else None
        self._counters.log_summary(snapshots)
