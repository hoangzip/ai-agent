import asyncio
from playwright.async_api import async_playwright
from collector.facebook.browser import BrowserFactory
from collector.config import load_config

async def test():
    config = load_config("config/crawler.yaml")
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        ctx = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
        page = await ctx.new_page()
        await page.goto("https://web.facebook.com/photo/?fbid=958370540642680&set=g.978769317924542", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        
        # Find the target="_blank" timestamp link next to author
        ts_link = await page.query_selector("a[target='_blank'][href*='__tn__']")
        if ts_link:
            print("Found ts_link, hovering...")
            await ts_link.hover()
            await asyncio.sleep(1.5)
            
            # Check tooltips
            tooltips = await page.evaluate('''() => {
                const res = [];
                for (let el of document.querySelectorAll("div[role='tooltip']")) {
                    res.push(el.innerText);
                }
                return res;
            }''')
            print("Tooltips:", tooltips)
            
            # Also check href
            href = await ts_link.get_attribute("href")
            print("href:", href)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
