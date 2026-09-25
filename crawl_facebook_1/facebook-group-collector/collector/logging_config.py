"""
collector/logging_config.py — Structured logging setup.

Uses Python standard logging with a clean format.
Log level configurable via config or LOG_LEVEL env var.
"""
from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with structured output."""
    level_str = os.getenv("LOG_LEVEL", level).upper()
    numeric_level = getattr(logging, level_str, logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
