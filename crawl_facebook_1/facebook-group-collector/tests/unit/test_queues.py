"""
tests/unit/test_queues.py — Phase 02: Bounded queue tests.

Tests verify:
1. Queue blocks producer when full (backpressure)
2. Sentinel drain signals consumers correctly
3. Queue stats (fill_pct, is_nearly_full) are accurate
"""
from __future__ import annotations

import asyncio

import pytest

from collector.config import QueueConfig
from collector.pipeline.items import SENTINEL, _Sentinel
from collector.pipeline.queues import Queues, QueueStats


# ---------------------------------------------------------------------------
# QueueStats tests
# ---------------------------------------------------------------------------

class TestQueueStats:
    def test_fill_pct_empty(self):
        q = asyncio.Queue(maxsize=100)
        stats = QueueStats("test", q)
        assert stats.fill_pct == 0.0
        assert not stats.is_nearly_full

    def test_fill_pct_calculation(self):
        q = asyncio.Queue(maxsize=100)
        stats = QueueStats("test", q)
        # Simulate 80 items
        for _ in range(80):
            q.put_nowait("item")
        assert stats.fill_pct == 80.0
        assert stats.is_nearly_full  # 80% == threshold

    def test_fill_pct_over_threshold(self):
        q = asyncio.Queue(maxsize=100)
        stats = QueueStats("test", q)
        for _ in range(90):
            q.put_nowait("item")
        assert stats.fill_pct == 90.0
        assert stats.is_nearly_full

    def test_snapshot_structure(self):
        q = asyncio.Queue(maxsize=50)
        stats = QueueStats("my_queue", q)
        snap = stats.snapshot()
        assert snap["name"] == "my_queue"
        assert snap["size"] == 0
        assert snap["maxsize"] == 50
        assert snap["fill_pct"] == 0.0
        assert snap["nearly_full"] is False


# ---------------------------------------------------------------------------
# Queues container tests
# ---------------------------------------------------------------------------

class TestQueues:
    def test_initialization(self):
        config = QueueConfig(posts=100, comments=200, media=300)
        queues = Queues(config)
        assert queues.post_queue.maxsize == 100
        assert queues.comment_queue.maxsize == 200
        assert queues.media_queue.maxsize == 300

    def test_snapshot_returns_all_queues(self):
        config = QueueConfig(posts=100, comments=200, media=300)
        queues = Queues(config)
        snaps = queues.snapshot()
        names = {s["name"] for s in snaps}
        assert "post_queue" in names
        assert "comment_queue" in names
        assert "media_queue" in names

    def test_any_nearly_full_false_when_empty(self):
        config = QueueConfig(posts=100, comments=200, media=300)
        queues = Queues(config)
        assert not queues.any_nearly_full()

    def test_any_nearly_full_true_when_saturated(self):
        config = QueueConfig(posts=10, comments=200, media=300)
        queues = Queues(config)
        for _ in range(9):  # 90%
            queues.post_queue.put_nowait("item")
        assert queues.any_nearly_full()


# ---------------------------------------------------------------------------
# Backpressure: queue blocks when full
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_blocks_producer_when_full():
    """Producer must block when queue is at maxsize — core backpressure test."""
    q = asyncio.Queue(maxsize=3)

    # Fill queue to capacity
    for _ in range(3):
        q.put_nowait("item")

    # Now try to put a 4th — should block
    producer_done = False

    async def slow_producer():
        nonlocal producer_done
        await q.put("item4")  # This MUST block
        producer_done = True

    task = asyncio.create_task(slow_producer())

    # Producer should NOT complete in 100ms (queue is full)
    await asyncio.sleep(0.1)
    assert not producer_done, "Producer should be blocked when queue is full"

    # Consume one item — producer should unblock
    q.get_nowait()
    await asyncio.wait_for(task, timeout=1.0)
    assert producer_done, "Producer should unblock after consumer dequeues"


# ---------------------------------------------------------------------------
# Sentinel drain tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sentinel_stops_consumer():
    """Consumer must exit when it receives a SENTINEL."""
    q = asyncio.Queue(maxsize=10)
    consumed = []

    async def consumer():
        while True:
            item = await q.get()
            if isinstance(item, _Sentinel):
                q.task_done()
                break
            consumed.append(item)
            q.task_done()

    task = asyncio.create_task(consumer())

    await q.put("item1")
    await q.put("item2")
    await q.put(SENTINEL)

    await asyncio.wait_for(task, timeout=2.0)

    assert consumed == ["item1", "item2"]
    assert task.done()
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_drain_all_sends_correct_sentinel_count():
    """drain_all should send exactly N sentinels for N workers per queue."""
    config = QueueConfig(posts=100, comments=100, media=100)
    queues = Queues(config)

    # Simulate 2 post workers, 1 comment worker, 3 media workers
    await queues.drain_all({
        queues.post_queue: 2,
        queues.comment_queue: 1,
        queues.media_queue: 3,
    })

    # Count sentinels in each queue
    def count_sentinels(q: asyncio.Queue) -> int:
        count = 0
        items = []
        while not q.empty():
            item = q.get_nowait()
            if isinstance(item, _Sentinel):
                count += 1
            else:
                items.append(item)
        for item in items:
            q.put_nowait(item)
        return count

    assert count_sentinels(queues.post_queue) == 2
    assert count_sentinels(queues.comment_queue) == 1
    assert count_sentinels(queues.media_queue) == 3
