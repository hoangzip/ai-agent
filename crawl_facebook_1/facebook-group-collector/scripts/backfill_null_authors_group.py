"""
scripts/backfill_null_authors_group.py — Backfill missing author names for posts in a group.

Inspects all posts where author_display_name is None, loads the corresponding photo page,
extracts author information (real name or anonymous alias), and updates the post JSON and cic_customers.json.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.pipeline.normalizer import clean_facebook_url, is_anonymous_user
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo
from scripts.crawl_media_gallery_sequential import inspect_photo_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_authors")


async def backfill_group(group_slug: str):
    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    posts_dir = layout.group_posts_dir(group_slug)
    leads_path = layout.group_cic_leads_path(group_slug)
    leads = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []

    # Find posts with null author
    null_posts = []
    for p in sorted(posts_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not d.get("author_display_name"):
                # Get photo_fbid from media metadata or facebook_post_id
                fbid = None
                media_ids = d.get("media_ids") or []
                for m_id in media_ids:
                    meta_p = Path(f"data/media/meta/{m_id}.json")
                    if meta_p.exists():
                        try:
                            m_d = json.loads(meta_p.read_text(encoding="utf-8"))
                            if m_d.get("photo_fbid"):
                                fbid = str(m_d["photo_fbid"])
                                break
                        except Exception:
                            pass
                if not fbid:
                    fbid = str(d.get("facebook_post_id"))
                null_posts.append((p, d, fbid))
        except Exception:
            pass

    logger.info("Group %s: Found %d posts with null author.", group_slug, len(null_posts))
    if not null_posts:
        return

    actor_repo = ActorRepo(layout, group_slug)
    browser_state = "data/browser_state/default.json"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
        ctx = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await ctx.new_page()

        fixed_count = 0
        leads_updated = False

        for idx, (post_path, post_data, fbid) in enumerate(null_posts):
            photo_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{group_slug}"
            logger.info("[%d/%d] Resolving author for post %s (photo %s)...",
                        idx + 1, len(null_posts), post_data["id"], fbid)

            try:
                info = await inspect_photo_page(page, photo_url)
            except Exception as e:
                logger.warning("Error inspecting photo %s: %s", fbid, e)
                continue

            author_name = info.get("author_name")
            author_profile_url = info.get("author_profile_url")
            is_anon = info.get("is_anonymous", False)

            if author_name:
                # Upsert actor
                fb_uid = None
                if author_profile_url and not is_anon:
                    m_user = re.search(r"/(?:user|profile\.php\?id=)/(\d+)", author_profile_url)
                    if m_user:
                        fb_uid = m_user.group(1)

                try:
                    actor_rec, _ = await actor_repo.upsert({
                        "facebook_user_id": fb_uid,
                        "profile_url": author_profile_url if not is_anon else None,
                        "display_name": author_name,
                        "is_anonymous": is_anon,
                        "anonymous_scope_post_id": str(post_data.get("facebook_post_id")) if is_anon else None,
                    })
                    post_data["author_id"] = actor_rec["id"]
                except Exception as e_actor:
                    logger.debug("Actor upsert error: %s", e_actor)

                post_data["author_display_name"] = author_name
                post_data["author_profile_url"] = author_profile_url if not is_anon else None
                post_data["author_is_anonymous"] = is_anon
                post_data["updated_at"] = datetime.now(timezone.utc).isoformat()

                if info.get("caption") and not post_data.get("content"):
                    post_data["content"] = info["caption"]
                    post_data["title"] = info["caption"][:100]

                # Save updated post JSON
                post_path.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
                fixed_count += 1
                logger.info("  -> FIXED: author=%s (anon=%s, url=%s)", author_name, is_anon, author_profile_url)

                # Update in cic_customers.json if present
                for l in leads:
                    if l.get("post_id") == post_data["id"] or l.get("facebook_post_id") == post_data.get("facebook_post_id"):
                        l["author_display_name"] = author_name
                        l["author_profile_url"] = author_profile_url if not is_anon else None
                        l["author_is_anonymous"] = is_anon
                        leads_updated = True

            await asyncio.sleep(2.0)

        if leads_updated:
            leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Updated cic_customers.json with recovered author names.")

        await browser.close()
        logger.info("Backfill complete! Fixed %d / %d posts.", fixed_count, len(null_posts))


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "3508387292634958"
    asyncio.run(backfill_group(slug))
