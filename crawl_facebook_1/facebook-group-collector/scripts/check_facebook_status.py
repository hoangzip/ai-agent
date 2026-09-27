"""
scripts/check_facebook_status.py — Quickly check if the Facebook session is healthy
and if photos in the group can be opened without rate limit.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from playwright.async_api import async_playwright

async def main():
    config = load_config("config/crawler.yaml")
    browser_state = "data/browser_state/default.json"
    
    test_photo_url = "https://web.facebook.com/photo/?fbid=122124554558691997&set=g.580277503401606"
    group_media_url = "https://web.facebook.com/groups/580277503401606/media"
    
    print("Launching browser check...")
    sys.stdout.flush()
    
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
        context = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await context.new_page()
        
        # 1. Check the photo URL from user screenshot
        print(f"Testing photo URL: {test_photo_url}")
        sys.stdout.flush()
        
        await page.goto(test_photo_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.5)
        
        body_text = await page.inner_text("body")
        is_blocked = "Temporarily Blocked" in body_text or "bị chặn tạm thời" in body_text.lower()
        title = await page.title()
        
        print(f"-> Page Title: {title}")
        print(f"-> Temporarily Blocked?: {is_blocked}")
        sys.stdout.flush()
        
        # 2. Check the group media gallery
        print(f"\nTesting media gallery URL: {group_media_url}")
        sys.stdout.flush()
        
        await page.goto(group_media_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.5)
        
        body_media = await page.inner_text("body")
        is_blocked_media = "Temporarily Blocked" in body_media or "bị chặn tạm thời" in body_media.lower()
        photos = await page.query_selector_all("a[href*='/photo/'], a[href*='photo.php'], a[href*='fbid=']")
        
        print(f"-> Media Page Title: {await page.title()}")
        print(f"-> Media Gallery Blocked?: {is_blocked_media}")
        print(f"-> Photos visible in gallery: {len(photos)}")
        sys.stdout.flush()
        
        await browser.close()
        
        if not is_blocked and not is_blocked_media and len(photos) > 0:
            print("\nSTATUS: ALL CLEAR! The Facebook session is normal and photos load successfully.")
        else:
            print("\nSTATUS: STILL RESTRICTED. Please wait a bit longer.")
        sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
