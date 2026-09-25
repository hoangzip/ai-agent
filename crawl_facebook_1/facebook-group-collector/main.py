"""
main.py — CLI entrypoint for the Facebook Group Collector.

Commands:
    python main.py crawl <group_url_or_id> [--mode full|incremental|deep|refresh]
    python main.py auth [--save-state <path>]    # Phase 03
    python main.py benchmark <group_url_or_id>   # Phase 11

Usage:
    python main.py crawl https://www.facebook.com/groups/123456789
    python main.py crawl https://www.facebook.com/groups/123456789 --mode incremental
    python main.py auth
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from collector.config import load_config
from collector.logging_config import setup_logging

# Automatically load .env if present
load_dotenv()

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fb-collector",
        description="Facebook Group Data Collector — Performance First",
    )
    parser.add_argument(
        "--config",
        default="config/crawler.yaml",
        help="Path to crawler.yaml (default: config/crawler.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- crawl command ---
    crawl_parser = subparsers.add_parser("crawl", help="Crawl a Facebook group")
    crawl_parser.add_argument(
        "group",
        help="Facebook Group URL or Group ID",
    )
    crawl_parser.add_argument(
        "--account",
        default=None,
        help="Account profile name to use (default: env FB_ACCOUNT or 'default')",
    )
    crawl_parser.add_argument(
        "--mode",
        choices=["full", "incremental", "deep", "refresh"],
        default=None,
        help="Crawl mode (overrides config file)",
    )
    crawl_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    crawl_parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help="Maximum posts to crawl (overrides config)",
    )
    crawl_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Crawl posts published in a specific year (e.g. 2026) and stop when older posts are reached",
    )

    # --- auth command (Phase 03) ---
    auth_parser = subparsers.add_parser(
        "auth",
        help="Open browser for Facebook login and save session state",
    )
    auth_parser.add_argument(
        "--account",
        default=None,
        help="Account profile name (default: env FB_ACCOUNT or 'default')",
    )
    auth_parser.add_argument(
        "--email",
        default=None,
        help="Facebook login email or phone (default: env FB_EMAIL)",
    )
    auth_parser.add_argument(
        "--password",
        default=None,
        help="Facebook login password (default: env FB_PASSWORD)",
    )
    auth_parser.add_argument(
        "--save-state",
        default=None,
        help="Custom path to save browser state (overrides default per-account path)",
    )
    auth_parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run in headless mode (default: False for auth to allow manual 2FA/checkpoint completion)",
    )

    # --- benchmark command (Phase 11) ---
    bench_parser = subparsers.add_parser(
        "benchmark",
        help="[Phase 11] Run benchmark and produce diagnostic performance report",
    )
    bench_parser.add_argument("group", help="Facebook Group URL or Group ID")
    bench_parser.add_argument(
        "--max-posts",
        type=int,
        default=100,
        help="Number of posts to benchmark (default 100)",
    )
    bench_parser.add_argument(
        "--account",
        default=None,
        help="Account profile name to use",
    )
    bench_parser.add_argument(
        "--mock",
        action="store_true",
        help="Run simulated 100-post pipeline benchmark without live Facebook page",
    )

    # --- media-crawl command ---
    media_parser = subparsers.add_parser(
        "media-crawl",
        help="Crawl group /media gallery — discovers posts from photo grid, patches missing fields",
    )
    media_parser.add_argument(
        "group",
        help="Facebook Group URL or Group ID",
    )
    media_parser.add_argument(
        "--account",
        default=None,
        help="Account profile name to use (default: env FB_ACCOUNT or 'default')",
    )

    return parser.parse_args()


async def cmd_media_crawl(args: argparse.Namespace, config) -> int:
    """Execute a media gallery crawl run."""
    import os
    from collector.facebook.auth import AccountManager
    from collector.media_gallery_orchestrator import MediaGalleryOrchestrator

    account_mgr = AccountManager(Path(config.storage.data_dir) / "browser_state")
    account_name = args.account or os.getenv("FB_ACCOUNT", "default")
    state_path = account_mgr.get_state_path(account_name)

    if not state_path.exists() or state_path.stat().st_size == 0:
        logger.error(
            "No active session for account '%s' at %s. "
            "Please run: python main.py auth --account %s",
            account_name, state_path, account_name,
        )
        return 2

    config.browser.browser_state_path = str(state_path)
    run_id = str(uuid.uuid4())
    logger.info(
        "Starting media-crawl: account=%s group=%s run_id=%s",
        account_name, args.group, run_id,
    )

    orchestrator = MediaGalleryOrchestrator(config)
    await orchestrator.run(group_url=args.group, run_id=run_id)
    return 0


async def cmd_crawl(args: argparse.Namespace, config) -> int:
    """Execute a crawl run."""
    import os
    from collector.facebook.auth import AccountManager
    from collector.orchestrator import Orchestrator

    # Multi-account resolution
    account_mgr = AccountManager(Path(config.storage.data_dir) / "browser_state")
    account_name = args.account or os.getenv("FB_ACCOUNT", "default")
    state_path = account_mgr.get_state_path(account_name)

    if not state_path.exists() or state_path.stat().st_size == 0:
        logger.error(
            "No active session for account '%s' at %s. "
            "Please run: python main.py auth --account %s",
            account_name, state_path, account_name,
        )
        return 2

    config.browser.browser_state_path = str(state_path)

    # Apply CLI overrides
    if args.mode:
        config.mode = args.mode
    if args.max_posts is not None:
        config.limits.max_posts = args.max_posts
    if getattr(args, "year", None) is not None:
        config.limits.since_year = args.year

    run_id = str(uuid.uuid4())
    logger.info(
        "Starting crawl: account=%s group=%s mode=%s resume=%s run_id=%s",
        account_name, args.group, config.mode, getattr(args, "resume", False), run_id,
    )

    orchestrator = Orchestrator(config)
    try:
        await orchestrator.run(
            group_url=args.group,
            run_id=run_id,
            resume=getattr(args, "resume", False),
        )
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error("Crawl failed: %s", e, exc_info=True)
        return 1


async def cmd_auth(args: argparse.Namespace, config) -> int:
    """Phase 03: Authenticate account and save session state."""
    import os
    from playwright.async_api import async_playwright
    from collector.facebook.auth import AccountManager, login_and_save_session
    from collector.facebook.browser import BrowserFactory

    account_mgr = AccountManager(Path(config.storage.data_dir) / "browser_state")
    account_name = args.account or os.getenv("FB_ACCOUNT", "default")
    email = args.email or os.getenv("FB_EMAIL")
    password = args.password or os.getenv("FB_PASSWORD")

    save_path = Path(args.save_state) if args.save_state else account_mgr.get_state_path(account_name)

    logger.info(
        "Starting authentication for account '%s' (headless=%s, target=%s)...",
        account_name, args.headless, save_path,
    )

    async with async_playwright() as pw:
        browser = await BrowserFactory.launch_browser(
            pw,
            config.browser,
            headless=args.headless,
        )
        try:
            # If an existing state exists, pass it so we can check if still valid
            context = await BrowserFactory.create_context(
                browser,
                config.browser,
                state_path=save_path if save_path.exists() else None,
            )
            page = await context.new_page()

            success, saved_path = await login_and_save_session(
                page=page,
                account_name=account_name,
                email=email,
                password=password,
                state_path=save_path,
            )

            if success:
                logger.info("Authentication succeeded for '%s'! State saved to %s", account_name, saved_path)
                return 0
            else:
                logger.error("Authentication failed or timed out for account '%s'", account_name)
                return 1
        finally:
            await browser.close()


async def cmd_benchmark(args: argparse.Namespace, config) -> int:
    """Phase 11: Run benchmark and produce performance report."""
    import time
    from collector.metrics.benchmark import BenchmarkReport
    from collector.metrics.emitter import MetricsCounters
    from collector.metrics.timer import timing_registry, time_block, time_block_async
    from collector.storage.layout import StorageLayout, slugify

    group_slug = slugify(args.group)
    max_posts = args.max_posts or 100
    timing_registry.reset()

    logger.info("Starting benchmark on group '%s' (max_posts=%d, mock=%s)...",
                group_slug, max_posts, args.mock)

    counters = MetricsCounters()

    if args.mock:
        # Run simulated 100-post workload to test all components under load
        from datetime import datetime, timezone
        from collector.pipeline.items import PostDiscoveredItem, CommentItem, SENTINEL
        from collector.writers.post_writer import PostWriterWorker
        from collector.writers.comment_writer import CommentWriterWorker
        from collector.pipeline.dedupe import DedupeManager

        layout = StorageLayout(root_dir=f"{config.storage.data_dir}_bench")
        layout.ensure_dirs(group_slug)

        post_queue = asyncio.Queue(maxsize=config.queues.posts)
        comment_queue = asyncio.Queue(maxsize=config.queues.comments)

        post_writer = PostWriterWorker(
            name="bench-post-writer",
            queue=post_queue,
            counters=counters,
            layout=layout,
            group_slug=group_slug,
            group_id=args.group,
        )
        comment_writer = CommentWriterWorker(
            name="bench-comment-writer",
            queue=comment_queue,
            counters=counters,
            layout=layout,
            group_slug=group_slug,
        )

        w1_task = asyncio.create_task(post_writer.run())
        w2_task = asyncio.create_task(comment_writer.run())

        now = datetime.now(timezone.utc)
        start_t = time.perf_counter()

        for i in range(max_posts):
            # Simulate browser feed scroll & parse timing
            async with time_block_async("browser.feed_scroll_per_post"):
                await asyncio.sleep(0.001)  # 1ms mock DOM time
                pid = f"bench_post_{i}"
                item = PostDiscoveredItem(
                    discovery_run_id="bench-run",
                    discovered_at=now,
                    facebook_post_id=pid,
                    post_url=f"https://fb.com/groups/{group_slug}/posts/{i}",
                    title=f"Benchmark Post #{i}",
                )

            counters.posts_discovered += 1
            await post_queue.put(item)

            # Simulate 10 comments per post
            async with time_block_async("browser.post_page_open"):
                await asyncio.sleep(0.002)

            async with time_block_async("browser.comment_extraction"):
                await asyncio.sleep(0.003)
                for c in range(10):
                    cid = f"cmt_{i}_{c}"
                    await comment_queue.put(CommentItem(
                        post_internal_id=pid,
                        facebook_comment_id=cid,
                        content=f"Benchmark comment {c} on post {i}",
                        commented_at=now,
                    ))
                    counters.comments_discovered += 1

            # Simulate media download
            async with time_block_async("media.download"):
                await asyncio.sleep(0.001)
                counters.media_discovered += 2
                counters.media_downloaded += 2
            with time_block("media.sha256"):
                pass
            async with time_block_async("media.storage_write"):
                pass

        await post_queue.put(SENTINEL)
        await comment_queue.put(SENTINEL)

        await w1_task
        await w2_task

    else:
        # Live Facebook crawl benchmark
        import os
        from collector.facebook.auth import AccountManager
        from collector.orchestrator import Orchestrator

        account_mgr = AccountManager(Path(config.storage.data_dir) / "browser_state")
        account_name = args.account or os.getenv("FB_ACCOUNT", "default")
        state_path = account_mgr.get_state_path(account_name)

        if not state_path.exists() or state_path.stat().st_size == 0:
            logger.error(
                "No active session for account '%s' at %s. "
                "Please run: python main.py auth --account %s",
                account_name, state_path, account_name,
            )
            return 2

        config.browser.browser_state_path = str(state_path)
        config.limits.max_posts = max_posts
        orchestrator = Orchestrator(config)
        run_id = str(uuid.uuid4())
        await orchestrator.run(group_url=args.group, run_id=run_id)
        if orchestrator._counters:
            counters = orchestrator._counters

    # Generate benchmark report
    if args.mock:
        peak_queues = {
            "post_queue": {"size": post_queue.qsize(), "maxsize": config.queues.posts, "fill_pct": 0},
            "comment_queue": {"size": comment_queue.qsize(), "maxsize": config.queues.comments, "fill_pct": 0},
            "media_queue": {"size": 0, "maxsize": config.queues.media, "fill_pct": 0},
        }
    else:
        snapshots = orchestrator._queues.snapshot() if (orchestrator and orchestrator._queues) else []
        peak_queues = {s["name"]: s for s in snapshots}


    report = BenchmarkReport(
        group_url_or_id=args.group,
        group_slug=group_slug,
        group_id=args.group,
        mode="full",
        config=config,
        counters=counters,
        peak_queues=peak_queues,
    )

    report_text = report.generate_report()
    print("\n" + report_text)

    saved_path = report.save_report()
    logger.info("Benchmark report successfully saved to: %s", saved_path)
    return 0


async def _main() -> int:
    args = parse_args()

    # Load config first to get log level
    config = load_config(args.config)
    setup_logging(config.metrics.log_level)

    logger.info("Facebook Group Collector starting (command=%s)", args.command)

    dispatch = {
        "crawl": cmd_crawl,
        "auth": cmd_auth,
        "benchmark": cmd_benchmark,
        "media-crawl": cmd_media_crawl,
    }

    handler = dispatch.get(args.command)
    if not handler:
        logger.error("Unknown command: %s", args.command)
        return 1

    return await handler(args, config)


def main() -> None:
    exit_code = asyncio.run(_main())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
