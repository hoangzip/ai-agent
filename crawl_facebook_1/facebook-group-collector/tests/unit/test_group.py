"""
tests/unit/test_group.py — Tests for Group metadata extraction and parsing.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.facebook.group import (
    GroupExtractor,
    extract_group_id_from_url,
    parse_member_count,
)
from collector.facebook.selectors import GroupSelectors


def test_parse_member_count():
    assert parse_member_count("12,5K thành viên") == 12500
    assert parse_member_count("1.2M members") == 1200000
    assert parse_member_count("350 người") == 350
    assert parse_member_count("1.450 thành viên") == 1450
    assert parse_member_count("50") == 50
    assert parse_member_count("Invalid string") is None
    assert parse_member_count("") is None


def test_extract_group_id_from_url():
    assert extract_group_id_from_url("https://www.facebook.com/groups/123456789/") == "123456789"
    assert extract_group_id_from_url("https://www.facebook.com/groups/tech-slug?ref=share") == "tech-slug"
    assert extract_group_id_from_url("https://www.facebook.com/other/path") is None


@pytest.mark.asyncio
async def test_group_extractor_metadata():
    page = MagicMock()
    page.url = "https://www.facebook.com/groups/123456789/"

    # Mock query_selector for name
    name_mock = MagicMock()
    name_mock.inner_text = AsyncMock(return_value="Python Vietnam Developers")

    # Mock members link
    members_mock = MagicMock()
    members_mock.inner_text = AsyncMock(return_value="55,2K thành viên")

    # Mock header spans for privacy
    span_mock = MagicMock()
    span_mock.inner_text = AsyncMock(return_value="Nhóm Công khai · 55,2K thành viên")

    async def mock_qs(selector):
        if selector == GroupSelectors.GROUP_NAME:
            return name_mock
        if selector == GroupSelectors.MEMBERS_LINK:
            return members_mock
        return None

    async def mock_qsa(selector):
        if selector == GroupSelectors.HEADER_INFO:
            return [span_mock]
        return []

    page.query_selector = AsyncMock(side_effect=mock_qs)
    page.query_selector_all = AsyncMock(side_effect=mock_qsa)

    meta = await GroupExtractor.extract_metadata(page, "https://www.facebook.com/groups/123456789/")
    assert meta["facebook_group_id"] == "123456789"
    assert meta["group_name"] == "Python Vietnam Developers"
    assert meta["privacy"] == "PUBLIC"
    assert meta["member_count"] == 55200
