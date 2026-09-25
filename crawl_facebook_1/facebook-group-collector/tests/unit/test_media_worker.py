"""
tests/unit/test_media_worker.py — Tests for MediaWorker and SHA-256 deduplication.
"""
import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.config import MediaConfig
from collector.downloaders.media_downloader import DownloadResult, MediaDownloader
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import MediaJobItem
from collector.storage.layout import StorageLayout
from collector.storage.repository import MediaRepo, PostRepo
from collector.workers.media_worker import MediaWorker


@pytest.mark.asyncio
async def test_media_worker_downloads_and_deduplicates(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    # Create post first
    post_repo = PostRepo(layout, group_slug)
    post_rec, _ = await post_repo.upsert({
        "group_slug": group_slug,
        "facebook_post_id": "p_with_media",
        "post_url": "https://facebook.com/groups/test_group/posts/p_with_media/",
    })
    post_id = post_rec["id"]

    queue = asyncio.Queue()
    counters = MetricsCounters()

    # Mock downloader
    mock_downloader = MagicMock()
    content = b"sample image binary data 987654321"
    sha = hashlib.sha256(content).hexdigest()

    mock_result = DownloadResult(
        content=content,
        sha256=sha,
        file_size=len(content),
        mime_type="image/jpeg",
        ext="jpg",
    )
    mock_downloader.download = AsyncMock(return_value=mock_result)

    worker = MediaWorker(
        name="test-media-worker",
        queue=queue,
        counters=counters,
        layout=layout,
        group_slug=group_slug,
        config=MediaConfig(),
        downloader=mock_downloader,
    )

    job1 = MediaJobItem(
        owner_type="post",
        owner_id=post_id,
        source_url="https://scontent.fbcdn.net/v/photo1.jpg",
        position=0,
    )

    # 1. First download
    await worker.process_item(job1)

    assert counters.media_downloaded == 1
    assert counters.media_deduped == 0

    # Verify post has media_id
    updated_post = await post_repo.get(post_id)
    assert len(updated_post["media_ids"]) == 1

    # 2. Second download with DIFFERENT URL but SAME content (SHA-256 deduplication!)
    job2 = MediaJobItem(
        owner_type="post",
        owner_id=post_id,
        source_url="https://scontent.fbcdn.net/v/photo2_duplicate.jpg",
        position=1,
    )

    await worker.process_item(job2)

    # Downloaded count stays 1, deduped count increases by 1!
    assert counters.media_downloaded == 1
    assert counters.media_deduped == 1
