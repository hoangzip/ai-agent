import asyncio
from playwright.async_api import async_playwright
import re

async def inspect_groups():
    groups = [
        {"slug": "kiemtranoxau", "url": "https://www.facebook.com/groups/kiemtranoxau/media"},
        {"slug": "1178898519573483", "url": "https://www.facebook.com/groups/1178898519573483/media"}
    ]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state="data/browser_state/default.json")
        page = await ctx.new_page()

        for g in groups:
            print(f"=== Inspecting {g['slug']} ===")
            await page.goto(g["url"], wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            print("Current URL:", page.url)

            # Check if Joined or Join button present
            join_btn = await page.query_selector("div[aria-label*='Join Group'], div[aria-label*='Tham gia nhóm'], div[role='button']:has-text('Tham gia nhóm'), div[role='button']:has-text('Join group')")
            if join_btn and await join_btn.is_visible():
                print("Join button present! Clicking Join...")
                try:
                    await join_btn.click()
                    await asyncio.sleep(2)
                except Exception as e:
                    print("Error clicking join:", e)
            else:
                print("Already joined or no join button found.")

            # Dismiss dialogs
            await page.evaluate("""() => {
                for (let d of document.querySelectorAll("div[role='dialog']")) {
                    if (d.innerText.includes('daily limit') || d.innerText.includes('Notifications') || d.innerText.includes('Turn on')) {
                        d.remove();
                    }
                }
            }""")

            # Sample links
            sample_links = await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll("a[href*='/photo/'], a[href*='fbid=']"));
                return els.slice(0, 10).map(a => a.href);
            }""")
            print(f"Sample photo links ({len(sample_links)} found):")
            for sl in sample_links[:5]:
                print("  ", sl)

            # Extract numeric group id if available
            group_id = await page.evaluate("""() => {
                const m = document.documentElement.innerHTML.match(/"groupID":"(\\\\d+)"/);
                return m ? m[1] : null;
            }""")
            print("Detected numeric group ID:", group_id)

            # Test a quick 3-step scroll to see if photo links increment properly
            initial_count = len(sample_links)
            for i in range(3):
                await page.keyboard.press("Escape")
                await page.mouse.wheel(0, 1500)
                await page.keyboard.press("PageDown")
                await asyncio.sleep(1.5)
            new_count = await page.evaluate("""() => {
                return document.querySelectorAll("a[href*='/photo/'], a[href*='fbid=']").length;
            }""")
            print(f"After 3 scrolls: photo links count changed from {initial_count} to {new_count}")
            print("-" * 50)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_groups())
