"""
collector/pipeline/worker.py — Base worker class and worker lifecycle management.

Provides:
- BaseWorker: abstract base with consume loop, error isolation, sentinel detection
- WorkerPool: manages a group of worker tasks with graceful shutdown

Phase 02: the concrete work is stubbed; phases 04-07 will fill in the real logic.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

from collector.pipeline.items import SENTINEL, _Sentinel
from collector.metrics.emitter import MetricsCounters

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Abstract base for all pipeline consumer workers.

    Subclasses implement `process_item(item)`.
    The consume loop handles:
      - Sentinel detection for graceful shutdown
      - Per-item error isolation (one bad item doesn't crash the worker)
      - Exponential backoff retry
      - Metrics increment
    """

    def __init__(
        self,
        name: str,
        queue: asyncio.Queue,
        counters: MetricsCounters,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max: float = 30.0,
    ):
        self.name = name
        self._queue = queue
        self._counters = counters
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._running = False
        self._items_processed = 0
        self._items_failed = 0

    @abstractmethod
    async def process_item(self, item: Any) -> None:
        """Process a single item from the queue. Raise on unrecoverable error."""

    async def run(self) -> None:
        """
        Consume loop: get item from queue, call process_item, handle errors.
        Exits cleanly when a SENTINEL is received.
        """
        self._running = True
        logger.debug("[%s] started", self.name)

        while self._running:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                logger.debug("[%s] cancelled while waiting for item", self.name)
                break

            if isinstance(item, _Sentinel):
                logger.debug("[%s] received sentinel — exiting", self.name)
                self._queue.task_done()
                break

            try:
                await self._process_with_retry(item)
                self._items_processed += 1
            except Exception as e:
                self._items_failed += 1
                self._counters.errors += 1
                logger.error(
                    "[%s] FAILED item after all retries: %s — %s",
                    self.name, type(item).__name__, e, exc_info=True,
                )
            finally:
                self._queue.task_done()

        logger.debug(
            "[%s] stopped (processed=%d, failed=%d)",
            self.name, self._items_processed, self._items_failed,
        )

    async def _process_with_retry(self, item: Any) -> None:
        """Retry with exponential backoff + jitter. Raise after max_retries."""
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                await self.process_item(item)
                return  # Success
            except NonRetryableError:
                raise  # Do not retry (e.g., DOM drift, 404)
            except Exception as e:
                last_exc = e
                self._counters.retries += 1
                if attempt < self._max_retries - 1:
                    wait = min(
                        self._backoff_base ** attempt + random.uniform(0, 1),
                        self._backoff_max,
                    )
                    logger.warning(
                        "[%s] attempt %d/%d failed: %s — retrying in %.1fs",
                        self.name, attempt + 1, self._max_retries, e, wait,
                    )
                    await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def stop(self) -> None:
        self._running = False


class NonRetryableError(Exception):
    """
    Raise this from process_item() to skip retries and mark the item as
    unrecoverable (e.g., selector not found = DOM drift, page 404).
    """


class WorkerPool:
    """
    Manages a group of worker tasks with uniform lifecycle.

    Usage:
        pool = WorkerPool()
        pool.add(worker_instance)
        await pool.start()
        # ... run ...
        await pool.stop(timeout=10)
    """

    def __init__(self):
        self._workers: list[BaseWorker] = []
        self._tasks: list[asyncio.Task] = []

    def add(self, worker: BaseWorker) -> None:
        self._workers.append(worker)

    async def start(self) -> None:
        """Launch all worker tasks concurrently."""
        for worker in self._workers:
            task = asyncio.create_task(worker.run(), name=worker.name)
            self._tasks.append(task)
        logger.info("WorkerPool: started %d workers", len(self._tasks))

    async def stop(self, timeout: float = 10.0) -> None:
        """
        Graceful shutdown:
        1. Signal all workers to stop (they will drain sentinel from queue)
        2. Wait up to `timeout` seconds for tasks to finish
        3. Cancel any remaining tasks
        """
        for worker in self._workers:
            worker.stop()

        if not self._tasks:
            return

        done, pending = await asyncio.wait(self._tasks, timeout=timeout)

        if pending:
            logger.warning(
                "WorkerPool: %d tasks did not finish within %.1fs — cancelling",
                len(pending), timeout,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        logger.info(
            "WorkerPool: stopped (done=%d, cancelled=%d)",
            len(done), len(pending),
        )
        self._tasks.clear()

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tasks if not t.done())
