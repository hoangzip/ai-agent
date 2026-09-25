"""
tests/unit/test_comments_extractor.py — Tests for CommentExtractor and reply tree parsing.
All tests use mocked Playwright Page and elements (no network calls).
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.facebook.comments import CommentExtractor, extract_comment_id_from_url
from collector.facebook.selectors import CommentSelectors
from collector.pipeline.items import CommentItem


def test_extract_comment_id_from_url():
    assert extract_comment_id_from_url("https://www.facebook.com/groups/1/posts/2/?comment_id=123456789") == "123456789"
    assert extract_comment_id_from_url("https://www.facebook.com/groups/1/posts/2/?reply_comment_id=987654321&comment_id=111") == "987654321"
    assert extract_comment_id_from_url("https://www.facebook.com/comment_id/555666") == "555666"
    assert extract_comment_id_from_url("https://www.facebook.com/groups/1/posts/2/") is None


def create_mock_comment_el(cid: str, author: str, text: str, is_reply: bool = False, reply_els=None):
    el = MagicMock()

    author_el = MagicMock()
    author_el.inner_text = AsyncMock(return_value=author)

    link_el = MagicMock()
    link_el.get_attribute = AsyncMock(return_value=f"https://www.facebook.com/profile.php?id={cid}_user")

    text_el = MagicMock()
    text_el.inner_text = AsyncMock(return_value=text)

    ts_el = MagicMock()
    ts_el.get_attribute = AsyncMock(side_effect=lambda attr: f"https://facebook.com/?comment_id={cid}" if attr == "href" else "1695500000")
    ts_el.inner_text = AsyncMock(return_value="10 phút")

    async def mock_qs(selector):
        if selector == CommentSelectors.COMMENT_AUTHOR:
            return author_el
        if selector == CommentSelectors.COMMENT_AUTHOR_LINK:
            return link_el
        if selector == CommentSelectors.COMMENT_TEXT:
            return text_el
        if selector == CommentSelectors.COMMENT_TIMESTAMP:
            return ts_el
        return None

    async def mock_qsa(selector):
        if selector == CommentSelectors.VIEW_REPLIES_BUTTON:
            return []
        if selector == CommentSelectors.REPLY_ITEMS:
            return reply_els or []
        return []

    el.query_selector = AsyncMock(side_effect=mock_qs)
    el.query_selector_all = AsyncMock(side_effect=mock_qsa)
    return el


@pytest.mark.asyncio
async def test_comment_extractor_hierarchical_tree():
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=None)  # no "view more" button

    # Reply element
    reply_el = create_mock_comment_el(
        cid="rep_1",
        author="Reply User",
        text="This is a reply to top comment",
        is_reply=True,
    )

    # Top level comment element containing reply
    top_el = create_mock_comment_el(
        cid="top_1",
        author="Top User",
        text="This is top-level comment",
        is_reply=False,
        reply_els=[reply_el],
    )

    page.query_selector_all = AsyncMock(return_value=[top_el])

    extractor = CommentExtractor(page)
    results = await extractor.extract_comments_tree(post_internal_id="post-uuid-1")

    assert len(results) == 2

    # Verify top-level comment
    top = results[0]
    assert top.facebook_comment_id == "top_1"
    assert top.author_display_name == "Top User"
    assert top.content == "This is top-level comment"
    assert top.depth == 0
    assert top.parent_comment_id is None

    # Verify reply comment
    reply = results[1]
    assert reply.facebook_comment_id == "rep_1"
    assert reply.author_display_name == "Reply User"
    assert reply.content == "This is a reply to top comment"
    assert reply.depth == 1
    assert reply.parent_comment_id == "top_1"


@pytest.mark.asyncio
async def test_comment_extractor_delta_stop_condition():
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=None)

    c1 = create_mock_comment_el(cid="known_c1", author="User 1", text="Text 1")
    c2 = create_mock_comment_el(cid="known_c2", author="User 2", text="Text 2")
    c3 = create_mock_comment_el(cid="known_c3", author="User 3", text="Text 3")

    page.query_selector_all = AsyncMock(return_value=[c1, c2, c3])

    extractor = CommentExtractor(page, known_comment_threshold=2)

    def is_known(cid: str) -> bool:
        return cid in ("known_c1", "known_c2", "known_c3")

    results = await extractor.extract_comments_tree(
        post_internal_id="post-uuid-2",
        is_known_comment_fn=is_known,
    )

    # Should stop after reaching threshold of 2 known comments
    assert len(results) == 2
