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
        
        info = await page.evaluate("""() => {
            // Find all elements that look like comments or post text
            const articles = Array.from(document.querySelectorAll("div[role='article']")).map(a => a.innerText);
            const main = document.querySelector("div[role='main']") ? document.querySelector("div[role='main']").innerText : "";
            const complementary = document.querySelector("div[role='complementary']") ? document.querySelector("div[role='complementary']").innerText : "";
            
            return {
                bodyText: document.body.innerText.slice(0, 3000),
                articlesCount: articles.length,
                articles: articles.slice(0, 5)
            };
        }""")
        print("BODY TEXT:\n", info.get("bodyText"))
        print("ARTICLES:\n", info.get("articles"))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
