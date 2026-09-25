"""
tests/unit/test_worker.py — Phase 02: Worker lifecycle tests.

Tests verify:
1. Worker exits cleanly on SENTINEL
2. Per-item errors don't crash the worker
3. Retry with backoff works (max_retries respected)
4. NonRetryableError skips retries immediately
5. WorkerPool starts/stops all workers
6. Graceful shutdown within timeout
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import SENTINEL
from collector.pipeline.worker import BaseWorker, NonRetryableError, WorkerPool


# ---------------------------------------------------------------------------
# Test concrete worker
# ---------------------------------------------------------------------------

class CountingWorker(BaseWorker):
    """A worker that counts items processed and can be configured to fail."""

    def __init__(self, queue, counters, fail_count=0, fail_with=None, **kwargs):
        super().__init__("test_worker", queue, counters, **kwargs)
        self.processed = []
        self.fail_count = fail_count
        self.fail_with = fail_with or Exception("test error")
        self._call_count = 0

    async def process_item(self, item: Any) -> None:
        self._call_count += 1
        if self.fail_count > 0:
            self.fail_count -= 1
            raise self.fail_with
        self.processed.append(item)


# ---------------------------------------------------------------------------
# Tests: sentinel exit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_exits_on_sentinel():
    """Worker must exit cleanly when SENTINEL is received."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    worker = CountingWorker(q, counters, max_retries=1, backoff_base=0.01)

    await q.put("item1")
    await q.put("item2")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=2.0)

    assert worker.processed == ["item1", "item2"]
    assert counters.errors == 0


@pytest.mark.asyncio
async def test_worker_processes_multiple_items_before_sentinel():
    """Worker should process all items before the sentinel."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    worker = CountingWorker(q, counters, max_retries=1, backoff_base=0.01)

    for i in range(5):
        await q.put(f"item{i}")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=2.0)
    assert len(worker.processed) == 5


# ---------------------------------------------------------------------------
# Tests: error isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_continues_after_item_failure():
    """One bad item must not crash the worker — next items should be processed."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    # fail_count=10 means first 10 attempts fail (3 retries = 3 attempts per item)
    # With max_retries=1, first item fails after 1 attempt, then continues
    worker = CountingWorker(q, counters, fail_count=1, max_retries=1, backoff_base=0.01)

    await q.put("bad_item")
    await q.put("good_item")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=5.0)

    assert "good_item" in worker.processed
    assert counters.errors == 1


@pytest.mark.asyncio
async def test_error_counter_incremented():
    """errors counter must be incremented when item fails all retries."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    # fail_count=999 ensures all attempts fail
    worker = CountingWorker(q, counters, fail_count=999, max_retries=2, backoff_base=0.01)

    await q.put("always_fails")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=5.0)

    assert counters.errors == 1
    assert counters.retries >= 1  # At least one retry before giving up


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_counter_incremented():
    """retry counter must be incremented on each failed attempt."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    # fail 2 times, then succeed
    worker = CountingWorker(q, counters, fail_count=2, max_retries=3, backoff_base=0.01)

    await q.put("eventually_succeeds")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=5.0)

    assert counters.retries == 2
    assert counters.errors == 0
    assert "eventually_succeeds" in worker.processed


# ---------------------------------------------------------------------------
# Tests: NonRetryableError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_retryable_error_skips_retries():
    """NonRetryableError must not be retried — error counted, no retries."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()
    worker = CountingWorker(
        q, counters,
        fail_count=999,
        fail_with=NonRetryableError("DOM drift"),
        max_retries=3,
        backoff_base=0.01,
    )

    await q.put("dom_drift_post")
    await q.put(SENTINEL)

    await asyncio.wait_for(worker.run(), timeout=2.0)

    assert counters.errors == 1
    assert counters.retries == 0  # No retries for NonRetryableError


# ---------------------------------------------------------------------------
# Tests: WorkerPool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_pool_starts_and_stops():
    """WorkerPool must start all workers and stop them gracefully."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()

    pool = WorkerPool()
    workers = [
        CountingWorker(q, counters, max_retries=1, backoff_base=0.01)
        for i in range(3)
    ]
    for w in workers:
        pool.add(w)

    await pool.start()
    assert pool.active_count == 3

    # Send sentinels to unblock workers
    for _ in range(3):
        await q.put(SENTINEL)

    await pool.stop(timeout=5.0)
    assert pool.active_count == 0


@pytest.mark.asyncio
async def test_worker_pool_shutdown_within_timeout():
    """WorkerPool.stop() must complete within timeout even if workers are slow."""
    q = asyncio.Queue(maxsize=10)
    counters = MetricsCounters()

    class SlowWorker(BaseWorker):
        async def process_item(self, item):
            await asyncio.sleep(100)  # Very slow

    pool = WorkerPool()
    w = SlowWorker("slow", q, counters)
    pool.add(w)

    await pool.start()

    # Don't send sentinel — worker is blocked on slow process_item
    # WorkerPool.stop() should cancel it within timeout
    import time
    start = time.monotonic()
    await pool.stop(timeout=1.0)
    elapsed = time.monotonic() - start

    assert elapsed < 3.0, f"stop() took too long: {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_worker_pool_processes_items_across_workers():
    """Items distributed across multiple workers should all be processed."""
    q = asyncio.Queue(maxsize=100)
    counters = MetricsCounters()

    all_processed = []

    class CollectingWorker(BaseWorker):
        async def process_item(self, item):
            all_processed.append(item)

    pool = WorkerPool()
    for i in range(3):
        pool.add(CollectingWorker(f"collector_{i}", q, counters))

    await pool.start()

    # Push 30 items
    for i in range(30):
        await q.put(f"item_{i}")

    # Send 3 sentinels (one per worker)
    for _ in range(3):
        await q.put(SENTINEL)

    await pool.stop(timeout=5.0)

    assert len(all_processed) == 30
