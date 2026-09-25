"""
collector/pipeline/queues.py — Bounded asyncio.Queue wrappers with metrics.

Queues are bounded (maxsize enforced) to provide natural backpressure.
When a queue is full, the producer's await queue.put() blocks, which
naturally slows the producer without extra code.

Usage:
    queues = Queues(config.queues)
    await queues.post_queue.put(item)    # blocks when full
    item = await queues.post_queue.get()
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from collector.config import QueueConfig

logger = logging.getLogger(__name__)


@dataclass
class QueueStats:
    name: str
    queue: asyncio.Queue

    @property
    def size(self) -> int:
        return self.queue.qsize()

    @property
    def maxsize(self) -> int:
        return self.queue.maxsize

    @property
    def fill_pct(self) -> float:
        if self.maxsize == 0:
            return 0.0
        return (self.size / self.maxsize) * 100.0

    @property
    def is_nearly_full(self) -> bool:
        return self.fill_pct >= 80.0

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "size": self.size,
            "maxsize": self.maxsize,
            "fill_pct": round(self.fill_pct, 1),
            "nearly_full": self.is_nearly_full,
        }


class Queues:
    """Container for all bounded pipeline queues."""

    def __init__(self, config: QueueConfig):
        self.post_queue: asyncio.Queue = asyncio.Queue(maxsize=config.posts)
        self.comment_job_queue: asyncio.Queue = asyncio.Queue(maxsize=config.posts)
        self.comment_queue: asyncio.Queue = asyncio.Queue(maxsize=config.comments)
        self.media_queue: asyncio.Queue = asyncio.Queue(maxsize=config.media)

        self._stats = [
            QueueStats("post_queue", self.post_queue),
            QueueStats("comment_job_queue", self.comment_job_queue),
            QueueStats("comment_queue", self.comment_queue),
            QueueStats("media_queue", self.media_queue),
        ]

    def snapshot(self) -> list[dict]:
        """Return current queue depths for metrics emission."""
        return [s.snapshot() for s in self._stats]

    def any_nearly_full(self) -> bool:
        return any(s.is_nearly_full for s in self._stats)

    async def drain_all(self, num_sentinels_per_queue: dict[asyncio.Queue, int]) -> None:
        """
        Put sentinel values into each queue to signal workers to exit.
        Call this during graceful shutdown after the producer has stopped.

        Args:
            num_sentinels_per_queue: {queue: number_of_worker_tasks_consuming_it}
        """
        from collector.pipeline.items import SENTINEL
        for queue, count in num_sentinels_per_queue.items():
            for _ in range(count):
                await queue.put(SENTINEL)
            logger.debug("Sent %d sentinels to queue (size=%d)", count, queue.qsize())
