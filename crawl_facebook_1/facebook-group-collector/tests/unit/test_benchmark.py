"""
tests/unit/test_benchmark.py — Unit tests for Phase 11: Benchmark & Metrics.
"""
from datetime import datetime, timezone
from pathlib import Path
import pytest

from collector.config import CrawlerConfig
from collector.metrics.benchmark import BenchmarkReport
from collector.metrics.emitter import MetricsCounters
from collector.metrics.timer import TimingRegistry, TimingSample, time_block, time_block_async


def test_timing_registry_and_samples():
    """Verify timing measurements and aggregations."""
    registry = TimingRegistry()
    registry.record("test.op", 10.0)
    registry.record("test.op", 20.0)
    registry.record("test.op", 30.0)

    sample = registry.get("test.op")
    assert sample.count == 3
    assert sample.total_ms == 60.0
    assert sample.min_ms == 10.0
    assert sample.max_ms == 30.0
    assert sample.avg_ms == 20.0


def test_time_block_context_managers():
    """Verify time_block and time_block_async record timings."""
    TimingRegistry.reset()
    registry = TimingRegistry.get_instance()

    with time_block("sync.block"):
        pass

    assert registry.get("sync.block").count == 1
    assert registry.get("sync.block").total_ms >= 0.0


@pytest.mark.asyncio
async def test_time_block_async():
    TimingRegistry.reset()
    registry = TimingRegistry.get_instance()

    async with time_block_async("async.block"):
        pass

    assert registry.get("async.block").count == 1


def test_benchmark_report_generation(tmp_path: Path):
    """Verify benchmark report formatting and all required sections."""
    config = CrawlerConfig()
    counters = MetricsCounters()
    counters.posts_discovered = 100
    counters.posts_new = 95
    counters.posts_skipped = 5
    counters.comments_discovered = 1500
    counters.comments_new = 1500
    counters.media_discovered = 300
    counters.media_downloaded = 290
    counters.media_deduped = 10

    timings = {
        "browser.feed_scroll_per_post": TimingSample(count=100, total_ms=18000.0),
        "browser.post_page_open": TimingSample(count=100, total_ms=210000.0),
        "browser.comment_extraction": TimingSample(count=100, total_ms=180000.0),
        "storage.flush_posts": TimingSample(count=100, total_ms=1200.0),
        "storage.flush_comments": TimingSample(count=1500, total_ms=28000.0),
        "media.download": TimingSample(count=290, total_ms=258100.0),
        "media.sha256": TimingSample(count=290, total_ms=580.0),
        "media.storage_write": TimingSample(count=290, total_ms=1450.0),
    }

    report = BenchmarkReport(
        group_url_or_id="https://facebook.com/groups/benchmark-target",
        group_slug="benchmark-target",
        group_id="999888777",
        mode="full",
        config=config,
        counters=counters,
        timings=timings,
    )

    text = report.generate_report()
    assert "BENCHMARK REPORT" in text
    assert "THROUGHPUT" in text
    assert "TIMING BREAKDOWN" in text
    assert "QUEUE DEPTHS" in text
    assert "RELIABILITY" in text
    assert "RESOURCES" in text
    assert "BOTTLENECK ANALYSIS" in text

    # Save to disk
    out_dir = tmp_path / "reports"
    saved = report.save_report(out_dir)
    assert saved.exists()
    assert saved.stat().st_size > 0


def test_benchmark_bottleneck_detection():
    """Verify decision table identifies page load and comment bottlenecks."""
    config = CrawlerConfig()
    counters = MetricsCounters()
    counters.posts_discovered = 100
    counters.errors = 10  # 10% errors

    timings = {
        # > 3000 ms -> page load bottleneck
        "browser.post_page_open": TimingSample(count=10, total_ms=45000.0),
        # > 2000 ms -> DOM extraction slow
        "browser.comment_extraction": TimingSample(count=10, total_ms=25000.0),
    }

    peak_queues = {
        "post_queue": {"size": 1800, "maxsize": 2000, "fill_pct": 90},
    }

    report = BenchmarkReport(
        group_url_or_id="https://facebook.com/groups/slow-group",
        group_slug="slow-group",
        group_id="111",
        mode="full",
        config=config,
        counters=counters,
        timings=timings,
        peak_queues=peak_queues,
    )

    diagnoses = report.diagnose_bottlenecks()
    diag_text = " ".join(diagnoses)

    assert "Page load is bottleneck" in diag_text
    assert "DOM comment parsing is slow" in diag_text
    assert "post_queue queue congested" in diag_text
    assert "Error rate high" in diag_text
