"""
scripts/repair_corrupted_posts.py — Repair post_url, facebook_post_id, posted_at, and author
for posts that captured the Facebook recovery/login banner link, and check their comments.
"""
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.pipeline.normalizer import parse_timestamp, clean_facebook_url, is_anonymous_user
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo
from collector.downloaders.media_downloader import MediaDownloader
from collector.facebook.comment_cic import extract_comment_photos_from_page, process_comment_cic_photo
from scripts.crawl_media_gallery_sequential import inspect_photo_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("repair_posts")

GROUP_SLUG = "978769317924542"


async def main():
    layout = StorageLayout(Path("data"))
    group_posts_dir = layout.group_posts_dir(GROUP_SLUG)
    cic_file = layout.root / "groups" / GROUP_SLUG / "cic_customers.json"
    state_file = layout.root / "groups" / GROUP_SLUG / "media_gallery_state.json"
    checked_comments_file = layout.root / "groups" / GROUP_SLUG / "checked_comment_posts.json"
    actor_repo = ActorRepo(layout, GROUP_SLUG)
    downloader = MediaDownloader()

    # 1. Identify corrupted post files
    corrupted_posts = []
    for p in sorted(group_posts_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            p_url = data.get("post_url") or ""
            if "recover/initiate" in p_url:
                corrupted_posts.append((p, data))
        except Exception:
            pass

    logger.info("Found %d posts with recover/initiate post_url needing repair.", len(corrupted_posts))
    if not corrupted_posts:
        logger.info("No corrupted posts found! All posts have clean URLs.")
        return

    # Load cic_customers.json
    cic_customers = []
    if cic_file.exists():
        try:
            cic_customers = json.loads(cic_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Load state
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Load checked comments
    checked_comment_post_ids = set()
    if checked_comments_file.exists():
        try:
            checked_comment_post_ids = set(json.loads(checked_comments_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    # Launch browser
    config = load_config()
    browser_state = "data/browser_state/default.json"
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        context = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await context.new_page()
        comment_page = await context.new_page()
        photo_page = await context.new_page()

        repaired_count = 0
        comment_leads_found = 0
        total = len(corrupted_posts)

        for idx, (post_path, post_data) in enumerate(corrupted_posts):
            post_uuid = post_data["id"]
            # Find photo fbid:
            fbid = None
            media_ids = post_data.get("media_ids", [])
            for m_id in media_ids:
                m_meta_path = layout.media_meta_path(m_id)
                if m_meta_path.exists():
                    try:
                        m_meta = json.loads(m_meta_path.read_text(encoding="utf-8"))
                        fbid = m_meta.get("photo_fbid")
                        if fbid:
                            break
                    except Exception:
                        pass
            if not fbid:
                fbid = post_data.get("facebook_post_id")

            if not fbid:
                logger.warning("[%d/%d] Post %s has no identifiable photo FBID! Skipping.", idx + 1, total, post_uuid)
                continue

            photo_url = f"https://web.facebook.com/photo/?fbid={fbid}&set=g.{GROUP_SLUG}"
            logger.info("[%d/%d] Repairing post %s (FBID=%s)...", idx + 1, total, post_uuid, fbid)

            try:
                info = await inspect_photo_page(page, photo_url)
            except Exception as e:
                logger.warning("[%d/%d] Error inspecting photo %s: %s", idx + 1, total, fbid, e)
                continue

            found_post_id = info.get("post_id")
            raw_purl = info.get("post_url")
            if found_post_id and str(found_post_id) != str(fbid) and raw_purl and "recover/initiate" not in raw_purl and ("posts" in raw_purl or "permalink" in raw_purl):
                real_post_id = str(found_post_id)
                real_post_url = raw_purl
            else:
                real_post_id = str(fbid)
                real_post_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{GROUP_SLUG}"

            # Update post dict
            post_data["facebook_post_id"] = real_post_id
            post_data["post_url"] = real_post_url
            if info.get("timestamp_str"):
                dt = parse_timestamp(None, info["timestamp_str"])
                if dt:
                    post_data["posted_at"] = dt.isoformat()
            if info.get("caption"):
                post_data["content"] = info["caption"]
                post_data["title"] = info["caption"][:100]

            # Author update if available
            a_name = info.get("author_name")
            a_url = info.get("author_profile_url")
            a_anon = info.get("is_anonymous", False)
            if a_name:
                post_data["author_display_name"] = a_name
                post_data["author_profile_url"] = a_url
                post_data["author_is_anonymous"] = a_anon

            post_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            post_path.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")

            # Update in cic_customers.json for existing lead
            for c_lead in cic_customers:
                if c_lead.get("post_id") == post_uuid:
                    c_lead["facebook_post_id"] = real_post_id
                    c_lead["post_url"] = real_post_url
                    if a_name:
                        c_lead["author_display_name"] = a_name
                        c_lead["author_profile_url"] = a_url
                        c_lead["author_is_anonymous"] = a_anon

            # Update state
            if fbid in state:
                state[fbid]["post_id"] = real_post_id

            # Check comments if not yet checked for real_post_id
            if real_post_id not in checked_comment_post_ids:
                checked_comment_post_ids.add(real_post_id)
                # Remove stale fbid if recorded
                checked_comment_post_ids.discard(str(fbid))
                try:
                    await comment_page.goto(real_post_url, wait_until="domcontentloaded", timeout=25_000)
                    await asyncio.sleep(2.0)

                    # Expand comments & replies
                    for _ in range(12):
                        more_btn = await comment_page.query_selector(
                            "span:has-text('View more comments'), span:has-text('Xem thêm bình luận'), div[role='button']:has-text('View more comments')"
                        )
                        if more_btn and await more_btn.is_visible():
                            try:
                                await more_btn.click()
                                await asyncio.sleep(0.8)
                            except Exception:
                                break
                        else:
                            break

                    reply_btns = await comment_page.query_selector_all("div[role='button']:has-text('replies'), div[role='button']:has-text('reply'), div[role='button']:has-text('câu trả lời')")
                    for b in reply_btns[:15]:
                        try:
                            if await b.is_visible():
                                await b.click()
                                await asyncio.sleep(0.4)
                        except Exception:
                            pass

                    c_photos = await extract_comment_photos_from_page(comment_page)
                    for c_item in c_photos:
                        c_lead = await process_comment_cic_photo(
                            photo_page=photo_page,
                            comment_data=c_item,
                            post_uuid=post_uuid,
                            facebook_post_id=real_post_id,
                            post_url=real_post_url,
                            group_slug=GROUP_SLUG,
                            layout=layout,
                            downloader=downloader,
                            actor_repo=actor_repo,
                            post_fbid=fbid,
                        )
                        if c_lead:
                            comment_leads_found += 1
                            # Deduplicate
                            matched = False
                            for idx_c, ex_c in enumerate(cic_customers):
                                if c_lead.get("author_profile_url") and ex_c.get("author_profile_url") == c_lead.get("author_profile_url"):
                                    cic_customers[idx_c].update(c_lead)
                                    matched = True
                                    break
                                elif c_lead.get("comment_id") and ex_c.get("comment_id") == c_lead.get("comment_id"):
                                    cic_customers[idx_c].update(c_lead)
                                    matched = True
                                    break
                                elif c_lead.get("cic_code") and ex_c.get("cic_code") == c_lead.get("cic_code"):
                                    cic_customers[idx_c].update(c_lead)
                                    matched = True
                                    break
                            if not matched:
                                cic_customers.append(c_lead)

                except Exception as e_comm:
                    logger.debug("Error checking comments for post %s: %s", real_post_id, e_comm)

            repaired_count += 1
            if repaired_count % 10 == 0:
                cic_file.write_text(json.dumps(cic_customers, ensure_ascii=False, indent=2), encoding="utf-8")
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                checked_comments_file.write_text(json.dumps(sorted(list(checked_comment_post_ids)), ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info("Progress saved: %d/%d posts repaired. Comment leads found: %d", repaired_count, total, comment_leads_found)

            await asyncio.sleep(0.5)

        # Final write
        cic_file.write_text(json.dumps(cic_customers, ensure_ascii=False, indent=2), encoding="utf-8")
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        checked_comments_file.write_text(json.dumps(sorted(list(checked_comment_post_ids)), ensure_ascii=False, indent=2), encoding="utf-8")
        await comment_page.close()
        await photo_page.close()
        await browser.close()
        logger.info("Repair complete! Successfully repaired %d / %d posts. New comment leads: %d.", repaired_count, total, comment_leads_found)


if __name__ == "__main__":
    asyncio.run(main())
