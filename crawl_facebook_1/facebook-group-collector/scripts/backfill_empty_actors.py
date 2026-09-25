"""
scripts/backfill_empty_actors.py — Automatically resolve and backfill real & anon names
for all actors with empty display_name by visiting their group profile page.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.pipeline.normalizer import is_anonymous_user
from collector.storage.layout import StorageLayout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("actor_backfill")

GROUP_SLUG = "978769317924542"


async def main():
    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    actors_dir = layout.group_actors_dir(GROUP_SLUG)
    posts_dir = layout.group_posts_dir(GROUP_SLUG)
    comments_dir = Path("data/comments")

    # 1. Map which actors belong to posts vs comments
    post_author_to_posts: dict[str, list[Path]] = {}
    for p in posts_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            aid = d.get("author_id")
            if aid:
                post_author_to_posts.setdefault(aid, []).append(p)
        except Exception:
            pass

    comment_author_to_comments: dict[str, list[Path]] = {}
    for c in comments_dir.glob("*/*.json"):
        try:
            d = json.loads(c.read_text(encoding="utf-8"))
            aid = d.get("author_id")
            if aid:
                comment_author_to_comments.setdefault(aid, []).append(c)
        except Exception:
            pass

    # 2. Find empty actors
    empty_actors = []
    for a in sorted(actors_dir.glob("*.json")):
        if a.name == "index.json":
            continue
        try:
            d = json.loads(a.read_text(encoding="utf-8"))
            name = (d.get("display_name") or "").strip()
            is_suspicious = len(name) > 35 or any(w in name.lower() for w in ("?", " k ", " không ", " vay ", " thẻ ", " nợ ", " check cic"))
            if not name or is_suspicious:
                aid = d["id"]
                is_in_posts = aid in post_author_to_posts
                empty_actors.append((is_in_posts, a, d))
        except Exception:
            pass

    # Sort so post authors come FIRST
    empty_actors.sort(key=lambda t: not t[0])

    logger.info("Found %d empty actors (%d are post authors, %d are comment authors)",
                len(empty_actors),
                sum(1 for t in empty_actors if t[0]),
                sum(1 for t in empty_actors if not t[0]))

    if not empty_actors:
        logger.info("All actors already have display_name!")
        return

    browser_state = "data/browser_state/default.json"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        ctx = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await ctx.new_page()

        filled_count = 0

        for idx, (is_in_posts, actor_path, actor_data) in enumerate(empty_actors):
            aid = actor_data["id"]
            uid = actor_data.get("facebook_user_id")
            url = actor_data.get("profile_url") or (f"https://web.facebook.com/groups/{GROUP_SLUG}/user/{uid}" if uid else None)

            if not url:
                continue

            tag = "[POST AUTHOR]" if is_in_posts else "[COMMENT AUTHOR]"
            logger.info("[%d/%d] %s Resolving name for uid=%s...", idx + 1, len(empty_actors), tag, uid)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                await asyncio.sleep(1.5)
                title = await page.title()

                clean_name = re.sub(r"^\(\d+\)\s*", "", title)
                clean_name = re.sub(r"\s*\|\s*Facebook.*$", "", clean_name).strip()

                if not clean_name or clean_name in ("Facebook", "Log in to Facebook", "Content not found", "Trang không tìm thấy"):
                    # Try reading from DOM h1/h2
                    dom_name = await page.evaluate("""() => {
                        const h = document.querySelector("h1, h2");
                        return h ? h.innerText.trim() : null;
                    }""")
                    if dom_name and len(dom_name) > 1 and "Facebook" not in dom_name:
                        clean_name = dom_name

                if clean_name and clean_name not in ("Facebook", "Log in to Facebook", "Content not found"):
                    is_anon = is_anonymous_user(clean_name, url)
                    actor_data["display_name"] = clean_name
                    actor_data["is_anonymous"] = is_anon
                    actor_data["anonymous_scope_post_id"] = actor_data.get("anonymous_scope_post_id") if is_anon else None
                    actor_path.write_text(json.dumps(actor_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    filled_count += 1
                    logger.info("  -> Found: '%s' (is_anon=%s)", clean_name, is_anon)

                    # Update posts referencing this author
                    if aid in post_author_to_posts:
                        for post_file in post_author_to_posts[aid]:
                            try:
                                pd = json.loads(post_file.read_text(encoding="utf-8"))
                                pd["author_display_name"] = clean_name
                                pd["author_is_anonymous"] = is_anon
                                post_file.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
                            except Exception:
                                pass

                    # Update comments referencing this author
                    if aid in comment_author_to_comments:
                        for comment_file in comment_author_to_comments[aid]:
                            try:
                                cd = json.loads(comment_file.read_text(encoding="utf-8"))
                                cd["author_display_name"] = clean_name
                                cd["author_is_anonymous"] = is_anon
                                comment_file.write_text(json.dumps(cd, ensure_ascii=False, indent=2), encoding="utf-8")
                            except Exception:
                                pass
                else:
                    logger.warning("  -> Could not determine name for uid=%s (title='%s')", uid, title)

            except Exception as e:
                logger.warning("  -> Error loading profile for uid=%s: %s", uid, e)

            await asyncio.sleep(0.5)

        await browser.close()
        logger.info("Finished backfilling! Total names resolved: %d/%d", filled_count, len(empty_actors))


if __name__ == "__main__":
    asyncio.run(main())
