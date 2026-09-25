"""
scripts/login_facebook.py — Interactive Facebook Login Helper.
Opens a clean Chrome window to facebook.com/login, waits for user to log in,
and automatically exports valid cookies to data/browser_state/default.json.
"""
import asyncio
import json
import logging
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.storage.layout import StorageLayout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("login")


async def main():
    config = load_config()
    state_file = Path("data/browser_state/default.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright

    logger.info("Opening Chrome browser for Facebook login...")
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850},
            locale="vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        page = await context.new_page()

        logger.info("Navigating to https://www.facebook.com/login ...")
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        logger.info("==================================================================")
        logger.info(">> VUI LÒNG ĐĂNG NHẬP FACEBOOK TRÊN CỬA SỔ TRÌNH DUYỆT VỪA MỞ <<")
        logger.info("Tool đang tự động chờ bạn đăng nhập thành công...")
        logger.info("==================================================================")

        # Poll every 2 seconds until c_user cookie is present
        logged_in = False
        for _ in range(150):  # Wait up to 5 minutes (300 seconds)
            await asyncio.sleep(2.0)
            cookies = await context.cookies()
            c_user = next((c for c in cookies if c.get("name") == "c_user"), None)
            xs = next((c for c in cookies if c.get("name") == "xs"), None)

            if c_user and xs:
                # Give Facebook 3 seconds to stabilize session
                await asyncio.sleep(3.0)
                await context.storage_state(path=str(state_file))
                logger.info("ĐĂNG NHẬP THÀNH CÔNG! UID = %s", c_user.get("value"))
                logger.info("Đã lưu session state vào: %s", state_file.resolve())
                logged_in = True
                break

        if not logged_in:
            logger.warning("Hết thời gian chờ đăng nhập (5 phút).")
        else:
            logger.info("Hoàn tất! Đóng trình duyệt sau 3 giây...")
            await asyncio.sleep(3.0)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
