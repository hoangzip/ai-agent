"""
collector/pipeline/revisit.py — Post revisit scheduling and crawl status state machine (Phase 10).

Responsibilities:
- Compute next_check_at per post age using RevisitConfig
- Determine if a post is due for refresh
- Enforce valid crawl_status state transitions
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Union

from collector.config import RevisitConfig

logger = logging.getLogger(__name__)


class CrawlStatus:
    """Standard lifecycle states for a Facebook post in the collector."""
    DISCOVERED = "DISCOVERED"
    CRAWLING = "CRAWLING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    REFRESH_DUE = "REFRESH_DUE"
    FAILED = "FAILED"

    VALID_STATUSES = {
        DISCOVERED,
        CRAWLING,
        COMPLETE,
        PARTIAL,
        REFRESH_DUE,
        FAILED,
    }

    # Directed acyclic/cyclic transitions allowed in the pipeline
    ALLOWED_TRANSITIONS = {
        DISCOVERED: {CRAWLING, FAILED},
        CRAWLING: {COMPLETE, PARTIAL, FAILED},
        COMPLETE: {REFRESH_DUE, CRAWLING},
        PARTIAL: {REFRESH_DUE, CRAWLING, FAILED},
        REFRESH_DUE: {CRAWLING, FAILED},
        FAILED: {CRAWLING},  # Allowed on retry
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        """Check if transition from current status to target status is valid."""
        if current == target:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def validate_transition(cls, current: str, target: str) -> None:
        """Raise ValueError if transition is invalid."""
        if not cls.can_transition(current, target):
            raise ValueError(
                f"Invalid crawl_status transition: cannot transition from '{current}' to '{target}'"
            )


def parse_datetime(dt_val: Union[datetime, str, None]) -> Optional[datetime]:
    """Parse an ISO format string or return datetime instance with UTC timezone."""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val
    try:
        dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def compute_next_check_at(
    posted_at: Union[datetime, str, None],
    config: Optional[RevisitConfig] = None,
    reference_time: Optional[datetime] = None,
) -> datetime:
    """
    Compute the next revisit time based on post age.

    Policy:
      < 1 day:      interval_under_1d_hours (default 1h)
      1 - 3 days:   interval_1_to_3d_hours (default 6h)
      3 - 7 days:   interval_3_to_7d_hours (default 12h)
      7 - 30 days:  interval_7_to_30d_hours (default 24h)
      30 - 90 days: interval_30_to_90d_hours (default 72h)
      > 90 days:    interval_over_90d_days (default 7 days)
    """
    cfg = config or RevisitConfig()
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    dt_posted = parse_datetime(posted_at)

    if not dt_posted:
        # Default fallback: 1 hour if post timestamp is unknown
        return now + timedelta(hours=cfg.interval_under_1d_hours)

    age = now - dt_posted
    if age < timedelta(0):
        # Clock skew / future timestamp: treat as newest
        age = timedelta(0)

    if age < timedelta(days=1):
        interval = timedelta(hours=cfg.interval_under_1d_hours)
    elif age < timedelta(days=3):
        interval = timedelta(hours=cfg.interval_1_to_3d_hours)
    elif age < timedelta(days=7):
        interval = timedelta(hours=cfg.interval_3_to_7d_hours)
    elif age < timedelta(days=30):
        interval = timedelta(hours=cfg.interval_7_to_30d_hours)
    elif age < timedelta(days=90):
        interval = timedelta(hours=cfg.interval_30_to_90d_hours)
    else:
        interval = timedelta(days=cfg.interval_over_90d_days)

    return now + interval


def is_refresh_due(post: dict, reference_time: Optional[datetime] = None) -> bool:
    """Check if a post is due for comment refresh."""
    status = post.get("crawl_status")
    if status == CrawlStatus.REFRESH_DUE:
        return True

    next_check_str = post.get("next_check_at")
    if not next_check_str:
        return False

    next_check = parse_datetime(next_check_str)
    if not next_check:
        return False

    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return next_check <= now
