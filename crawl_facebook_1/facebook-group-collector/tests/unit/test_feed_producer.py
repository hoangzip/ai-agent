"""
tests/unit/test_feed_producer.py — Tests for FeedProducer.
All tests use mocked Playwright Page and elements (no real browser/network).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.config import CrawlerConfig, LimitsConfig, IncrementalConfig
from collector.facebook.feed import FeedProducer
from collector.facebook.selectors import FeedSelectors
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.backpressure import ProducerGate


def create_mock_card(post_id: str, title: str):
    card = MagicMock()

    link_el = MagicMock()
    link_el.get_attribute = AsyncMock(return_value=f"https://www.facebook.com/groups/1/posts/{post_id}/")

    content_el = MagicMock()
    content_el.inner_text = AsyncMock(return_value=title)

    async def mock_qs(selector):
        if selector == FeedSelectors.POST_LINK:
            return link_el
        if selector == FeedSelectors.CONTENT_PREVIEW:
            return content_el
        return None

    card.query_selector = AsyncMock(side_effect=mock_qs)
    card.query_selector_all = AsyncMock(return_value=[])
    return card


@pytest.mark.asyncio
async def test_feed_producer_discovers_and_queues_posts():
    config = CrawlerConfig()
    post_queue = asyncio.Queue()
    producer_gate = ProducerGate()
    counters = MetricsCounters()
    shutdown_event = asyncio.Event()

    # Mock page
    page = MagicMock()
    page.url = "https://www.facebook.com/groups/test_group/"
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()

    card1 = create_mock_card("101", "First post content")
    card2 = create_mock_card("102", "Second post content")

    page.query_selector_all = AsyncMock(side_effect=[
        [card1, card2],
        [], [], [], [], []  # empty scrolls to trigger end of feed
    ])

    producer = FeedProducer(
        page=page,
        config=config,
        post_queue=post_queue,
        producer_gate=producer_gate,
        counters=counters,
        run_id="run-test",
    )

    found = await producer.run("https://www.facebook.com/groups/test_group/", shutdown_event)
    assert found == 2
    assert post_queue.qsize() == 2
    assert counters.posts_discovered == 2

    item1 = await post_queue.get()
    assert item1.facebook_post_id == "101"
    assert item1.title == "First post content"

    item2 = await post_queue.get()
    assert item2.facebook_post_id == "102"


@pytest.mark.asyncio
async def test_feed_producer_stops_at_max_posts():
    config = CrawlerConfig(limits=LimitsConfig(max_posts=2))
    post_queue = asyncio.Queue()
    producer_gate = ProducerGate()
    counters = MetricsCounters()
    shutdown_event = asyncio.Event()

    page = MagicMock()
    page.url = "https://www.facebook.com/groups/test_group/"
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()

    card1 = create_mock_card("201", "Post 1")
    card2 = create_mock_card("202", "Post 2")
    card3 = create_mock_card("203", "Post 3")

    page.query_selector_all = AsyncMock(return_value=[card1, card2, card3])

    producer = FeedProducer(
        page=page,
        config=config,
        post_queue=post_queue,
        producer_gate=producer_gate,
        counters=counters,
        run_id="run-test",
    )

    found = await producer.run("https://www.facebook.com/groups/test_group/", shutdown_event)
    assert found == 2
    assert post_queue.qsize() == 2


@pytest.mark.asyncio
async def test_feed_producer_incremental_mode_stop_condition():
    config = CrawlerConfig(
        mode="incremental",
        incremental=IncrementalConfig(stop_after_consecutive_known_posts=2),
    )
    post_queue = asyncio.Queue()
    producer_gate = ProducerGate()
    counters = MetricsCounters()
    shutdown_event = asyncio.Event()

    page = MagicMock()
    page.url = "https://www.facebook.com/groups/test_group/"
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()

    card1 = create_mock_card("9001", "Known 1")
    card2 = create_mock_card("9002", "Known 2")

    page.query_selector_all = AsyncMock(return_value=[card1, card2])

    def mock_is_known(ident: str) -> bool:
        return ident in ("9001", "9002")

    producer = FeedProducer(
        page=page,
        config=config,
        post_queue=post_queue,
        producer_gate=producer_gate,
        counters=counters,
        run_id="run-test",
        is_known_post_fn=mock_is_known,
    )

    found = await producer.run("https://www.facebook.com/groups/test_group/", shutdown_event)
    assert found == 2
    assert producer._consecutive_known >= 2
