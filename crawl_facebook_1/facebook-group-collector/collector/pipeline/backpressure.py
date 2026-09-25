"""
collector/pipeline/backpressure.py — Backpressure monitoring.

The primary backpressure mechanism is simply asyncio.Queue(maxsize=N):
producers block on `await queue.put()` when the queue is full.

This module provides:
1. A monitoring helper that WARNS when queues are consistently full.
2. An optional explicit pause/resume gate for producers that need
   more control than the implicit asyncio.Queue backpressure.

In Phase 02, we only need the monitoring helper.
The ProducerGate is available for Phase 04 browser producer use.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class BackpressureMonitor:
    """
    Monitors queue depths and logs warnings when queues are consistently full.
    Should be run as a background task alongside the pipeline.
    """

    def __init__(
        self,
        snapshot_fn: Callable[[], list[dict]],
        check_interval_sec: float = 5.0,
        warn_threshold_pct: float = 80.0,
        warn_after_consecutive: int = 3,
    ):
        """
        Args:
            snapshot_fn: Returns list of queue snapshots (from Queues.snapshot()).
            check_interval_sec: How often to check queue depths.
            warn_threshold_pct: Log WARNING if queue is over this % full.
            warn_after_consecutive: Only warn after N consecutive checks over threshold.
        """
        self._snapshot_fn = snapshot_fn
        self._interval = check_interval_sec
        self._threshold = warn_threshold_pct
        self._warn_after = warn_after_consecutive
        self._consecutive_counts: dict[str, int] = {}
        self._running = False
        self.gate = ProducerGate()

    async def run(self) -> None:
        """Run the backpressure monitor loop until stop() is called."""
        self._running = True
        logger.debug("BackpressureMonitor started (interval=%.1fs)", self._interval)

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                self._check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("BackpressureMonitor error: %s", e)

        logger.debug("BackpressureMonitor stopped")

    def stop(self) -> None:
        self._running = False

    def _check(self) -> None:
        snapshots = self._snapshot_fn()
        any_congested = False
        for snap in snapshots:
            name = snap["name"]
            pct = snap["fill_pct"]

            if pct >= self._threshold:
                any_congested = True
                self._consecutive_counts[name] = self._consecutive_counts.get(name, 0) + 1
                if self._consecutive_counts[name] >= self._warn_after:
                    logger.warning(
                        "BACKPRESSURE: %s is %.1f%% full (%d/%d) — "
                        "downstream may be bottleneck",
                        name, pct, snap["size"], snap["maxsize"],
                    )
                    self.gate.close()
            else:
                if self._consecutive_counts.get(name, 0) >= self._warn_after:
                    logger.info("BACKPRESSURE resolved: %s is now %.1f%% full", name, pct)
                self._consecutive_counts[name] = 0

        if not any_congested and not self.gate.is_open:
            self.gate.open()


class ProducerGate:
    """
    An explicit pause/resume gate for producers.

    While the implicit asyncio.Queue backpressure is sufficient for most cases,
    this gate allows the browser producer to implement a "soft pause" —
    stopping the scroll loop without blocking the event loop.

    Usage:
        gate = ProducerGate()

        # In producer:
        async for item in scroll_feed():
            await gate.wait()  # blocks if gate is closed
            await queue.put(item)

        # From controller:
        gate.close()   # producer pauses at next iteration
        gate.open()    # producer resumes
    """

    def __init__(self):
        self._event = asyncio.Event()
        self._event.set()  # Open by default
        self._paused = False

    def close(self) -> None:
        """Pause the producer."""
        if not self._paused:
            self._paused = True
            self._event.clear()
            logger.debug("ProducerGate: closed (producer will pause)")

    def open(self) -> None:
        """Resume the producer."""
        if self._paused:
            self._paused = False
            self._event.set()
            logger.debug("ProducerGate: opened (producer resuming)")

    async def wait(self) -> None:
        """Await this to pause when gate is closed."""
        await self._event.wait()

    @property
    def is_open(self) -> bool:
        return not self._paused
