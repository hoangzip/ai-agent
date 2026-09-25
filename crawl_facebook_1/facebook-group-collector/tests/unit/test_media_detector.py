"""
tests/unit/test_media_detector.py — Tests for media URL filtering and DOM detection.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.facebook.media import MediaDetector, is_content_media_url


def test_is_content_media_url():
    # Valid media URLs
    assert is_content_media_url("https://scontent.fhan1-1.fna.fbcdn.net/v/t39.30808-6/456_n.jpg?stp=dst-jpg&_nc_cat=1") is True
    assert is_content_media_url("https://video.fhan1-1.fna.fbcdn.net/v/t42.1790-2/vid.mp4") is True
    assert is_content_media_url("https://www.facebook.com/photo.php?fbid=123") is True

    # Ignored URLs (emojis, UI sprites, blank gifs, data URIs)
    assert is_content_media_url("https://static.xx.fbcdn.net/rsrc.php/v3/yZ/r/ui_icon.png") is False
    assert is_content_media_url("https://static.xx.fbcdn.net/images/emoji.php/v9/t51/1/16/1f600.png") is False
    assert is_content_media_url("data:image/png;base64,iVBORw0KGgo...") is False
    assert is_content_media_url("https://example.com/other.png") is False
    assert is_content_media_url("") is False
    assert is_content_media_url(None) is False


@pytest.mark.asyncio
async def test_media_detector_extract_post_media():
    element = MagicMock()

    # Mock 2 images: 1 genuine post image, 1 emoji
    img1 = MagicMock()
    img1.get_attribute = AsyncMock(return_value="https://scontent.fbcdn.net/v/t39/photo1.jpg?__cft__=123")

    img2 = MagicMock()
    img2.get_attribute = AsyncMock(return_value="https://static.xx.fbcdn.net/rsrc.php/sprite.png")

    element.query_selector_all = AsyncMock(side_effect=lambda sel: [img1, img2] if sel == "img" else [])

    results = await MediaDetector.extract_post_media(element)
    assert len(results) == 1
    assert "photo1.jpg" in results[0]["source_url"]
    assert results[0]["media_type"] == "image"
    assert "__cft__" not in results[0]["source_url"]
