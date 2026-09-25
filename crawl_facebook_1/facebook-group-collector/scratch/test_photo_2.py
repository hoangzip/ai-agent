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
        # Direct goto photo 2:
        await page.goto("https://web.facebook.com/photo/?fbid=1122754740437725&set=g.978769317924542", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        
        info = await page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll("a[href]")).map(a => ({
                href: a.href,
                text: a.innerText.trim(),
                target: a.getAttribute("target"),
                aria: a.getAttribute("aria-label")
            }));
            return links.filter(l => l.href.includes("978769317924542") || l.href.includes("/posts/") || l.href.includes("/permalink/") || l.href.includes("__tn__"));
        }''')
        print(f"Links on photo 2 ({len(info)}):")
        for l in info:
            print(" ", l)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
