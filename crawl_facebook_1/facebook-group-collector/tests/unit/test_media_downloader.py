"""
tests/unit/test_media_downloader.py — Tests for MediaDownloader and file saving.
"""
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from collector.downloaders.media_downloader import DownloadResult, MediaDownloader
from collector.storage.layout import StorageLayout


@pytest.mark.asyncio
async def test_media_downloader_save_to_disk_sharded(tmp_path: Path):
    layout = StorageLayout(str(tmp_path))
    content = b"fake image bytes content for testing 12345"
    sha = hashlib.sha256(content).hexdigest()

    result = DownloadResult(
        content=content,
        sha256=sha,
        file_size=len(content),
        mime_type="image/jpeg",
        ext="jpg",
    )

    saved_path = await MediaDownloader.save_to_disk(layout, result)
    assert saved_path.exists()
    assert saved_path.read_bytes() == content

    # Verify sharding by first 4 characters: media/assets/ab/cd/abcd...jpg
    shard1 = sha[:2]
    shard2 = sha[2:4]
    expected_rel = Path("media") / "assets" / shard1 / shard2 / f"{sha}.jpg"
    assert str(expected_rel) in str(saved_path)

    # Calling save_to_disk again on existing file is idempotent
    second_path = await MediaDownloader.save_to_disk(layout, result)
    assert second_path == saved_path
