import asyncio
from playwright.async_api import async_playwright

async def test_scroll():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(storage_state="data/browser_state/default.json", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        for g in ["kiemtranoxau", "1178898519573483"]:
            url = f"https://www.facebook.com/groups/{g}/media"
            print(f"\nTesting scroll on {g} ({url})...", flush=True)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Focus center
            await page.mouse.click(700, 500)
            await asyncio.sleep(0.5)

            # Scroll 10 times with mouse wheel & page down
            seen_fbids = set()
            for s in range(15):
                await page.keyboard.press("Escape")
                await page.mouse.wheel(0, 1500)
                await page.keyboard.press("PageDown")
                await asyncio.sleep(1.2)

                links = await page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll("a[href*='/photo/'], a[href*='photo.php'], a[href*='set=g.'], a[href*='fbid=']"));
                    return els.map(a => a.href);
                }""")
                for l in links:
                    import re
                    m = re.search(r"fbid=(\d+)", l)
                    if m:
                        seen_fbids.add(m.group(1))

                if (s + 1) % 5 == 0:
                    print(f"Scroll {s+1}: found {len(seen_fbids)} unique fbids", flush=True)

            print(f"Total unique photos found on {g} after 15 scrolls: {len(seen_fbids)}", flush=True)
            snap_path = f"/Users/hoangtq13/.gemini/antigravity-ide/brain/1097a3d2-550c-4360-ab0c-795e9eb07038/{g}_scrolled.png"
            await page.screenshot(path=snap_path, full_page=False)
            print(f"Saved scrolled screenshot to {snap_path}", flush=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_scroll())
