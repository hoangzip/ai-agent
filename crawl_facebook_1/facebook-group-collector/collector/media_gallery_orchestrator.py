"""
collector/media_gallery_orchestrator.py — Orchestrator for /media gallery crawl.

Responsibilities:
- Launch browser with saved session
- Navigate to group /media page
- Run MediaGalleryCrawler to discover posts from photo grid
- For known posts: patch missing fields (posted_at, content, author)
- For new posts: run full crawl pipeline (comments + media download)
- Save updated posts back to JSON
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid

from playwright.async_api import async_playwright

from collector.config import CrawlerConfig
from collector.facebook.auth import AuthStatus, check_auth_status
from collector.facebook.browser import BrowserFactory
from collector.facebook.group import GroupExtractor
from collector.facebook.media_gallery import MediaGalleryCrawler
from collector.metrics.emitter import MetricsCounters, MetricsEmitter
from collector.pipeline.items import SENTINEL
from collector.pipeline.queues import Queues
from collector.pipeline.worker import WorkerPool
from collector.storage.layout import StorageLayout, slugify
from collector.storage.repository import GroupRepo, PostRepo, RunRepo
from collector.workers.comment_worker import CommentWorker
from collector.workers.media_worker import MediaWorker
from collector.writers.comment_writer import CommentWriterWorker
from collector.writers.post_writer import PostWriterWorker

logger = logging.getLogger(__name__)

GROUP_ID = "978769317924542"


class MediaGalleryOrchestrator:
    """Orchestrates crawling from the group /media photo grid."""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._shutdown_event = asyncio.Event()
        self.layout = StorageLayout(self.config.storage.data_dir)
        self.group_repo = GroupRepo(self.layout)
        self.run_repo = RunRepo(self.layout)
        self._playwright = None
        self._browser = None
        self._context = None

    def _setup_signals(self):
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except NotImplementedError:
                pass

    async def run(self, group_url: str, run_id: str) -> None:
        self._setup_signals()

        # Determine account / state path
        account = getattr(self.config, "account", "default") or "default"
        state_path = self.layout.root / "browser_state" / f"{account}.json"

        if not state_path.exists():
            logger.error("Browser state not found at %s. Run 'python main.py auth' first.", state_path)
            return

        # ------------------------------------------------------------------
        # 1. Launch browser
        # ------------------------------------------------------------------
        self._playwright = await async_playwright().start()
        self._browser = await BrowserFactory.launch_browser(
            self._playwright, self.config.browser, headless=self.config.browser.headless
        )
        self._context = await BrowserFactory.create_context(
            self._browser, self.config.browser, state_path=state_path
        )
        page = await self._context.new_page()

        # ------------------------------------------------------------------
        # 2. Auth check
        # ------------------------------------------------------------------
        nav_url = group_url.rstrip("/") + "/?sorting_setting=CHRONOLOGICAL"
        try:
            await page.goto(nav_url, wait_until="domcontentloaded", timeout=35_000)
        except Exception as e:
            logger.warning("Navigation hit: %s; continuing", e)
        await asyncio.sleep(3)

        auth_status = AuthStatus.UNKNOWN
        for attempt in range(3):
            auth_status = await check_auth_status(page)
            if auth_status == AuthStatus.OK:
                break
            if attempt < 2:
                logger.warning("Auth attempt %d/3: %s — retrying in 3s", attempt + 1, auth_status)
                await asyncio.sleep(3)

        if auth_status != AuthStatus.OK:
            logger.error("Auth failed: %s. Run 'python main.py auth'.", auth_status)
            return

        logger.info("Auth OK. Starting media gallery crawl...")

        # ------------------------------------------------------------------
        # 3. Group metadata & storage setup
        # ------------------------------------------------------------------
        group_meta = await GroupExtractor.extract_metadata(page, group_url)
        group_slug = group_meta["slug"]
        await self.group_repo.upsert(group_meta)
        self.layout.ensure_dirs(group_slug)

        # Build known-post lookup from existing JSON files
        posts_dir = self.layout.group_posts_dir(group_slug)
        known_fb_ids: dict[str, Path] = {}   # fb_post_id -> path
        known_post_urls: dict[str, Path] = {}  # post_url -> path

        for path in posts_dir.glob("*.json"):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                fb_id = d.get("facebook_post_id")
                post_url = d.get("post_url")
                if fb_id:
                    known_fb_ids[fb_id] = path
                if post_url:
                    known_post_urls[post_url] = path
            except Exception:
                pass

        logger.info("Loaded %d known posts from disk", len(known_fb_ids))

        def is_known_post(id_or_url: str) -> bool:
            return id_or_url in known_fb_ids or id_or_url in known_post_urls

        def patch_post(fb_post_id: str, patch: dict) -> None:
            """Update only null/missing fields in existing post JSON, and queue media if post lacks it."""
            path = known_fb_ids.get(fb_post_id)
            if not path or not path.exists():
                return
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                changed = False
                for key, value in patch.items():
                    if key == "media_urls":
                        continue
                    # Only fill in if field is currently null/missing
                    if data.get(key) is None and value is not None:
                        data[key] = value
                        changed = True
                if changed:
                    data["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                    path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    logger.debug("Patched post %s: %s", fb_post_id, list(patch.keys()))

                # If post has empty media_ids and media_urls are discovered, queue them!
                media_urls = patch.get("media_urls")
                if media_urls and not data.get("media_ids") and queues and queues.media_queue:
                    from collector.pipeline.items import MediaJobItem
                    post_internal_id = data["id"]
                    for pos, m_url in enumerate(media_urls):
                        queues.media_queue.put_nowait(MediaJobItem(
                            owner_type="post",
                            owner_id=post_internal_id,
                            post_id=post_internal_id,
                            source_url=m_url,
                            position=pos,
                            media_type="image",
                        ))
                    logger.info("Queued %d media items for known post %s (%s)", len(media_urls), fb_post_id, post_internal_id)
            except Exception as e:
                logger.warning("Failed to patch post %s: %s", fb_post_id, e)

        # ------------------------------------------------------------------
        # 4. Start pipeline for new posts (comments + media)
        # ------------------------------------------------------------------
        from collector.pipeline.queues import Queues
        from collector.pipeline.worker import WorkerPool
        from collector.metrics.emitter import MetricsCounters, MetricsEmitter
        from collector.storage.repository import PostRepo
        from collector.workers.comment_worker import CommentWorker
        from collector.workers.media_worker import MediaWorker
        from collector.writers.comment_writer import CommentWriterWorker
        from collector.writers.post_writer import PostWriterWorker

        queues = Queues(self.config.queues)
        counters = MetricsCounters()
        metrics = MetricsEmitter(
            counters=counters,
            emit_every_sec=self.config.metrics.emit_every_seconds,
            queue_snapshot_fn=queues.snapshot,
        )
        post_repo = PostRepo(self.layout, group_slug)

        worker_pool = WorkerPool()

        writer = PostWriterWorker(
            name="post-writer-0",
            queue=queues.post_queue,
            counters=counters,
            layout=self.layout,
            group_slug=group_slug,
            group_id=group_slug,
            media_queue=queues.media_queue,
            comment_job_queue=queues.comment_job_queue,
        )
        worker_pool.add(writer)

        c_writer = CommentWriterWorker(
            name="comment-writer-0",
            queue=queues.comment_queue,
            counters=counters,
            layout=self.layout,
            group_slug=group_slug,
            media_queue=queues.media_queue,
        )
        worker_pool.add(c_writer)

        for i in range(self.config.workers.comment_workers):
            cw = CommentWorker(
                name=f"comment-worker-{i}",
                queue=queues.comment_job_queue,
                comment_queue=queues.comment_queue,
                counters=counters,
                context=self._context,
                layout=self.layout,
                group_slug=group_slug,
                config=self.config,
                media_queue=queues.media_queue,
            )
            worker_pool.add(cw)

        for i in range(self.config.workers.media_workers):
            mw = MediaWorker(
                name=f"media-worker-{i}",
                queue=queues.media_queue,
                counters=counters,
                layout=self.layout,
                group_slug=group_slug,
                config=self.config.media,
            )
            worker_pool.add(mw)

        await worker_pool.start()
        metrics_task = asyncio.create_task(metrics.run())

        # ------------------------------------------------------------------
        # 5. Run MediaGalleryCrawler
        # ------------------------------------------------------------------
        crawler = MediaGalleryCrawler(
            page=page,
            group_url=group_url,
            group_slug=group_slug,
            is_known_post_fn=is_known_post,
            patch_post_fn=patch_post,
            post_queue=queues.post_queue,
            run_id=run_id,
            shutdown_event=self._shutdown_event,
        )

        summary = await crawler.run()
        logger.info("Gallery crawl complete: %s", summary)

        # ------------------------------------------------------------------
        # 6. Drain pipeline
        # ------------------------------------------------------------------
        logger.info("Waiting for pipeline to finish...")
        await queues.drain_all({
            queues.post_queue: 1,
            queues.comment_job_queue: self.config.workers.comment_workers,
            queues.comment_queue: 1,
            queues.media_queue: self.config.workers.media_workers,
        })
        await worker_pool.stop(timeout=15.0)
        metrics_task.cancel()

        # ------------------------------------------------------------------
        # 7. Cleanup
        # ------------------------------------------------------------------
        await self._context.close()
        await self._browser.close()
        await self._playwright.stop()

        logger.info(
            "MediaGalleryCrawler done — new=%d patched=%d skipped=%d",
            summary["new_posts_queued"],
            summary["existing_posts_patched"],
            summary["skipped_already_complete"],
        )
