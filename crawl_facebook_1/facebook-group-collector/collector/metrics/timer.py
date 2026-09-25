"""
collector/metrics/timer.py — High-precision timing instrumentation for benchmarks.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TimingSample:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    def add(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        if duration_ms < self.min_ms:
            self.min_ms = duration_ms
        if duration_ms > self.max_ms:
            self.max_ms = duration_ms

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / self.count, 1) if self.count > 0 else 0.0


class TimingRegistry:
    """Singleton/shared registry collecting timing measurements across workers."""
    _instance: Optional[TimingRegistry] = None

    def __init__(self):
        self._metrics: Dict[str, TimingSample] = {}

    @classmethod
    def get_instance(cls) -> TimingRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance._metrics.clear()

    def record(self, name: str, duration_ms: float) -> None:
        if name not in self._metrics:
            self._metrics[name] = TimingSample()
        self._metrics[name].add(duration_ms)

    def get(self, name: str) -> TimingSample:
        return self._metrics.get(name, TimingSample())

    def get_all(self) -> Dict[str, TimingSample]:
        return dict(self._metrics)


timing_registry = TimingRegistry.get_instance()


@contextmanager
def time_block(name: str):
    """Synchronous context manager measuring elapsed time in milliseconds."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        timing_registry.record(name, elapsed_ms)


@asynccontextmanager
async def time_block_async(name: str):
    """Asynchronous context manager measuring elapsed time in milliseconds."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        timing_registry.record(name, elapsed_ms)
