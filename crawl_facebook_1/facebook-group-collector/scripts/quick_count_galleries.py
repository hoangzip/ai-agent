import asyncio
from playwright.async_api import async_playwright
import re

async def count_photos_in_gallery(group_url, name):
    print(f"\nScanning gallery for {name} ({group_url})...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(storage_state="data/browser_state/default.json", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        await page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)

        # Focus center of page
        try:
            await page.mouse.move(700, 500)
            await page.mouse.click(700, 500)
        except Exception:
            pass

        seen_fbids = set()
        no_new = 0
        scroll = 0

        while scroll < 50:  # test up to 50 scrolls
            scroll += 1
            # Dismiss dialogs
            await page.evaluate("""() => {
                for (let d of document.querySelectorAll("div[role='dialog']")) {
                    if (d.innerText.includes('daily limit') || d.innerText.includes('Notifications') || d.innerText.includes('Turn on')) {
                        d.remove();
                    }
                }
            }""")

            links = await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll("a[href*='/photo/'], a[href*='photo.php'], a[href*='fbid=']"));
                return els.map(a => a.href);
            }""")
            before_len = len(seen_fbids)
            for l in links:
                m = re.search(r"fbid=(\d+)", l)
                if m:
                    seen_fbids.add(m.group(1))

            added = len(seen_fbids) - before_len
            if added == 0:
                no_new += 1
                if no_new >= 8:
                    print(f"[{name}] Reached end at scroll {scroll}. Total photos: {len(seen_fbids)}", flush=True)
                    break
            else:
                no_new = 0

            if scroll % 10 == 0:
                print(f"[{name}] Scroll {scroll}: {len(seen_fbids)} photos collected so far...", flush=True)

            # Scroll
            await page.keyboard.press("Escape")
            await page.mouse.wheel(0, 1500)
            await page.keyboard.press("PageDown")
            await asyncio.sleep(1.2)

        print(f"[{name}] Finished scan. Total photos collected: {len(seen_fbids)}", flush=True)
        await browser.close()
        return len(seen_fbids)

async def main():
    await count_photos_in_gallery("https://www.facebook.com/groups/508242083145361/media/photos", "kiemtranoxau")
    await count_photos_in_gallery("https://www.facebook.com/groups/1178898519573483/media/photos", "1178898519573483")

if __name__ == "__main__":
    asyncio.run(main())
