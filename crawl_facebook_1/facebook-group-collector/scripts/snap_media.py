import asyncio
from playwright.async_api import async_playwright

async def snap():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(storage_state="data/browser_state/default.json", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        for g in ["kiemtranoxau", "1178898519573483"]:
            url = f"https://www.facebook.com/groups/{g}/media"
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check subtabs under media
            subtabs = await page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll("a[role='tab'], a[href*='/media/']"));
                return links.map(a => ({ text: a.innerText.trim(), href: a.href }));
            }""")
            print(f"=== {g} subtabs ===")
            for t in subtabs:
                print("  Tab:", t)

            # Screenshot
            snap_path = f"/Users/hoangtq13/.gemini/antigravity-ide/brain/1097a3d2-550c-4360-ab0c-795e9eb07038/{g}_media.png"
            await page.screenshot(path=snap_path, full_page=False)
            print(f"Saved screenshot to {snap_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(snap())
