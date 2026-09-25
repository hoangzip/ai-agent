import asyncio
from playwright.async_api import async_playwright
from collector.facebook.browser import BrowserFactory
from collector.config import load_config
from collector.pipeline.normalizer import clean_facebook_url
import re

POST_ID_RE = re.compile(r"/(?:posts|permalink)/(\d+)")

async def extract_current_photo_info(page):
    post_url = None
    post_id = None
    timestamp_str = None
    
    # Reset mouse to trigger fresh mouseenter
    await page.mouse.move(0, 0)
    await asyncio.sleep(0.3)

    ts_link = await page.query_selector("a[target='_blank'][href*='__tn__']")
    if ts_link:
        await ts_link.hover()
        await asyncio.sleep(1.2)
        raw_href = await ts_link.get_attribute("href")
        if raw_href and ("posts/" in raw_href or "permalink/" in raw_href):
            post_url = clean_facebook_url(raw_href)
            m = POST_ID_RE.search(post_url)
            if m:
                post_id = m.group(1)
                
        # Read tooltip
        tooltips = await page.evaluate('''() => {
            const res = [];
            for (let el of document.querySelectorAll("div[role='tooltip']")) {
                const t = el.innerText.trim();
                if (t) res.push(t);
            }
            return res;
        }''')
        if tooltips:
            timestamp_str = tooltips[0]

    # Author
    author_el = await page.query_selector("h2 a[href*='/user/'], a[role='link'][href*='/user/']")
    author_name = None
    author_url = None
    if author_el:
        author_name = (await author_el.inner_text()).strip()
        raw_author_href = await author_el.get_attribute("href")
        author_url = clean_facebook_url(raw_author_href) if raw_author_href else None

    # Image
    img_el = await page.query_selector("div[data-pagelet='MediaViewerPhoto'] img, img[data-visualcompletion='media-vc-image']")
    img_src = None
    if img_el:
        img_src = await img_el.get_attribute("src")

    return {
        "viewer_url": page.url,
        "post_id": post_id,
        "post_url": post_url,
        "author_name": author_name,
        "author_url": author_url,
        "timestamp_str": timestamp_str,
        "has_img": bool(img_src),
        "img_src": (img_src[:80] + "...") if img_src else None
    }

async def test():
    config = load_config("config/crawler.yaml")
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        ctx = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
        page = await ctx.new_page()
        await page.goto("https://web.facebook.com/groups/978769317924542/media", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # Click first photo
        first_photo = await page.query_selector("a[href*='set=g.978769317924542']")
        await first_photo.click()
        await asyncio.sleep(3)
        
        for step in range(3):
            info = await extract_current_photo_info(page)
            print(f"Step {step + 1}:", info)
            print("Pressing ArrowRight...")
            await page.keyboard.press("ArrowRight")
            await asyncio.sleep(2.5)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
