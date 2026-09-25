"""
collector/metrics/benchmark.py — Benchmark report generator and analyzer (Phase 11).

Generates comprehensive benchmark reports matching BENCHMARK_PLAN.md Section 3
and performs automatic diagnosis using the Section 4 Decision Table.
"""
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import psutil

from collector.config import CrawlerConfig
from collector.metrics.emitter import MetricsCounters
from collector.metrics.timer import TimingSample, timing_registry


class BenchmarkReport:
    """Formats and writes benchmark reports to disk and stdout."""

    def __init__(
        self,
        group_url_or_id: str,
        group_slug: str,
        group_id: str,
        mode: str,
        config: CrawlerConfig,
        counters: MetricsCounters,
        timings: Optional[Dict[str, TimingSample]] = None,
        peak_queues: Optional[Dict[str, dict]] = None,
        crawl_date: Optional[datetime] = None,
    ):
        self.group_url_or_id = group_url_or_id
        self.group_slug = group_slug
        self.group_id = group_id
        self.mode = mode
        self.config = config
        self.counters = counters
        self.timings = timings or timing_registry.get_all()
        self.peak_queues = peak_queues or {}
        self.crawl_date = crawl_date or datetime.now(timezone.utc)

    def _get_hardware_info(self) -> str:
        try:
            mem = psutil.virtual_memory()
            total_ram_gb = round(mem.total / (1024 ** 3), 1)
            proc_name = platform.processor() or platform.machine()
            sys_name = platform.system()
            return f"{sys_name} ({proc_name}), {total_ram_gb}GB RAM, Python {platform.python_version()}"
        except Exception:
            return "Standard Environment"

    def diagnose_bottlenecks(self) -> list[str]:
        """Apply BENCHMARK_PLAN.md Section 4 Decision Table."""
        diagnoses = []

        post_page_open = self.timings.get("browser.post_page_open")
        if post_page_open and post_page_open.avg_ms > 3000:
            diagnoses.append(
                f"Page load is bottleneck (browser.post_page_open avg {post_page_open.avg_ms} ms > 3000 ms) "
                "— Recommended Action: enable asset/font blocking in browser context"
            )

        comment_ext = self.timings.get("browser.comment_extraction")
        if comment_ext and comment_ext.avg_ms > 2000:
            diagnoses.append(
                f"DOM comment parsing is slow (browser.comment_extraction avg {comment_ext.avg_ms} ms > 2000 ms) "
                "— Recommended Action: optimize selector queries and reduce evaluate calls"
            )

        db_flush = self.timings.get("storage.flush_posts")
        if db_flush and db_flush.avg_ms > 200:
            diagnoses.append(
                f"Storage flush is bottleneck (storage.flush_posts avg {db_flush.avg_ms} ms > 200 ms) "
                "— Recommended Action: check file I/O latency or increase batch size"
            )

        # Queue congestion
        for q_name, q_data in self.peak_queues.items():
            pct = q_data.get("fill_pct", 0)
            if pct > 80:
                diagnoses.append(
                    f"{q_name} queue congested (peak {pct}% full) "
                    f"— Recommended Action: increase consumer workers for {q_name}"
                )

        # Memory check
        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
        if mem_mb > 3000:
            diagnoses.append(
                f"Memory usage critical ({mem_mb} MB > 3000 MB) "
                "— Recommended Action: check queue maxsizes and dedupe cache lifecycle"
            )

        total_items = self.counters.posts_discovered + self.counters.comments_discovered
        if total_items > 50 and (self.counters.errors / total_items) > 0.05:
            diagnoses.append(
                f"Error rate high ({self.counters.errors}/{total_items} items, "
                f"{round(self.counters.errors / total_items * 100, 1)}%) "
                "— Recommended Action: investigate network stability or DOM selector updates"
            )

        if not diagnoses:
            diagnoses.append("No critical bottlenecks detected. Pipeline operating within performance thresholds.")

        return diagnoses

    def generate_report(self) -> str:
        proc = psutil.Process()
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)

        t_feed = self.timings.get("browser.feed_scroll_per_post", TimingSample()).avg_ms
        t_page = self.timings.get("browser.post_page_open", TimingSample()).avg_ms
        t_comments = self.timings.get("browser.comment_extraction", TimingSample()).avg_ms
        t_storage_posts = self.timings.get("storage.flush_posts", TimingSample()).avg_ms
        t_storage_cmts = self.timings.get("storage.flush_comments", TimingSample()).avg_ms
        t_media_dl = self.timings.get("media.download", TimingSample()).avg_ms
        t_media_hash = self.timings.get("media.sha256", TimingSample()).avg_ms
        t_media_write = self.timings.get("media.storage_write", TimingSample()).avg_ms

        # Queue strings
        pq_post = self.peak_queues.get("post_queue", {"size": 0, "maxsize": self.config.queues.posts, "fill_pct": 0})
        pq_cmt = self.peak_queues.get("comment_queue", {"size": 0, "maxsize": self.config.queues.comments, "fill_pct": 0})
        pq_media = self.peak_queues.get("media_queue", {"size": 0, "maxsize": self.config.queues.media, "fill_pct": 0})

        diagnoses = self.diagnose_bottlenecks()
        diag_str = "\n".join(f"- {d}" for d in diagnoses)

        report = f"""============================================================
 BENCHMARK REPORT — Facebook Group Collector
============================================================
 Target Group : {self.group_slug} ({self.group_id})
 Mode         : {self.mode}
 Crawl Date   : {self.crawl_date.strftime("%Y-%m-%d %H:%M:%S UTC")}
 Hardware     : {self._get_hardware_info()}
 Config       : context_count={self.config.browser.context_count}, comment_workers={self.config.workers.comment_workers}, media_workers={self.config.workers.media_workers}

 THROUGHPUT
 ----------
 Posts discovered       : {self.counters.posts_discovered:,}
 Posts new              : {self.counters.posts_new:,}
 Posts skipped          : {self.counters.posts_skipped:,}
 Posts/sec              : {self.counters.posts_per_sec()}
 Comments discovered    : {self.counters.comments_discovered:,}
 Comments new           : {self.counters.comments_new:,}
 Comments skipped       : {self.counters.comments_skipped:,}
 Comments/sec           : {self.counters.comments_per_sec()}
 Media discovered       : {self.counters.media_discovered:,}
 Media downloaded       : {self.counters.media_downloaded:,}
 Media deduped          : {self.counters.media_deduped:,}
 Media/sec              : {self.counters.media_per_sec()}

 TIMING BREAKDOWN (avg per operation)
 ------------------------------------
 Browser: feed scroll + parse : {t_feed:,.1f} ms/post
 Browser: post page open      : {t_page:,.1f} ms/post
 Browser: comment extraction  : {t_comments:,.1f} ms/post
 Storage: flush (posts)       : {t_storage_posts:,.1f} ms/batch
 Storage: flush (comments)    : {t_storage_cmts:,.1f} ms/batch
 Media: download              : {t_media_dl:,.1f} ms/file
 Media: sha256 hashing        : {t_media_hash:,.1f} ms/file
 Media: storage write         : {t_media_write:,.1f} ms/file

 QUEUE DEPTHS (peak)
 -------------------
 post_queue    : {pq_post.get('size', 0)} / {pq_post.get('maxsize', 0)} ({pq_post.get('fill_pct', 0)}%)
 comment_queue : {pq_cmt.get('size', 0)} / {pq_cmt.get('maxsize', 0)} ({pq_cmt.get('fill_pct', 0)}%)
 media_queue   : {pq_media.get('size', 0)} / {pq_media.get('maxsize', 0)} ({pq_media.get('fill_pct', 0)}%)

 RELIABILITY
 -----------
 Errors        : {self.counters.errors}
 Retries       : {self.counters.retries}
 PARTIAL posts : {self.counters.partial_posts}
 FAILED posts  : {self.counters.failed_posts}

 RESOURCES
 ---------
 Peak memory RSS : {mem_mb:,.1f} MB
 Elapsed time    : {self.counters.elapsed_str()}

 BOTTLENECK ANALYSIS & DECISION
 ------------------------------
{diag_str}
============================================================
"""
        return report

    def save_report(self, target_dir: str | Path = "docs/benchmark_results") -> Path:
        """Save benchmark report markdown to docs/benchmark_results/."""
        path = Path(target_dir)
        path.mkdir(parents=True, exist_ok=True)
        timestamp = self.crawl_date.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self.group_slug}.txt"
        file_path = path / filename

        report_content = self.generate_report()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return file_path
