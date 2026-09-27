import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(storage_state="data/browser_state/default.json", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        for g in ["kiemtranoxau", "1178898519573483"]:
            url = f"https://www.facebook.com/groups/{g}/media"
            print(f"\n=================== Group: {g} ===================", flush=True)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Dismiss dialogs
            await page.evaluate("""() => {
                for (let d of document.querySelectorAll("div[role='dialog']")) {
                    if (d.innerText.includes('daily limit') || d.innerText.includes('Notifications') || d.innerText.includes('Turn on')) {
                        d.remove();
                    }
                }
            }""")

            # Get numeric group ID
            gid = await page.evaluate("""() => {
                const m = document.documentElement.innerHTML.match(/"groupID":"(\\d+)"/);
                return m ? m[1] : null;
            }""")
            print(f"Detected groupID: {gid}", flush=True)

            # Focus center & scroll 5 times
            try:
                await page.mouse.move(700, 500)
                await page.mouse.click(700, 500)
            except Exception:
                pass

            for s in range(5):
                await page.keyboard.press("Escape")
                await page.mouse.wheel(0, 1500)
                await page.keyboard.press("PageDown")
                await asyncio.sleep(1.5)

            # Extract links
            links = await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll("a[href*='/photo/'], a[href*='photo.php'], a[href*='fbid=']"));
                return els.map(a => a.href);
            }""")
            print(f"Found {len(links)} photo links after 5 scrolls ({len(set(links))} unique)", flush=True)
            for l in list(set(links))[:4]:
                print("   Link:", l, flush=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
