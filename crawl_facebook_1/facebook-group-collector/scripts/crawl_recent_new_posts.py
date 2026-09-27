"""
scripts/crawl_recent_new_posts.py — Incremental 3-day crawler for photo posts across all groups.

Requirements:
1. Scan all 6 existing groups:
   - 978769317924542
   - 580277503401606
   - 1295572999197093
   - 745513060834871
   - kiemtranoxau (508242083145361)
   - 1178898519573483
2. Time window: Strictly within the last 3 days (cutoff at 00:00:00 3 days ago).
3. If an old post (already crawled and in DB) is encountered, SKIP IT.
4. Checks group Media Gallery photos (/media/photos) strictly within main container.
5. Extracts author, post text, downloads images, runs OCR CIC extraction, and saves posts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
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
from collector.pipeline.normalizer import clean_facebook_url, parse_timestamp, is_anonymous_user
from collector.analysis.cic_extractor import CICExtractor
from collector.downloaders.media_downloader import MediaDownloader
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("recent_crawler")

GROUPS = [
    {"slug": "978769317924542", "numeric_id": "978769317924542", "name": "Group 978769317924542"},
    {"slug": "580277503401606", "numeric_id": "580277503401606", "name": "Group 580277503401606"},
    {"slug": "1295572999197093", "numeric_id": "1295572999197093", "name": "Group 1295572999197093"},
    {"slug": "745513060834871", "numeric_id": "745513060834871", "name": "Group 745513060834871"},
    {"slug": "kiemtranoxau", "numeric_id": "508242083145361", "name": "Kiểm tra Nợ Xấu CIC"},
    {"slug": "1178898519573483", "numeric_id": "1178898519573483", "name": "Hỗ Trợ Vay Tín Chấp MOMO CIC"},
]

POST_ID_RE = re.compile(r"/(?:posts|permalink)/(\d+)")
FBID_RE = re.compile(r"fbid=(\d+)")
MAX_AGE_DAYS = 3


def is_within_3_days(dt: datetime | None, raw_str: str | None = None) -> bool:
    """Check if timestamp or relative time string is within the last 3 days."""
    now = datetime.now(timezone.utc)
    # Include start of day 3 days ago
    cutoff = (now - timedelta(days=MAX_AGE_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)

    if dt:
        return dt >= cutoff

    if raw_str:
        s = raw_str.lower().strip()
        # Relative minutes / hours / today / yesterday / just now
        if any(w in s for w in ("phút", "min", "giờ", "hr", "h", "vừa xong", "just now", "vừa đăng")):
            return True
        if "hôm qua" in s or "yesterday" in s:
            return True
        # Format like '2d', '1d', '3d', '2 ngày', '3 ngày'
        m_day = re.search(r"(\d+)\s*(?:ngày|days?|d)\b", s)
        if m_day:
            return int(m_day.group(1)) <= MAX_AGE_DAYS
        m_week = re.search(r"(\d+)\s*(?:tuần|weeks?|w)\b", s)
        if m_week:
            return False
        m_month = re.search(r"(\d+)\s*(?:tháng|months?|mo)\b", s)
        if m_month:
            return False

        parsed = parse_timestamp(None, raw_str)
        if parsed:
            return parsed >= cutoff

    # Default to True if indeterminate to allow inspection
    return True


async def dismiss_dialogs(page):
    """Dismiss any blocking dialogs, permission prompts, or notification overlays."""
    try:
        await page.keyboard.press("Escape")
        await page.evaluate("""() => {
            for (let d of document.querySelectorAll("div[role='dialog'], div[role='region']")) {
                const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                const txt = (d.innerText || '').toLowerCase();
                if (aria.includes('notification') || txt.includes('notification') || txt.includes('turn on') || txt.includes('daily limit') || txt.includes('báo cáo biệt danh')) {
                    d.remove();
                }
            }
        }""")
    except Exception:
        pass


async def inspect_photo_page(page, photo_url: str) -> dict:
    """Load photo page and extract post metadata, author, caption, and image."""
    await page.goto(photo_url, wait_until="domcontentloaded", timeout=35_000)
    await asyncio.sleep(2.5)

    # Check for temporary block
    body_txt = await page.inner_text("body")
    if "Temporarily Blocked" in body_txt or "bị chặn tạm thời" in body_txt.lower():
        raise RuntimeError("FACEBOOK_TEMPORARILY_BLOCKED")

    # Dismiss overlays
    await dismiss_dialogs(page)

    post_url = None
    post_id = None
    timestamp_str = None

    # 1. Author
    author_info = await page.evaluate("""() => {
        for (let h2 of document.querySelectorAll("h2")) {
            const txt = h2.innerText.trim();
            const low = txt.toLowerCase();
            if (txt && !low.includes('bình luận') && !low.includes('comments') && !low.includes('chia sẻ') && low !== 'new' && low !== 'earlier' && !low.includes('no comments') && !low.includes('facebook menu') && !low.includes('menu')) {
                const a = h2.querySelector("a[href*='/user/'], a[href*='profile.php'], a[role='link']");
                if (a) {
                    return { name: txt, url: a.href };
                }
                if (low.includes('anonymous') || low.includes('ẩn danh')) {
                    return { name: txt, url: null };
                }
            }
        }
        return null;
    }""")

    author_name = None
    author_profile_url = None
    is_anon = False

    invalid_names = ("kiểm tra nợ xấu", "hỗ trợ vay", "check cic", "notifications", "thông báo", "earlier", "new", "comments", "bình luận")

    if author_info:
        raw_name = (author_info.get("name") or "").strip()
        raw_name = re.sub(r"'s\s+Post$", "", raw_name, flags=re.IGNORECASE).strip()
        raw_name = re.sub(r"^Bài\s+viết\s+của\s+", "", raw_name, flags=re.IGNORECASE).strip()
        raw_url = author_info.get("url")
        if any(w in raw_name.lower() for w in ("anonymous", "ẩn danh")):
            author_name = "Anonymous participant"
            author_profile_url = None
            is_anon = True
        elif is_anonymous_user(raw_name, raw_url):
            author_name = raw_name
            author_profile_url = clean_facebook_url(raw_url) if raw_url else None
            is_anon = True
        elif raw_name and len(raw_name) > 1 and not any(k in raw_name.lower() for k in invalid_names):
            author_name = raw_name
            author_profile_url = clean_facebook_url(raw_url) if raw_url else None
            is_anon = False

    # 2. Timestamp & Post URL
    ts_link = await page.query_selector("a[href*='/posts/'], a[href*='/permalink/']")
    if ts_link:
        raw_href = await ts_link.get_attribute("href")
        if raw_href and "recover/initiate" not in raw_href:
            post_url = clean_facebook_url(raw_href)
            if post_url:
                m = POST_ID_RE.search(post_url)
                if m:
                    post_id = m.group(1)

        try:
            await ts_link.hover(timeout=1500, force=True)
            await asyncio.sleep(0.4)
        except Exception:
            pass

        tooltips = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll("div[role='tooltip']")).map(el => el.innerText.trim()).filter(Boolean);
        }""")
        if tooltips and tooltips[0] != "Close":
            timestamp_str = tooltips[0]
        else:
            aria = await ts_link.get_attribute("aria-label")
            txt = (await ts_link.inner_text()).strip()
            if aria and aria != "View post":
                timestamp_str = aria
            elif txt and txt != "View post":
                timestamp_str = txt

    # Fallback timestamp search if not found
    if not timestamp_str or timestamp_str == "View post":
        timestamp_str = await page.evaluate("""() => {
            // Check short relative time spans in header or comments
            for (let el of document.querySelectorAll("span")) {
                const txt = (el.innerText || '').trim();
                if (txt.match(/^\\d+[hmwd]$/) && el.children.length === 0) {
                    return txt;
                }
            }
            return null;
        }""")

    # 3. Caption
    caption = None
    msg_el = await page.query_selector("div[data-ad-preview='message'], div[data-ad-comet-preview='message']")
    if msg_el:
        caption = (await msg_el.inner_text()).strip()

    # 4. Image source
    img_src = None
    try:
        img_el = await page.wait_for_selector(
            "div[data-pagelet='MediaViewerPhoto'] img, img[data-visualcompletion='media-vc-image']",
            timeout=3000
        )
        if img_el:
            img_src = await img_el.get_attribute("src")
    except Exception:
        pass

    if not img_src:
        img_src = await page.evaluate("""() => {
            let maxArea = 0, bestSrc = null;
            for (let img of document.querySelectorAll("img")) {
                const rect = img.getBoundingClientRect();
                const area = rect.width * rect.height;
                if (area > maxArea && rect.width > 200 && rect.height > 200) {
                    maxArea = area;
                    bestSrc = img.src;
                }
            }
            return bestSrc;
        }""")

    return {
        "post_id": post_id,
        "post_url": post_url,
        "timestamp_str": timestamp_str,
        "author_name": author_name,
        "author_profile_url": author_profile_url,
        "is_anonymous": is_anon,
        "caption": caption,
        "img_src": img_src,
    }


async def crawl_group_recent(
    group: dict,
    browser_context,
    layout: StorageLayout,
    downloader: MediaDownloader,
) -> dict:
    group_slug = group["slug"]
    numeric_gid = group["numeric_id"]
    group_name = group["name"]

    logger.info("================================================================================")
    logger.info("SCANNING GROUP FOR RECENT POSTS (LAST 3 DAYS): %s (%s)", group_slug, group_name)
    logger.info("================================================================================")

    posts_dir = layout.group_posts_dir(group_slug)
    posts_dir.mkdir(parents=True, exist_ok=True)
    leads_path = layout.group_cic_leads_path(group_slug)
    order_file = Path(f"data/groups/{group_slug}/media_gallery_order.json")
    state_file = Path(f"data/groups/{group_slug}/media_gallery_state.json")

    # Load existing known IDs
    known_post_ids: set[str] = set()
    for p in posts_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("facebook_post_id"):
                known_post_ids.add(str(d["facebook_post_id"]))
        except Exception:
            pass

    existing_state: dict = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    for fbid, s_info in existing_state.items():
        if isinstance(s_info, dict) and s_info.get("post_id"):
            known_post_ids.add(str(s_info["post_id"]))

    existing_order: list[dict] = json.loads(order_file.read_text(encoding="utf-8")) if order_file.exists() else []
    known_fbids: set[str] = {str(item["fbid"]) for item in existing_order if "fbid" in item}
    leads: list[dict] = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []

    actor_repo = ActorRepo(layout, group_slug)
    page = await browser_context.new_page()

    stats = {
        "group": group_slug,
        "new_photos_found": 0,
        "new_posts_saved": 0,
        "new_cic_leads": 0,
        "skipped_old_posts": 0,
        "skipped_older_than_3d": 0,
    }

    try:
        # STEP 1: Scan Media Gallery for new photos
        media_url = f"https://www.facebook.com/groups/{numeric_gid}/media/photos"
        logger.info("[%s] Checking media gallery: %s ...", group_slug, media_url)
        await page.goto(media_url, wait_until="domcontentloaded", timeout=40_000)
        await asyncio.sleep(3.5)

        await dismiss_dialogs(page)

        # Focus center & scroll up to 6 rounds
        try:
            await page.mouse.move(700, 500)
            await page.mouse.click(700, 500)
        except Exception:
            pass

        discovered_new_fbids: list[dict] = []
        consecutive_known = 0

        for scroll_round in range(8):
            await dismiss_dialogs(page)

            # Strictly query links within main container
            raw_links = await page.evaluate("""() => {
                const main = document.querySelector("div[role='main']") || document.body;
                const els = Array.from(main.querySelectorAll("a[href*='set=g.'], a[href*='/photo/'], a[href*='photo.php']"));
                return els.map(a => a.href);
            }""")

            hit_boundary = False
            for l in raw_links:
                m = FBID_RE.search(l)
                if not m:
                    continue
                fbid = m.group(1)

                if fbid in known_fbids:
                    # Ignore cover photo (e.g. index > 500)
                    consecutive_known += 1
                    if consecutive_known >= 10:
                        logger.info("[%s] Encountered %d consecutive known photos -> reached boundary of existing DB!", group_slug, consecutive_known)
                        hit_boundary = True
                        break
                else:
                    consecutive_known = 0
                    if not any(it["fbid"] == fbid for it in discovered_new_fbids):
                        clean_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{numeric_gid}"
                        discovered_new_fbids.append({"fbid": fbid, "url": clean_url})

            if hit_boundary:
                break

            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(1.5)

        logger.info("[%s] Discovered %d un-indexed candidate photos at top of gallery", group_slug, len(discovered_new_fbids))

        # Process discovered new photos
        for item in discovered_new_fbids:
            fbid = item["fbid"]
            photo_url = item["url"]
            stats["new_photos_found"] += 1

            logger.info("[%s] Inspecting candidate photo FBID=%s...", group_slug, fbid)
            try:
                info = await inspect_photo_page(page, photo_url)
            except Exception as e:
                logger.warning("[%s] Failed to inspect photo %s: %s", group_slug, fbid, e)
                continue

            found_post_id = info.get("post_id")
            p_id = str(found_post_id) if (found_post_id and str(found_post_id) != str(fbid)) else str(fbid)

            # Check 1: Old post check
            if p_id in known_post_ids:
                logger.info("[%s] Post %s is already in DB -> SKIPPING (bài cũ)", group_slug, p_id)
                stats["skipped_old_posts"] += 1
                known_fbids.add(fbid)
                continue

            # Check 2: 3-day time window check
            dt_posted = parse_timestamp(None, info.get("timestamp_str")) if info.get("timestamp_str") else None
            if not is_within_3_days(dt_posted, info.get("timestamp_str")):
                logger.info("[%s] Post %s timestamp (%s) is older than 3 days -> SKIPPING", group_slug, p_id, info.get("timestamp_str"))
                stats["skipped_older_than_3d"] += 1
                continue

            # Ingest new post within 3 days
            img_src = info.get("img_src")
            if not img_src:
                logger.warning("[%s] No image found for photo FBID=%s", group_slug, fbid)
                continue

            res = await downloader.download(img_src)
            post_uuid = str(uuid.uuid4())
            named_image_path = layout.group_post_image_path(group_slug, post_uuid, 0, res.ext)
            named_image_path.parent.mkdir(parents=True, exist_ok=True)
            named_image_path.write_bytes(res.content)
            file_path = await MediaDownloader.save_to_disk(layout, res)
            rel_uri = str(file_path.relative_to(layout.root))

            # OCR CIC extraction
            cic_report = await CICExtractor.extract_from_image(named_image_path)

            m_id = str(uuid.uuid4())
            meta_dict = {
                "id": m_id,
                "media_type": "image",
                "source_url": img_src,
                "owner_type": "post",
                "owner_id": post_uuid,
                "photo_fbid": fbid,
                "position": 0,
                "storage_uri": rel_uri,
                "sha256": res.sha256,
                "mime_type": res.mime_type,
                "file_size": res.file_size,
                "download_status": "downloaded",
                "ocr_status": "complete",
                "ocr_text": cic_report.raw_text[:1000] if cic_report.raw_text else None,
            }
            layout.media_meta_path(m_id).parent.mkdir(parents=True, exist_ok=True)
            layout.media_meta_path(m_id).write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")

            # Actor upsert
            is_anon = info.get("is_anonymous", False)
            author_name = info.get("author_name") or ("Anonymous participant" if is_anon else "Unknown")
            author_rec, _ = await actor_repo.upsert({
                "facebook_user_id": None,
                "profile_url": info.get("author_profile_url"),
                "display_name": author_name,
                "is_anonymous": is_anon,
                "anonymous_scope_post_id": str(p_id) if is_anon else None,
            })

            post_data = {
                "id": post_uuid,
                "facebook_post_id": str(p_id),
                "group_id": numeric_gid,
                "group_slug": group_slug,
                "author_id": author_rec["id"],
                "author_display_name": author_name,
                "author_profile_url": info.get("author_profile_url"),
                "author_is_anonymous": is_anon,
                "post_url": info.get("post_url") or f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{numeric_gid}",
                "title": (info.get("caption") or "")[:100],
                "title_source": "derived",
                "content": info.get("caption") or "",
                "posted_at": dt_posted.isoformat() if dt_posted else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "crawl_status": "COMPLETED",
                "media_ids": [m_id],
                "cic_data": cic_report.to_dict() if cic_report.is_cic else None,
            }

            (posts_dir / f"{post_uuid}.json").write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
            known_post_ids.add(str(p_id))
            known_fbids.add(fbid)
            stats["new_posts_saved"] += 1
            logger.info("[%s] Saved new post %s (FBID=%s, author=%s)", group_slug, post_uuid, fbid, author_name)

            if cic_report.is_cic:
                lead_entry = {
                    "post_id": post_uuid,
                    "facebook_post_id": str(p_id),
                    "media_id": m_id,
                    "lead_source": "post",
                    "author_display_name": author_name,
                    "author_profile_url": info.get("author_profile_url"),
                    "author_is_anonymous": is_anon,
                    "post_url": post_data["post_url"],
                    "score": cic_report.score,
                    "credit_tier": cic_report.tier,
                    "scoring_date": cic_report.scoring_date,
                    "customer_name": cic_report.customer_name,
                    "id_card_number": cic_report.id_card_number,
                    "phone_number": cic_report.phone_number,
                    "cic_code": cic_report.cic_code,
                    "has_bad_debt": cic_report.has_bad_debt,
                    "overdue_amount": cic_report.total_debt,
                    "provider": cic_report.provider,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
                leads.append(lead_entry)
                leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
                stats["new_cic_leads"] += 1
                logger.info("[%s] -> [NEW CIC FOUND] score=%s tier=%s date=%s customer=%s debt=%s",
                            group_slug, cic_report.score, cic_report.tier, cic_report.scoring_date, cic_report.customer_name, cic_report.total_debt)

            # Prepend to order and state
            existing_state[fbid] = {
                "status": "crawled_cic_found" if cic_report.is_cic else "crawled_no_cic",
                "post_id": p_id,
                "post_uuid": post_uuid,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            state_file.write_text(json.dumps(existing_state, ensure_ascii=False, indent=2), encoding="utf-8")
            existing_order.insert(0, {"fbid": fbid, "url": photo_url, "order_index": 0})
            order_file.write_text(json.dumps(existing_order, ensure_ascii=False, indent=2), encoding="utf-8")

            await asyncio.sleep(random.uniform(4.0, 7.0))

    except Exception as e_grp:
        logger.error("[%s] Error checking group: %s", group_slug, e_grp, exc_info=True)
    finally:
        await page.close()

    logger.info("[%s] SCAN COMPLETED: New Posts Saved=%d | New CIC Leads=%d | Skipped Old Posts=%d | Skipped >3d=%d",
                group_slug, stats["new_posts_saved"], stats["new_cic_leads"], stats["skipped_old_posts"], stats["skipped_older_than_3d"])
    return stats


async def main():
    logger.info(">>> INCREMENTAL 3-DAY CRAWLER STARTING FOR ALL GROUPS <<<")
    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    downloader = MediaDownloader()
    browser_state = "data/browser_state/default.json"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
        context = await BrowserFactory.create_context(browser, config.browser, browser_state)

        all_stats = []
        for g in GROUPS:
            stats = await crawl_group_recent(g, context, layout, downloader)
            all_stats.append(stats)
            await asyncio.sleep(5)

        await browser.close()

    logger.info("================================================================================")
    logger.info("INCREMENTAL 3-DAY CRAWL FINISHED FOR ALL GROUPS!")
    logger.info("Summary: %s", json.dumps(all_stats, ensure_ascii=False, indent=2))
    logger.info("================================================================================")


if __name__ == "__main__":
    asyncio.run(main())
