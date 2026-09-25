"""
tests/unit/test_normalizer.py — Tests for PostNormalizer and extraction helpers.
"""
from datetime import datetime, timezone
import pytest

from collector.pipeline.normalizer import (
    PostNormalizer,
    clean_facebook_url,
    extract_post_id,
    extract_user_id,
    parse_count,
    parse_timestamp,
)


def test_clean_facebook_url():
    url = "https://www.facebook.com/groups/123456/posts/7891011/?__cft__[0]=AZX...&__tn__=%2CO%2CP-R"
    cleaned = clean_facebook_url(url)
    assert "__cft__" not in cleaned
    assert "__tn__" not in cleaned
    assert "7891011" in cleaned


def test_clean_facebook_url_preserves_story_fbid():
    url = "https://www.facebook.com/permalink.php?story_fbid=987654&id=123456&__cft__=xyz"
    cleaned = clean_facebook_url(url)
    assert "story_fbid=987654" in cleaned
    assert "id=123456" in cleaned
    assert "__cft__" not in cleaned


def test_extract_post_id():
    assert extract_post_id("https://www.facebook.com/groups/tech/posts/123456789/") == "123456789"
    assert extract_post_id("https://www.facebook.com/groups/tech/permalink/987654321/") == "987654321"
    assert extract_post_id("https://www.facebook.com/permalink.php?story_fbid=555666&id=123") == "555666"
    assert extract_post_id("https://www.facebook.com/home.php") is None


def test_extract_user_id():
    assert extract_user_id("https://www.facebook.com/profile.php?id=1000123456") == "1000123456"
    assert extract_user_id("https://www.facebook.com/user/1000987654/") == "1000987654"
    assert extract_user_id("https://www.facebook.com/johndoe/") is None


def test_parse_count():
    assert parse_count("45 bình luận") == 45
    assert parse_count("1,5K comments") == 1500
    assert parse_count("2.3M lượt thích") == 2300000
    assert parse_count("0 comments") == 0
    assert parse_count("") is None


def test_parse_timestamp():
    # Unix timestamp
    dt = parse_timestamp("1695500000")
    assert isinstance(dt, datetime)
    assert dt.tzinfo == timezone.utc

    # Relative time
    now_dt = parse_timestamp(None, "15 phút trước")
    assert isinstance(now_dt, datetime)

    hours_dt = parse_timestamp(None, "2 giờ")
    assert isinstance(hours_dt, datetime)


def test_normalize_feed_card():
    raw = {
        "post_url": "https://www.facebook.com/groups/123/posts/456789/?ref=share",
        "author_display_name": "Nguyen Van A",
        "author_profile_url": "https://www.facebook.com/profile.php?id=999888&ref=hovercard",
        "content_preview": "This is a great post about AI.\nSecond line of content.",
        "utime": "1695555555",
        "comment_count_text": "34 bình luận",
        "media_urls": ["https://scontent.xx.fbcdn.net/v/photo.jpg?__nc_cat=1"],
    }

    item = PostNormalizer.normalize_feed_card(raw, run_id="run-1", group_id="group-123")
    assert item is not None
    assert item.facebook_post_id == "456789"
    assert item.author_display_name == "Nguyen Van A"
    assert item.author_facebook_user_id == "999888"
    assert item.title == "This is a great post about AI."
    assert item.title_source == "derived"
    assert item.source_comment_count == 34
    assert len(item.media_urls_preview) == 1
    assert item.has_identifier() is True
