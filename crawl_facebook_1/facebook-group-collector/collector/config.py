"""
collector/config.py — Configuration loader from crawler.yaml.
All tunable parameters come from config; nothing hard-coded in source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml



# ---------------------------------------------------------------------------
# Config dataclasses (strongly typed, no dict access in business logic)
# ---------------------------------------------------------------------------

@dataclass
class BrowserConfig:
    context_count: int = 1
    feed_pages: int = 1
    comment_pages: int = 2
    headless: bool = True
    browser_state_path: str = "data/browser_state/default.json"
    scroll_delay_min_ms: int = 500
    scroll_delay_max_ms: int = 2000
    page_timeout_ms: int = 30_000
    navigation_timeout_ms: int = 60_000
    block_resources: bool = False
    channel: Optional[str] = "chrome"


@dataclass
class WorkerConfig:
    comment_workers: int = 2
    media_workers: int = 6


@dataclass
class QueueConfig:
    posts: int = 2000
    comments: int = 5000
    media: int = 5000


@dataclass
class StorageConfig:
    """File-based JSON storage configuration."""
    data_dir: str = "data"              # Root data directory
    pretty_json: bool = True            # Pretty-print JSON (indent=2)
    # Batch write: flush after N items or flush_ms timeout
    posts_batch: int = 50               # Lower than DB: file I/O is cheap per-item
    comments_batch: int = 100
    actors_batch: int = 50
    flush_ms: int = 2000


@dataclass
class MediaConfig:
    workers: int = 6
    storage_path: str = "data/media"
    download_timeout_sec: int = 60
    max_retries: int = 3


@dataclass
class CheckpointConfig:
    every_posts: int = 20
    every_seconds: int = 15


@dataclass
class IncrementalConfig:
    stop_after_consecutive_known_posts: int = 30


@dataclass
class RevisitConfig:
    interval_under_1d_hours: int = 1
    interval_1_to_3d_hours: int = 6
    interval_3_to_7d_hours: int = 12
    interval_7_to_30d_hours: int = 24
    interval_30_to_90d_hours: int = 72
    interval_over_90d_days: int = 7


@dataclass
class LimitsConfig:
    max_posts: Optional[int] = None
    since_year: Optional[int] = None
    since_date: Optional[str] = None


@dataclass
class MetricsConfig:
    emit_every_seconds: int = 10
    log_level: str = "INFO"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 30.0


@dataclass
class CrawlerConfig:
    mode: str = "full"
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    queues: QueueConfig = field(default_factory=QueueConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    incremental: IncrementalConfig = field(default_factory=IncrementalConfig)
    revisit: RevisitConfig = field(default_factory=RevisitConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base."""
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str | Path = "config/crawler.yaml") -> CrawlerConfig:
    """Load config from YAML file."""
    path = Path(path)
    raw: dict = {}
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

    def _sub(key: str) -> dict:
        return raw.get(key, {}) or {}

    return CrawlerConfig(
        mode=raw.get("crawler", {}).get("mode", "full") if isinstance(raw.get("crawler"), dict) else "full",
        browser=BrowserConfig(**{k: v for k, v in _sub("browser").items() if k in BrowserConfig.__dataclass_fields__}),
        workers=WorkerConfig(**{k: v for k, v in _sub("workers").items() if k in WorkerConfig.__dataclass_fields__}),
        queues=QueueConfig(**{k: v for k, v in _sub("queues").items() if k in QueueConfig.__dataclass_fields__}),
        storage=StorageConfig(**{k: v for k, v in _sub("storage").items() if k in StorageConfig.__dataclass_fields__}),
        media=MediaConfig(**{k: v for k, v in _sub("media").items() if k in MediaConfig.__dataclass_fields__}),
        checkpoint=CheckpointConfig(**{k: v for k, v in _sub("checkpoint").items() if k in CheckpointConfig.__dataclass_fields__}),
        incremental=IncrementalConfig(**{k: v for k, v in _sub("incremental").items() if k in IncrementalConfig.__dataclass_fields__}),
        revisit=RevisitConfig(**{k: v for k, v in _sub("revisit").items() if k in RevisitConfig.__dataclass_fields__}),
        limits=LimitsConfig(**{k: v for k, v in _sub("limits").items() if k in LimitsConfig.__dataclass_fields__}),
        metrics=MetricsConfig(**{k: v for k, v in _sub("metrics").items() if k in MetricsConfig.__dataclass_fields__}),
        retry=RetryConfig(**{k: v for k, v in _sub("retry").items() if k in RetryConfig.__dataclass_fields__}),
    )
