"""
scripts/crawl_comments_cic.py — Dedicated Comment CIC Extractor.

Features:
1. --post-url: Crawl comment photos for a specific post URL.
2. --all-posts: Scan all existing post JSON files in data/groups/{group_slug}/posts and extract comment photos.
3. --feed: Scroll group feed to discover discussion / text-only posts and extract their comment photos.
4. Identifies comment author (Commenter) with anonymity check (Report nickname / persona / anonymous).
5. High-resolution photo loading via Photo Theater, OCR via native Vision OCR, and saves to cic_customers.json.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import random
import re
import sys
import uuid

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.downloaders.media_downloader import MediaDownloader
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo
from collector.facebook.comment_cic import extract_comment_photos_from_page, process_comment_cic_photo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("comment_cic_crawler")

GROUP_SLUG = "978769317924542"


async def crawl_comments_for_post(
    page,
    photo_page,
    post_url: str,
    post_uuid: str,
    facebook_post_id: str,
    group_slug: str,
    layout: StorageLayout,
    downloader: MediaDownloader,
    actor_repo: ActorRepo,
    leads: list[dict],
    leads_path: Path,
) -> int:
    """Extract comment photos from a single post and save any CIC leads found."""
    logger.info("Checking comments for post %s (%s)...", facebook_post_id, post_url)
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(3.0)
    except Exception as e:
        logger.warning("Failed opening post %s: %s", post_url, e)
        return 0

    # Deep expand comments (up to 25 times)
    for _ in range(25):
        more_btn = await page.query_selector(
            "span:has-text('View more comments'), span:has-text('Xem thêm bình luận'), div[role='button']:has-text('View more comments'), span:has-text('View previous comments')"
        )
        if more_btn and await more_btn.is_visible():
            try:
                await more_btn.click()
                await asyncio.sleep(1.2)
            except Exception:
                break
        else:
            break

    # Expand comment replies (up to 40 threads)
    reply_btns = await page.query_selector_all(
        "div[role='button']:has-text('replies'), div[role='button']:has-text('reply'), div[role='button']:has-text('câu trả lời')"
    )
    for b in reply_btns[:40]:
        try:
            if await b.is_visible():
                await b.click()
                await asyncio.sleep(0.6)
        except Exception:
            pass

    comment_photos = await extract_comment_photos_from_page(page)
    if not comment_photos:
        logger.info("  -> No comment photos in post %s.", facebook_post_id)
        return 0

    logger.info("  -> Found %d comment photos in post %s. Inspecting for CIC...", len(comment_photos), facebook_post_id)
    new_leads_count = 0

    for c in comment_photos:
        lead = await process_comment_cic_photo(
            photo_page=photo_page,
            comment_data=c,
            post_uuid=post_uuid,
            facebook_post_id=facebook_post_id,
            post_url=post_url,
            group_slug=group_slug,
            layout=layout,
            downloader=downloader,
            actor_repo=actor_repo,
        )
        if lead:
            new_leads_count += 1
            logger.info("  [CIC IN COMMENT FOUND] author=%s (%s) score=%s tier=%s date=%s sđt=%s provider=%s",
                        lead.get("author_display_name"), lead.get("author_profile_url"),
                        lead.get("score"), lead.get("tier"), lead.get("scoring_date"),
                        lead.get("phone_number"), lead.get("provider"))

            # Deduplicate by author_profile_url or comment_id or cic_code
            matched = False
            for idx, ex in enumerate(leads):
                if lead.get("author_profile_url") and ex.get("author_profile_url") == lead.get("author_profile_url"):
                    leads[idx].update(lead)
                    matched = True
                    break
                elif lead.get("comment_id") and ex.get("comment_id") == lead.get("comment_id"):
                    leads[idx].update(lead)
                    matched = True
                    break
                elif lead.get("cic_code") and ex.get("cic_code") == lead.get("cic_code"):
                    leads[idx].update(lead)
                    matched = True
                    break

            if not matched:
                leads.append(lead)

            leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

    return new_leads_count


async def main():
    parser = argparse.ArgumentParser(description="Facebook Comments CIC Crawler")
    parser.add_argument("--group", type=str, default="978769317924542", help="Facebook group slug or ID")
    parser.add_argument("--post-url", type=str, default=None, help="Crawl comments of a specific post URL")
    parser.add_argument("--all-posts", action="store_true", help="Crawl comments for all saved posts in posts/ dir")
    parser.add_argument("--limit", type=int, default=None, help="Stop after checking N posts")
    args = parser.parse_args()

    group_slug = args.group
    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    downloader = MediaDownloader()
    actor_repo = ActorRepo(layout, group_slug)
    leads_path = layout.group_cic_leads_path(group_slug)
    leads = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []

    posts_dir = layout.group_posts_dir(group_slug)
    posts_dir.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        context = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
        page = await context.new_page()
        photo_page = await context.new_page()

        total_cic_found = 0

        if args.post_url:
            post_id_match = re.search(r"/(?:posts|permalink)/(\d+)", args.post_url)
            fb_id = post_id_match.group(1) if post_id_match else "unknown"
            found = await crawl_comments_for_post(
                page=page,
                photo_page=photo_page,
                post_url=args.post_url,
                post_uuid=str(uuid.uuid4()),
                facebook_post_id=fb_id,
                group_slug=group_slug,
                layout=layout,
                downloader=downloader,
                actor_repo=actor_repo,
                leads=leads,
                leads_path=leads_path,
            )
            total_cic_found += found

        elif args.all_posts:
            post_files = sorted(list(posts_dir.glob("*.json")))
            logger.info("Scanning comments across %d existing posts in group %s...", len(post_files), group_slug)
            if args.limit:
                post_files = post_files[:args.limit]

            for idx, pf in enumerate(post_files):
                try:
                    post_data = json.loads(pf.read_text(encoding="utf-8"))
                    post_url = post_data.get("post_url")
                    fb_id = post_data.get("facebook_post_id") or "unknown"
                    post_uuid = post_data.get("id") or str(uuid.uuid4())
                    if not post_url:
                        continue

                    found = await crawl_comments_for_post(
                        page=page,
                        photo_page=photo_page,
                        post_url=post_url,
                        post_uuid=post_uuid,
                        facebook_post_id=fb_id,
                        group_slug=group_slug,
                        layout=layout,
                        downloader=downloader,
                        actor_repo=actor_repo,
                        leads=leads,
                        leads_path=leads_path,
                    )
                    total_cic_found += found
                    await asyncio.sleep(random.uniform(1.2, 2.0))
                except Exception as e:
                    logger.warning("Error processing post file %s: %s", pf.name, e)

        await photo_page.close()
        await page.close()
        await browser.close()

        logger.info("Comment Crawl Completed! Total new CIC leads extracted from comments: %d (Total in database: %d)",
                    total_cic_found, len(leads))


if __name__ == "__main__":
    asyncio.run(main())
