#!/usr/bin/env python3
"""
run_collector.py — Unified Master CLI for Facebook Group Crawler.

Usage examples:
  # Standard initial crawl on any group:
  python run_collector.py --group 978769317924542 --check-comments

  # Incremental run (tomorrow or daily) to only collect NEW posts & photos:
  python run_collector.py --group 978769317924542 --update-new --check-comments

  # Crawl another group:
  python run_collector.py --group ANOTHER_GROUP_ID --check-comments

  # Limit number of posts for quick check:
  python run_collector.py --group 978769317924542 --limit 10
"""
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.crawl_media_gallery_sequential import main

if __name__ == "__main__":
    asyncio.run(main())
