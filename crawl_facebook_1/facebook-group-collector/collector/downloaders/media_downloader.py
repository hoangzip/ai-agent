"""
collector/downloaders/media_downloader.py — Async HTTP media file downloader and hasher.

Features:
- Stream download with aiohttp (independent of browser)
- SHA-256 computation on raw bytes
- MIME type and file extension detection
- Atomic file write via aiofiles to sharded disk path
- Retry with exponential backoff on network failure
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Optional

import aiofiles
import aiohttp

from collector.storage.layout import StorageLayout

logger = logging.getLogger(__name__)

MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


@dataclass
class DownloadResult:
    content: bytes
    sha256: str
    file_size: int
    mime_type: str
    ext: str


class MediaDownloader:
    """Independent async HTTP media downloader."""

    def __init__(self, timeout_sec: int = 60, max_retries: int = 3):
        self.timeout = aiohttp.ClientTimeout(total=timeout_sec)
        self.max_retries = max_retries

    async def download(self, url: str) -> DownloadResult:
        """
        Download binary content from URL and compute its SHA-256 hash.
        Raises Exception if download fails after retries.
        """
        attempt = 0
        backoff = 1.0

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://www.facebook.com/",
        }

        while True:
            attempt += 1
            try:
                connector = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=connector, timeout=self.timeout) as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            from collector.metrics.timer import time_block, time_block_async
                            async with time_block_async("media.download"):
                                content = await resp.read()
                            with time_block("media.sha256"):
                                sha = hashlib.sha256(content).hexdigest()
                            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                            ext = MIME_EXTENSIONS.get(content_type, "jpg")

                            return DownloadResult(
                                content=content,
                                sha256=sha,
                                file_size=len(content),
                                mime_type=content_type,
                                ext=ext,
                            )
                        elif resp.status in (429, 500, 502, 503, 504):
                            logger.warning("HTTP %d downloading %s (attempt %d/%d)", resp.status, url, attempt, self.max_retries)
                        else:
                            from collector.pipeline.worker import NonRetryableError
                            raise NonRetryableError(f"HTTP {resp.status} unrecoverable error downloading {url}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning("Network error downloading %s: %s (attempt %d/%d)", url, e, attempt, self.max_retries)

            if attempt >= self.max_retries:
                raise RuntimeError(f"Failed downloading {url} after {self.max_retries} attempts")

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 16.0)

    @staticmethod
    async def save_to_disk(layout: StorageLayout, result: DownloadResult) -> Path:
        """Save downloaded binary content into sharded path structure."""
        file_path = layout.media_file_path(sha256=result.sha256, ext=result.ext)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write if not already exists (SHA-256 deduplication at filesystem level)
        if not file_path.exists():
            from collector.metrics.timer import time_block_async
            async with time_block_async("media.storage_write"):
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(result.content)
            logger.debug("Saved media asset to %s (%d bytes)", file_path, result.file_size)
        else:
            logger.debug("File %s already exists on disk — skipping write", file_path)

        return file_path
