"""
tests/unit/test_backpressure.py — Phase 02: Backpressure and ProducerGate tests.
"""
from __future__ import annotations

import asyncio

import pytest

from collector.pipeline.backpressure import BackpressureMonitor, ProducerGate


# ---------------------------------------------------------------------------
# ProducerGate tests
# ---------------------------------------------------------------------------

class TestProducerGate:
    def test_gate_open_by_default(self):
        gate = ProducerGate()
        assert gate.is_open

    def test_close_sets_paused(self):
        gate = ProducerGate()
        gate.close()
        assert not gate.is_open

    def test_open_resumes(self):
        gate = ProducerGate()
        gate.close()
        gate.open()
        assert gate.is_open

    @pytest.mark.asyncio
    async def test_wait_passes_when_open(self):
        gate = ProducerGate()
        # Should not block
        await asyncio.wait_for(gate.wait(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_blocks_when_closed(self):
        gate = ProducerGate()
        gate.close()

        completed = False

        async def waiter():
            nonlocal completed
            await gate.wait()
            completed = True

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.1)
        assert not completed  # Still blocked

        gate.open()
        await asyncio.wait_for(task, timeout=1.0)
        assert completed  # Unblocked after open()


# ---------------------------------------------------------------------------
# BackpressureMonitor tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backpressure_monitor_runs_and_stops():
    """Monitor should start and stop cleanly."""
    snapshots = [{"name": "q", "fill_pct": 10.0, "size": 10, "maxsize": 100}]
    monitor = BackpressureMonitor(
        snapshot_fn=lambda: snapshots,
        check_interval_sec=0.05,
    )

    task = asyncio.create_task(monitor.run())
    await asyncio.sleep(0.15)  # Let it run a couple cycles
    monitor.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()


@pytest.mark.asyncio
async def test_backpressure_monitor_warns_on_full_queue(caplog):
    """Monitor should log WARNING when queue is consistently > 80% full."""
    import logging

    # Create a queue snapshot that's consistently 90% full
    snapshots = [{"name": "test_queue", "fill_pct": 90.0, "size": 90, "maxsize": 100}]

    monitor = BackpressureMonitor(
        snapshot_fn=lambda: snapshots,
        check_interval_sec=0.05,
        warn_threshold_pct=80.0,
        warn_after_consecutive=2,
    )

    with caplog.at_level(logging.WARNING, logger="collector.pipeline.backpressure"):
        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.2)  # Enough for 3+ checks
        monitor.stop()
        await asyncio.wait_for(task, timeout=1.0)

    # Should have at least one BACKPRESSURE warning
    assert any("BACKPRESSURE" in r.message for r in caplog.records)
