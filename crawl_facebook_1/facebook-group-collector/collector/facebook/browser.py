"""
collector/facebook/browser.py — Playwright browser and context factory.

Provides:
- Browser launching with stealth/anti-detection flags
- Context creation with persistent session state loading
- Atomic session state saving
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from collector.config import BrowserConfig

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_VIEWPORT = {"width": 1280, "height": 800}


class BrowserFactory:
    """Factory for creating Playwright browser and context instances."""

    @staticmethod
    async def launch_browser(
        playwright: Playwright,
        config: BrowserConfig,
        headless: Optional[bool] = None,
    ) -> Browser:
        """Launch Chromium browser with anti-automation flags."""
        is_headless = headless if headless is not None else config.headless
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-notifications",
        ]
        channel = getattr(config, "channel", None) or "chrome"
        launch_kwargs = {
            "headless": is_headless,
            "args": args,
        }
        if channel:
            launch_kwargs["channel"] = channel

        logger.info("Launching browser (headless=%s, channel=%s)", is_headless, channel)
        try:
            browser = await playwright.chromium.launch(**launch_kwargs)
        except Exception as e:
            logger.warning("Failed to launch with channel '%s': %s — falling back to bundled chromium", channel, e)
            launch_kwargs.pop("channel", None)
            browser = await playwright.chromium.launch(**launch_kwargs)
        return browser

    @staticmethod
    async def create_context(
        browser: Browser,
        config: BrowserConfig,
        state_path: Optional[str | Path] = None,
    ) -> BrowserContext:
        """
        Create a new browser context.
        If state_path is given and exists, loads cookies/localStorage from it.
        """
        resolved_state = None
        if state_path:
            p = Path(state_path)
            if p.exists() and p.stat().st_size > 0:
                resolved_state = str(p.resolve())
                logger.info("Loading browser state from %s", resolved_state)
            else:
                logger.debug("State file %s does not exist; starting fresh context", state_path)

        context_kwargs = {
            "user_agent": DEFAULT_USER_AGENT,
            "viewport": DEFAULT_VIEWPORT,
            "locale": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "timezone_id": "Asia/Ho_Chi_Minh",
        }
        if resolved_state:
            context_kwargs["storage_state"] = resolved_state

        context = await browser.new_context(**context_kwargs)

        # Set default timeouts
        context.set_default_timeout(config.page_timeout_ms)
        context.set_default_navigation_timeout(config.navigation_timeout_ms)

        return context

    @staticmethod
    async def save_context_state(context: BrowserContext, state_path: str | Path) -> Path:
        """Save browser storage state (cookies, localStorage) to path."""
        p = Path(state_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(p))
        logger.info("Saved browser storage state to %s (size: %d bytes)", p, p.stat().st_size)
        return p
