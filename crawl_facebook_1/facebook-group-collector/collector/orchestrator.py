"""
collector/orchestrator.py — Main orchestrator and graceful shutdown handler.

Responsibilities:
- Instantiate all storage repositories, queues, workers, metrics emitter, backpressure monitor
- Launch and monitor Playwright browser session
- Validate authentication status (halt if BLOCKED_AUTH)
- Extract and persist group metadata
- Start FeedProducer (Phase 04) with backpressure gate
- Run PostWriterWorker to persist posts and authors
- Handle SIGTERM/SIGINT for graceful shutdown
- Coordinate startup sequence and clean shutdown sequence
"""
from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, async_playwright

from collector.config import CrawlerConfig
from collector.facebook.auth import AuthStatus, check_auth_status
from collector.facebook.browser import BrowserFactory
from collector.facebook.feed import FeedProducer
from collector.facebook.group import GroupExtractor
from collector.metrics.emitter import MetricsCounters, MetricsEmitter
from collector.pipeline.backpressure import BackpressureMonitor
from collector.pipeline.items import SENTINEL
from collector.pipeline.queues import Queues
from collector.pipeline.worker import WorkerPool
from collector.storage.layout import StorageLayout, slugify
from collector.storage.repository import CheckpointRepo, GroupRepo, PostRepo, RunRepo
from collector.workers.comment_worker import CommentWorker
from collector.workers.media_worker import MediaWorker
from collector.writers.comment_writer import CommentWriterWorker
from collector.writers.post_writer import PostWriterWorker

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central coordinator for the crawler pipeline."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._queues: Optional[Queues] = None
        self._counters: Optional[MetricsCounters] = None
        self._metrics_emitter: Optional[MetricsEmitter] = None
        self._bp_monitor: Optional[BackpressureMonitor] = None
        self._worker_pool: Optional[WorkerPool] = None
        self._background_tasks: list[asyncio.Task] = []

        # Storage & repos
        self.layout = StorageLayout(self.config.storage.data_dir)
        self.group_repo = GroupRepo(self.layout)
        self.run_repo = RunRepo(self.layout)
        self.checkpoint_repo = CheckpointRepo(self.layout)
        self.checkpoint_manager = None
        self._completed = False

        # Browser handles
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, group_url: str, run_id: str, resume: bool = False) -> None:
        """
        Execute a full crawl run.

        Args:
            group_url: Facebook group URL or ID
            run_id: UUID for this crawl_run (pre-created by caller)
            resume: Whether to resume from previous checkpoint
        """
        logger.info("Orchestrator starting run_id=%s group=%s mode=%s resume=%s",
                    run_id, group_url, self.config.mode, resume)

        self._register_signals()

        try:
            await self._startup(run_id)
            await self._run_pipeline(group_url, run_id, resume=resume)
        except asyncio.CancelledError:
            logger.info("Orchestrator cancelled — initiating graceful shutdown")
            await self.run_repo.finish(run_id, "CANCELLED")
        except Exception as e:
            logger.error("Orchestrator unhandled error: %s", e, exc_info=True)
            await self.run_repo.finish(run_id, "FAILED", error=str(e))
            raise
        finally:
            await self._shutdown()

        logger.info("Orchestrator finished run_id=%s", run_id)

    def request_shutdown(self) -> None:
        """Signal the orchestrator to stop gracefully."""
        if not self._shutdown_event.is_set():
            logger.info("Shutdown requested")
            self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Internal Pipeline
    # ------------------------------------------------------------------

    async def _startup(self, run_id: str) -> None:
        """Initialize pipeline queues, metrics, and workers."""
        logger.info("Starting pipeline components...")

        # 1. Queues
        self._queues = Queues(self.config.queues)

        # 2. Metrics counters
        self._counters = MetricsCounters()

        # 3. Worker pool
        self._worker_pool = WorkerPool()

        # 4. Metrics emitter
        self._metrics_emitter = MetricsEmitter(
            counters=self._counters,
            emit_every_sec=self.config.metrics.emit_every_seconds,
            queue_snapshot_fn=self._queues.snapshot,
        )
        self._start_background(self._metrics_emitter.run(), "metrics_emitter")

        # 5. Backpressure monitor
        self._bp_monitor = BackpressureMonitor(
            snapshot_fn=self._queues.snapshot,
            check_interval_sec=5.0,
        )
        self._start_background(self._bp_monitor.run(), "backpressure_monitor")

        logger.info("Pipeline components initialized")

    async def _run_pipeline(self, group_url: str, run_id: str, resume: bool = False) -> None:
        """Execute browser feed discovery and consumer workers."""
        # 1. Launch Browser & Context
        state_path = Path(self.config.browser.browser_state_path)
        if not state_path.exists():
            logger.error("Session state file not found at %s. Please run: python main.py auth", state_path)
            await self.run_repo.finish(run_id, "BLOCKED_AUTH", error="Missing session state")
            return

        self._playwright = await async_playwright().start()
        self._browser = await BrowserFactory.launch_browser(
            self._playwright,
            self.config.browser,
        )
        self._context = await BrowserFactory.create_context(
            self._browser,
            self.config.browser,
            state_path=state_path,
        )

        page = await self._context.new_page()

        # 2. Navigate directly to group and validate auth
        nav_url = group_url
        if "sorting_setting" not in nav_url and "/groups/" in nav_url:
            if "?" in nav_url:
                nav_url = f"{nav_url}&sorting_setting=CHRONOLOGICAL"
            else:
                nav_url = f"{nav_url.rstrip('/')}/?sorting_setting=CHRONOLOGICAL"
        logger.info("Navigating to group: %s", nav_url)
        try:
            await page.goto(nav_url, wait_until="networkidle", timeout=60_000)
        except Exception as e:
            logger.warning("Initial navigation to group URL hit: %s; continuing to check state", e)

        # Wait longer for headless browser to fully render Facebook
        await asyncio.sleep(5)

        # Retry auth check up to 3 times — headless may need extra time to settle
        auth_status = AuthStatus.UNKNOWN
        for attempt in range(3):
            auth_status = await check_auth_status(page)
            if auth_status == AuthStatus.OK:
                break
            if attempt < 2:
                logger.warning(
                    "Auth check attempt %d/3 returned %s — retrying in 3s...",
                    attempt + 1, auth_status,
                )
                await asyncio.sleep(3)

        if auth_status != AuthStatus.OK:
            logger.error(
                "Authentication check failed with status: %s. "
                "Please run 'python main.py auth' to refresh login.",
                auth_status,
            )
            await self.run_repo.finish(run_id, "BLOCKED_AUTH", error=f"Auth status: {auth_status}")
            return

        logger.info("Facebook authentication confirmed (status=OK)")

        # 3. Extract Group Metadata

        group_meta = await GroupExtractor.extract_metadata(page, group_url)
        group_slug = group_meta["slug"]
        group_id = group_meta["facebook_group_id"] or group_slug

        # Upsert group into storage
        await self.group_repo.upsert(group_meta)

        # Create Run record
        await self.run_repo.create(
            run_id=run_id,
            group_slug=group_slug,
            group_id=group_id,
            mode=self.config.mode,
        )

        # 3b. Setup Checkpoint Manager
        from collector.checkpoints.checkpoint_manager import CheckpointManager
        self.checkpoint_manager = CheckpointManager(
            checkpoint_repo=self.checkpoint_repo,
            group_slug=group_slug,
            group_id=group_id,
            mode=self.config.mode,
            run_id=run_id,
            config=self.config.checkpoint,
            counters=self._counters,
        )

        initial_consecutive_known = 0
        if resume:
            cp = await self.checkpoint_manager.load()
            if cp:
                initial_consecutive_known = self.checkpoint_manager.consecutive_known_posts
                logger.info(
                    "Resumed from checkpoint: last_post=%s, consecutive_known=%d, posts_seen=%d",
                    self.checkpoint_manager.last_post_id,
                    initial_consecutive_known,
                    self._counters.posts_discovered,
                )
            else:
                logger.info("Resume requested, but no checkpoint found for group=%s mode=%s",
                            group_slug, self.config.mode)

        self._start_background(self.checkpoint_manager.run(), "checkpoint_manager")

        # 4. Start PostWriterWorker, CommentWriterWorker, and MediaWorkers
        post_repo = PostRepo(self.layout, group_slug)
        writer = PostWriterWorker(
            name="post-writer-0",
            queue=self._queues.post_queue,
            counters=self._counters,
            layout=self.layout,
            group_slug=group_slug,
            group_id=group_id,
            media_queue=self._queues.media_queue,
            comment_job_queue=self._queues.comment_job_queue,
        )
        self._worker_pool.add(writer)

        # Comment Writer
        c_writer = CommentWriterWorker(
            name="comment-writer-0",
            queue=self._queues.comment_queue,
            counters=self._counters,
            layout=self.layout,
            group_slug=group_slug,
            media_queue=self._queues.media_queue,
        )
        self._worker_pool.add(c_writer)

        # Comment Workers (consume from comment_job_queue to extract comments)
        for i in range(self.config.workers.comment_workers):
            cw = CommentWorker(
                name=f"comment-worker-{i}",
                queue=self._queues.comment_job_queue,
                comment_queue=self._queues.comment_queue,
                counters=self._counters,
                context=self._context,
                layout=self.layout,
                group_slug=group_slug,
                config=self.config,
                media_queue=self._queues.media_queue,
            )
            self._worker_pool.add(cw)

        # Media Workers (consume from media_queue to download images/videos)
        for i in range(self.config.workers.media_workers):
            mw = MediaWorker(
                name=f"media-worker-{i}",
                queue=self._queues.media_queue,
                counters=self._counters,
                layout=self.layout,
                group_slug=group_slug,
                config=self.config.media,
            )
            self._worker_pool.add(mw)

        # Launch all workers in pool
        await self._worker_pool.start()

        # 5. Initialize DedupeManager and pre-warm in-memory cache
        from collector.pipeline.dedupe import DedupeManager
        dedupe_mgr = DedupeManager(self.layout, group_slug)
        await dedupe_mgr.warm_up()

        # 6. Start Feed Producer
        feed_producer = FeedProducer(
            page=page,
            config=self.config,
            post_queue=self._queues.post_queue,
            producer_gate=self._bp_monitor.gate,
            counters=self._counters,
            run_id=run_id,
            group_id=group_id,
            is_known_post_fn=dedupe_mgr.is_post_known,
            on_post_fn=self.checkpoint_manager.record_post,
            initial_consecutive_known=initial_consecutive_known,
        )

        logger.info("Feed discovery starting...")
        posts_found = await feed_producer.run(
            group_url=group_url,
            shutdown_event=self._shutdown_event,
        )
        logger.info("Feed discovery complete — discovered %d posts", posts_found)

        # Wait for downstream queues to drain what was already produced
        logger.info("Waiting for pipeline queues to finish processing...")
        try:
            await asyncio.wait_for(self._queues.post_queue.join(), timeout=30.0)
            await asyncio.wait_for(self._queues.comment_job_queue.join(), timeout=180.0)
            await asyncio.wait_for(self._queues.comment_queue.join(), timeout=60.0)
            await asyncio.wait_for(self._queues.media_queue.join(), timeout=120.0)
        except asyncio.TimeoutError:
            logger.warning("Pipeline queue drain timed out; proceeding to shutdown")
        except Exception as e:
            logger.warning("Pipeline queue drain encountered error: %s", e)

        # Trigger graceful shutdown to drain remaining items in queue
        self.request_shutdown()

        # Update run summary
        await self.run_repo.update(run_id, {
            "posts_found": posts_found,
            "posts_new": self._counters.posts_new,
            "comments_found": self._counters.comments_discovered,
            "comments_new": self._counters.comments_new,
            "media_found": self._counters.media_discovered,
            "media_downloaded": self._counters.media_downloaded,
        })
        await self.run_repo.finish(run_id, "COMPLETED")
        self._completed = True
        if self.checkpoint_manager:
            await self.checkpoint_manager.clear()

    async def _shutdown(self) -> None:
        """Graceful shutdown sequence in order."""
        logger.info("Shutdown: stopping background monitors...")
        if self._metrics_emitter:
            self._metrics_emitter.stop()
        if self._bp_monitor:
            self._bp_monitor.stop()

        # Shutdown checkpoint manager
        if self.checkpoint_manager:
            self.checkpoint_manager.stop()
            if not self._completed:
                try:
                    await asyncio.wait_for(
                        self.checkpoint_manager.save_now(status="interrupted"),
                        timeout=2.0,
                    )
                    logger.info("Saved shutdown checkpoint successfully")
                except Exception as e:
                    logger.warning("Failed saving shutdown checkpoint: %s", e)

        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        # Drain queues with sentinels
        if self._queues and self._worker_pool:
            logger.info("Shutdown: sending sentinels to drain queues...")
            await self._queues.drain_all({
                self._queues.post_queue: 1,
                self._queues.comment_job_queue: self.config.workers.comment_workers,
                self._queues.comment_queue: 1,
                self._queues.media_queue: self.config.workers.media_workers,
            })

        # Wait for workers to finish
        if self._worker_pool:
            logger.info("Shutdown: waiting for workers to stop...")
            await self._worker_pool.stop(timeout=15.0)

        # Close Browser and Playwright
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        # Final metrics flush
        if self._metrics_emitter:
            self._metrics_emitter.emit_now()

        logger.info("Shutdown complete")

    def _start_background(self, coro, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.append(task)
        return task

    def _register_signals(self) -> None:
        """Register SIGTERM and SIGINT handlers."""
        loop = asyncio.get_event_loop()

        def _handler(sig_name: str):
            logger.info("Signal %s received — requesting shutdown", sig_name)
            self.request_shutdown()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig.name: _handler(s))
            except NotImplementedError:
                pass
