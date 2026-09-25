"""
scripts/crawl_media_gallery_sequential.py — Sequential Media Gallery Crawler.

Follows user requirements strictly:
1. Only crawl posts inside group Media gallery:
   https://web.facebook.com/groups/978769317924542/media
2. Process photos sequentially from left to right, row by row, until the end.
3. Download and OCR parse CIC information ONLY from post images (never comments, never ads).
4. Skip posts that are already crawled and have complete CIC information.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
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
from collector.pipeline.normalizer import clean_facebook_url, parse_timestamp, is_anonymous_user
from collector.analysis.cic_extractor import CICExtractor
from collector.downloaders.media_downloader import MediaDownloader
from collector.facebook.comment_cic import extract_comment_photos_from_page, process_comment_cic_photo
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("media_crawler")

GROUP_SLUG = "978769317924542"
POST_ID_RE = re.compile(r"/(?:posts|permalink)/(\d+)")
FBID_RE = re.compile(r"fbid=(\d+)")


def _slugify(text: str | None) -> str:
    if not text:
        return "unknown"
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    clean = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean) or "unknown"


def has_complete_cic(post_data: dict | None) -> bool:
    """Check if post already has complete CIC/debt information."""
    if not post_data:
        return False
    cic = post_data.get("cic_data")
    if not isinstance(cic, dict):
        return False
    # Check for verified CIC or debt record
    return bool(
        cic.get("is_cic") or
        cic.get("score") is not None or
        cic.get("customer_name") or
        cic.get("id_card_number") or
        cic.get("cic_code") or
        cic.get("has_bad_debt") or
        cic.get("overdue_amount")
    )


async def collect_media_gallery_order(
    page,
    group_slug: str,
    max_scrolls: int = 200,
    stop_on_known_fbids: set[str] | None = None,
    stop_threshold: int = 5,
) -> list[dict]:
    """
    Scroll /media to collect all photos in natural grid order:
    left-to-right, row-by-row (top-to-bottom).
    If stop_on_known_fbids is provided, stops early when encountering
    stop_threshold consecutive known photos (delta / incremental mode).
    """
    media_url = f"https://web.facebook.com/groups/{group_slug}/media"
    logger.info("Collecting media gallery order from %s ...", media_url)
    
    await page.goto(media_url, wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(4)
    
    ordered_photos: list[dict] = []
    seen_fbids: set[str] = set()
    no_new_rounds = 0
    max_no_new = 15
    consecutive_known = 0
    hit_known_boundary = False

    for scroll_i in range(max_scrolls):
        # Extract visible photo links with bounding box coordinates
        raw_items = await page.evaluate(f"""() => {{
            const els = Array.from(document.querySelectorAll("a[href*='set=g.{group_slug}']"));
            return els.map(a => {{
                const rect = a.getBoundingClientRect();
                return {{
                    href: a.href,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y + window.scrollY),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                }};
            }});
        }}""")

        # Filter valid items and sort by (y_bucket, x) to strictly enforce row-by-row, left-to-right order
        valid_items = [it for it in raw_items if it.get("href") and it.get("w", 0) > 30]
        valid_items.sort(key=lambda it: (round(it["y"] / 40) * 40, it["x"]))

        added_this_round = 0
        for it in valid_items:
            href = it["href"]
            m = FBID_RE.search(href)
            if not m:
                continue
            fbid = m.group(1)

            # Check incremental boundary
            if stop_on_known_fbids and fbid in stop_on_known_fbids:
                consecutive_known += 1
                if consecutive_known >= stop_threshold:
                    logger.info("Incremental check: reached %d consecutive known photos -> reached historical boundary!", consecutive_known)
                    hit_known_boundary = True
                    break
            else:
                consecutive_known = 0

            if fbid not in seen_fbids:
                seen_fbids.add(fbid)
                clean_href = f"https://web.facebook.com/photo/?fbid={fbid}&set=g.{group_slug}"
                ordered_photos.append({
                    "fbid": fbid,
                    "url": clean_href,
                    "x": it["x"],
                    "y": it["y"],
                    "order_index": len(ordered_photos)
                })
                added_this_round += 1

        if hit_known_boundary:
            break

        if added_this_round == 0:
            no_new_rounds += 1
            if no_new_rounds >= max_no_new:
                logger.info("Reached end of media gallery at scroll %d (total=%d photos)", scroll_i, len(ordered_photos))
                break
        else:
            no_new_rounds = 0
            logger.info("Scroll %d: +%d new photos (total=%d)", scroll_i, added_this_round, len(ordered_photos))

        # Scroll down smoothly
        await page.evaluate("window.scrollBy(0, window.innerHeight * 2);")
        await asyncio.sleep(1.2)

    return ordered_photos


async def inspect_photo_page(page, photo_url: str) -> dict:
    """
    Load photo page, extract post ID, author, timestamp, caption, and the post image.
    Guaranteed: ONLY extracts post image, never comment images, never ads.
    """
    await page.goto(photo_url, wait_until="domcontentloaded", timeout=35_000)
    await asyncio.sleep(2.5)

    post_url = None
    post_id = None
    timestamp_str = None

    # 1. Extract Author BEFORE hover (to prevent hover events from altering header DOM)
    author_info = await page.evaluate("""() => {
        // Strategy A: Find post author from ancestor of the post permalink / timestamp link
        const ts = document.querySelector("a[href*='/posts/'], a[href*='/permalink/']");
        if (ts) {
            let p = ts;
            for (let i = 0; i < 10; i++) {
                if (!p.parentElement) break;
                p = p.parentElement;
                for (let h2 of p.querySelectorAll("h2")) {
                    const txt = h2.innerText.trim();
                    if (txt && !txt.includes('Bình luận') && !txt.includes('Comments') && !txt.includes('Chia sẻ') && txt !== 'New' && !txt.includes('No comments yet')) {
                        const a = h2.querySelector("a[href*='/user/'], a[href*='profile.php'], a[role='link']");
                        return { name: txt, url: a ? a.href : null };
                    }
                }
            }
        }
        // Strategy B: Search top h2 elements on page before comments
        for (let h2 of document.querySelectorAll("h2")) {
            const txt = h2.innerText.trim();
            if (txt && !txt.includes('Bình luận') && !txt.includes('Comments') && !txt.includes('Chia sẻ') && txt !== 'New' && !txt.includes('No comments yet')) {
                const a = h2.querySelector("a[href*='/user/'], a[href*='profile.php'], a[role='link']");
                return { name: txt, url: a ? a.href : null };
            }
        }
        return null;
    }""")

    author_name = None
    author_profile_url = None
    is_anon = False

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
        elif raw_name and raw_name != "CHECK CIC - HỖ TRỢ VAY NGÂN HÀNG" and len(raw_name) > 1:
            author_name = raw_name
            author_profile_url = clean_facebook_url(raw_url) if raw_url else None
            is_anon = False

            # Check Facebook's ground-truth "Report nickname" (Báo cáo biệt danh) on hover
            a_el = await page.query_selector("h2 a[href*='/user/'], h2 a[role='link']")
            if a_el:
                try:
                    await a_el.hover(timeout=2500, force=True)
                    await asyncio.sleep(0.6)
                    has_report_nick = await page.evaluate("""() => {
                        for (let el of document.querySelectorAll("div[role='dialog'], div[data-pagelet*='ProfileHovercard'], div[role='tooltip']")) {
                            const txt = el.innerText.toLowerCase();
                            if (txt.includes('report nickname') || txt.includes('báo cáo biệt danh') || txt.includes('with a nickname') || txt.includes('bằng một biệt danh')) {
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if has_report_nick:
                        is_anon = True
                        author_profile_url = None
                except Exception:
                    pass

    # 2. Find exact post permalink link (matching /posts/ or /permalink/) and extract post URL + timestamp
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
            await ts_link.hover(timeout=2500, force=True)
            await asyncio.sleep(0.8)
        except Exception:
            pass

        tooltips = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll("div[role='tooltip']")).map(el => el.innerText.trim()).filter(Boolean);
        }""")
        if tooltips:
            timestamp_str = tooltips[0]
        else:
            aria = await ts_link.get_attribute("aria-label")
            txt = (await ts_link.inner_text()).strip()
            if aria:
                timestamp_str = aria
            elif txt:
                timestamp_str = txt
            else:
                # Fallback to abbr / data-utime / aria-label
                timestamp_str = await page.evaluate("""() => {
                    for (let el of document.querySelectorAll("abbr, [data-utime]")) {
                        const aria = el.getAttribute("aria-label");
                        const utime = el.getAttribute("data-utime");
                        const txt = el.innerText.trim();
                        if (aria) return aria;
                        if (utime) return utime;
                        if (txt) return txt;
                    }
                    return null;
                }""")

    # 3. Extract Caption / Message Text
    caption = None
    msg_el = await page.query_selector("div[data-ad-preview='message'], div[data-ad-comet-preview='message']")
    if msg_el:
        caption = (await msg_el.inner_text()).strip()

    # 4. Extract Post Image strictly from MediaViewerPhoto
    img_src = None
    img_el = await page.query_selector(
        "div[data-pagelet='MediaViewerPhoto'] img, "
        "img[data-visualcompletion='media-vc-image']"
    )
    if img_el:
        img_src = await img_el.get_attribute("src")

    # Fallback for largest image in photo viewer if selector differs
    if not img_src:
        largest = await page.evaluate("""() => {
            let maxArea = 0;
            let bestSrc = null;
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
        img_src = largest

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


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Facebook Group Media Gallery & CIC Crawler")
    parser.add_argument("--group", type=str, default="978769317924542", help="Facebook group slug or ID (e.g. 978769317924542)")
    parser.add_argument("--limit", type=int, default=None, help="Stop after crawling N posts")
    parser.add_argument("--update-new", action="store_true", help="Incremental mode: crawl only new photos published since the last crawl")
    parser.add_argument("--check-comments", action="store_true", help="Also check and extract comment CIC photos for each post")
    args, _ = parser.parse_known_args()

    group_slug = args.group
    logger.info("Initializing crawler for group: %s (mode: %s)", group_slug, "INCREMENTAL (--update-new)" if args.update_new else "STANDARD")

    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    posts_dir = layout.group_posts_dir(group_slug)
    posts_dir.mkdir(parents=True, exist_ok=True)
    leads_path = layout.group_cic_leads_path(group_slug)
    order_file = Path(f"data/groups/{group_slug}/media_gallery_order.json")
    state_file = Path(f"data/groups/{group_slug}/media_gallery_state.json")
    checked_comments_file = Path(f"data/groups/{group_slug}/checked_comment_posts.json")

    # Load leads
    leads = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []

    # Build DB index
    posts_by_fb_id: dict[str, tuple[Path, dict]] = {}
    for p in posts_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            fbid = d.get("facebook_post_id")
            if fbid:
                posts_by_fb_id[str(fbid)] = (p, d)
        except Exception:
            pass

    logger.info("Indexed %d existing posts in DB (%d with complete CIC info)",
                len(posts_by_fb_id),
                sum(1 for _, d in posts_by_fb_id.values() if has_complete_cic(d)))

    # Load state
    state: dict = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

    # Load checked comments tracker
    checked_comment_post_ids: set[str] = set()
    if checked_comments_file.exists():
        try:
            checked_comment_post_ids = set(json.loads(checked_comments_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    actor_repo = ActorRepo(layout, group_slug)
    downloader = MediaDownloader()
    browser_state = "data/browser_state/default.json"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        context = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await context.new_page()
        comment_page = await context.new_page() if getattr(args, "check_comments", False) else None
        photo_page = await context.new_page() if getattr(args, "check_comments", False) else None

        # Step 1: Collect /media gallery order
        if args.update_new and order_file.exists():
            existing_order = json.loads(order_file.read_text(encoding="utf-8"))
            known_fbids = set(str(item["fbid"]) for item in existing_order if "fbid" in item)
            logger.info("Incremental Mode (--update-new): Checking for new photos against %d existing items...", len(known_fbids))

            new_order_items = await collect_media_gallery_order(
                page, group_slug, stop_on_known_fbids=known_fbids, stop_threshold=5
            )
            really_new = [item for item in new_order_items if str(item["fbid"]) not in known_fbids]

            if really_new:
                logger.info("Discovered %d NEW photos! Prepending to media_gallery_order.json...", len(really_new))
                ordered_photos = really_new + existing_order
                order_file.write_text(json.dumps(ordered_photos, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                logger.info("No new photos found since last run for group %s. Continuing with existing queue...", group_slug)
                ordered_photos = existing_order
            photos_to_crawl = ordered_photos
        elif order_file.exists():
            ordered_photos = json.loads(order_file.read_text(encoding="utf-8"))
            logger.info("Loaded %d ordered photos from %s", len(ordered_photos), order_file)
            photos_to_crawl = ordered_photos
        else:
            ordered_photos = await collect_media_gallery_order(page, group_slug)
            order_file.write_text(json.dumps(ordered_photos, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Saved %d ordered photos to %s", len(ordered_photos), order_file)
            photos_to_crawl = ordered_photos

        total_photos = len(photos_to_crawl)
        logger.info("Starting processing of %d photos...", total_photos)

        processed_count = 0
        skipped_count = 0
        new_posts_count = 0
        cic_found_count = 0

        for idx, item in enumerate(photos_to_crawl):
            fbid = item["fbid"]
            photo_url = item["url"]

            # Check if this photo was already visited and resolved
            prev_info = state.get(fbid)
            if prev_info and prev_info.get("status") in ("skipped_complete_cic", "crawled_cic_found", "crawled_no_cic"):
                skipped_count += 1
                continue

            logger.info("[%d/%d] Inspecting photo FBID=%s...", idx + 1, total_photos, fbid)

            # Inspect photo page with automatic retry on network disconnect
            info = None
            for attempt in range(3):
                try:
                    info = await inspect_photo_page(page, photo_url)
                    break
                except Exception as e:
                    err_msg = str(e)
                    is_net_err = any(net_code in err_msg for net_code in ("ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_TIMED_OUT"))
                    if is_net_err:
                        wait_sec = (attempt + 1) * 10
                        logger.warning("[%d/%d] Network error on photo %s (attempt %d/3). Waiting %ds to retry...",
                                       idx + 1, total_photos, fbid, attempt + 1, wait_sec)
                        await asyncio.sleep(wait_sec)
                        if attempt == 2:
                            logger.error("Persistent network disconnection detected. Stopping crawl to preserve progress.")
                            if comment_page:
                                await comment_page.close()
                            if photo_page:
                                await photo_page.close()
                            await browser.close()
                            return
                    else:
                        logger.warning("[%d/%d] Error loading photo %s: %s", idx + 1, total_photos, fbid, e)
                        state[fbid] = {"status": "error", "error": err_msg}
                        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                        break

            if not info:
                continue

            found_post_id = info.get("post_id")
            raw_purl = info.get("post_url")
            if found_post_id and str(found_post_id) != str(fbid) and raw_purl and "recover/initiate" not in raw_purl and ("posts" in raw_purl or "permalink" in raw_purl):
                post_id = str(found_post_id)
                post_url = raw_purl
            else:
                # Standalone photo upload: the canonical working Facebook URL is photo/?fbid=
                post_id = str(fbid)
                post_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{group_slug}"

            # Step 4: Check if post already crawled and has complete CIC information
            existing_entry = posts_by_fb_id.get(str(post_id))
            if existing_entry:
                post_path, post_data = existing_entry
                if has_complete_cic(post_data):
                    logger.info("[%d/%d] Post %s already crawled with complete CIC info -> SKIPPING",
                                idx + 1, total_photos, post_id)
                    state[fbid] = {
                        "status": "skipped_complete_cic",
                        "post_id": post_id,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    skipped_count += 1
                    continue
            else:
                post_path = None
                post_data = None

            # Not skipped: download post image and run OCR/CIC
            img_src = info.get("img_src")
            if not img_src:
                logger.warning("[%d/%d] No image found for photo %s (post %s)", idx + 1, total_photos, fbid, post_id)
                state[fbid] = {"status": "no_image", "post_id": post_id}
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                continue

            # Download post image
            try:
                res = await downloader.download(img_src)
            except Exception as e:
                logger.warning("[%d/%d] Failed to download image for post %s: %s", idx + 1, total_photos, post_id, e)
                continue

            # Determine post UUID and file paths
            if post_data:
                post_uuid = post_data["id"]
            else:
                post_uuid = str(uuid.uuid4())
                post_path = posts_dir / f"{post_uuid}.json"

            # Save named post image to data/groups/{group_slug}/images/posts/{post_uuid}_0.{ext}
            named_image_path = layout.group_post_image_path(group_slug, post_uuid, 0, res.ext)
            named_image_path.parent.mkdir(parents=True, exist_ok=True)
            named_image_path.write_bytes(res.content)

            # Save to sharded disk path
            file_path = await MediaDownloader.save_to_disk(layout, res)
            rel_uri = str(file_path.relative_to(layout.root))

            # Step 3: Run OCR + CIC extraction strictly on post image
            cic_report = await CICExtractor.extract_from_image(named_image_path)
            
            # Create media metadata record with standard UUID
            m_id = str(uuid.uuid4())
            meta_path = layout.media_meta_path(m_id)
            meta_path.parent.mkdir(parents=True, exist_ok=True)
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

            now_iso = datetime.now(timezone.utc).isoformat()

            # Parse posted_at if timestamp_str available
            posted_at_iso = None
            if info.get("timestamp_str"):
                dt = parse_timestamp(None, info["timestamp_str"])
                if dt:
                    posted_at_iso = dt.isoformat()

            # Resolve or create actor record
            is_anon = info.get("is_anonymous", False)
            author_name = info.get("author_name")
            author_profile_url = info.get("author_profile_url")

            # Fallback to existing post data only if info is None AND post_data didn't have invalid UI values
            if not author_name and post_data:
                ex_name = post_data.get("author_display_name")
                if ex_name and ex_name != "Notifications":
                    author_name = ex_name
                    author_profile_url = post_data.get("author_profile_url")
                    is_anon = post_data.get("author_is_anonymous", False)

            if author_name:
                is_anon = is_anon or is_anonymous_user(author_name, author_profile_url) or any(w in author_name.lower() for w in ("anonymous", "ẩn danh"))

            author_id = None
            if author_name or author_profile_url or is_anon:
                fb_uid = None
                if author_profile_url and not is_anon:
                    m_user = re.search(r"/(?:user|profile\.php\?id=)/(\d+)", author_profile_url)
                    if m_user:
                        fb_uid = m_user.group(1)

                try:
                    actor_rec, _ = await actor_repo.upsert({
                        "facebook_user_id": fb_uid,
                        "profile_url": author_profile_url if not is_anon else None,
                        "display_name": author_name or "Anonymous participant",
                        "is_anonymous": is_anon,
                        "anonymous_scope_post_id": str(post_id) if is_anon else None,
                    })
                    author_id = actor_rec["id"]
                except Exception as e_actor:
                    logger.debug("Error upserting actor for post %s: %s", post_id, e_actor)

            # Update or create post dict
            if post_data is None:
                post_data = {
                    "id": post_uuid,
                    "facebook_post_id": str(post_id),
                    "group_id": group_slug,
                    "group_slug": group_slug,
                    "author_id": author_id,
                    "author_display_name": author_name,
                    "author_profile_url": author_profile_url if not is_anon else None,
                    "author_is_anonymous": is_anon,
                    "post_url": post_url,
                    "title": (info.get("caption") or "")[:100],
                    "title_source": "derived",
                    "content": info.get("caption") or "",
                    "posted_at": posted_at_iso,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "crawl_status": "COMPLETED",
                    "media_ids": [m_id],
                    "cic_data": None
                }
                new_posts_count += 1
            else:
                post_data["updated_at"] = now_iso
                if author_id:
                    post_data["author_id"] = author_id
                if posted_at_iso and not post_data.get("posted_at"):
                    post_data["posted_at"] = posted_at_iso
                if author_name:
                    post_data["author_display_name"] = author_name
                post_data["author_profile_url"] = author_profile_url if not is_anon else None
                post_data["author_is_anonymous"] = is_anon
                if info.get("caption") and not post_data.get("content"):
                    post_data["content"] = info["caption"]
                media_ids = list(post_data.get("media_ids") or [])
                if m_id not in media_ids:
                    media_ids.append(m_id)
                post_data["media_ids"] = media_ids

            if cic_report.is_cic:
                cic_dict = cic_report.to_dict()

                # Check for phone number in caption if image OCR didn't catch one
                phone_num = cic_dict.get("phone_number")
                if not phone_num and info.get("caption"):
                    m_cap_phone = re.search(r"\b(0(?:3[2-9]|5[6-9]|7[06-9]|8[1-9]|9[0-9])[.\s-]?\d{3}[.\s-]?\d{4})\b", info["caption"])
                    if m_cap_phone:
                        phone_num = re.sub(r"[^\d]", "", m_cap_phone.group(1))
                        cic_dict["phone_number"] = phone_num

                meta_dict["cic_data"] = cic_dict
                post_data["cic_data"] = cic_dict
                cic_found_count += 1
                logger.info("  -> [CIC FOUND] score=%s tier=%s date=%s customer=%s cccd=%s sđt=%s debt=%s provider=%s",
                            cic_report.score, cic_report.tier, cic_report.scoring_date,
                            cic_dict.get("customer_name"), cic_dict.get("id_card_number"),
                            phone_num, cic_dict.get("total_debt"), cic_report.provider)

                # Upsert to cic_customers.json
                img_filename = f"{post_uuid}_0.{res.ext}"
                lead_entry = {
                    "lead_source": "post",
                    "post_id": post_uuid,
                    "facebook_post_id": str(post_id),
                    "post_url": post_url,
                    "media_id": m_id,
                    "image_file": img_filename,
                    "image_path": f"groups/{group_slug}/images/posts/{img_filename}",
                    "author_id": author_id,
                    "author_display_name": post_data.get("author_display_name"),
                    "author_profile_url": post_data.get("author_profile_url"),
                    "author_is_anonymous": post_data.get("author_is_anonymous"),
                    "customer_name": cic_dict.get("customer_name"),
                    "id_card_number": cic_dict.get("id_card_number"),
                    "phone_number": phone_num,
                    "date_of_birth": cic_dict.get("date_of_birth"),
                    "cic_code": cic_dict.get("cic_code"),
                    "address": cic_dict.get("address"),
                    "score": cic_dict.get("score"),
                    "tier": cic_dict.get("tier"),
                    "scoring_date": cic_dict.get("scoring_date"),
                    "total_debt": cic_dict.get("total_debt"),
                    "has_bad_debt": cic_dict.get("has_bad_debt"),
                    "provider": cic_dict.get("provider"),
                }
                match_idx = -1
                for idx_lead, e in enumerate(leads):
                    if (lead_entry["cic_code"] and e.get("cic_code") == lead_entry["cic_code"]) or \
                       (lead_entry["id_card_number"] and e.get("id_card_number") == lead_entry["id_card_number"]) or \
                       (lead_entry["post_id"] and e.get("post_id") == lead_entry["post_id"]):
                        match_idx = idx_lead
                        break
                if match_idx >= 0:
                    leads[match_idx].update({k: v for k, v in lead_entry.items() if v is not None})
                else:
                    leads.append(lead_entry)

                leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

            # Write meta and post
            meta_path.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            post_path.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
            posts_by_fb_id[str(post_id)] = (post_path, post_data)

            # Update state
            state[fbid] = {
                "status": "crawled_cic_found" if cic_report.is_cic else "crawled_no_cic",
                "post_id": post_id,
                "post_uuid": post_uuid,
                "updated_at": now_iso
            }
            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

            # Step 5: Check and extract comment CIC photos if enabled (once per unique post_id)
            if getattr(args, "check_comments", False) and comment_page and photo_page and str(post_id) not in checked_comment_post_ids:
                checked_comment_post_ids.add(str(post_id))
                try:
                    checked_comments_file.write_text(json.dumps(sorted(list(checked_comment_post_ids)), ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

                try:
                    await comment_page.goto(post_url, wait_until="domcontentloaded", timeout=25_000)
                    await asyncio.sleep(2.0)

                    # Expand comments & replies
                    for _ in range(15):
                        more_btn = await comment_page.query_selector(
                            "span:has-text('View more comments'), span:has-text('Xem thêm bình luận'), div[role='button']:has-text('View more comments')"
                        )
                        if more_btn and await more_btn.is_visible():
                            try:
                                await more_btn.click()
                                await asyncio.sleep(1.0)
                            except Exception:
                                break
                        else:
                            break

                    reply_btns = await comment_page.query_selector_all("div[role='button']:has-text('replies'), div[role='button']:has-text('reply'), div[role='button']:has-text('câu trả lời')")
                    for b in reply_btns[:20]:
                        try:
                            if await b.is_visible():
                                await b.click()
                                await asyncio.sleep(0.5)
                        except Exception:
                            pass

                    c_photos = await extract_comment_photos_from_page(comment_page)
                    for c_item in c_photos:
                        c_lead = await process_comment_cic_photo(
                            photo_page=photo_page,
                            comment_data=c_item,
                            post_uuid=post_uuid,
                            facebook_post_id=str(post_id),
                            post_url=post_url,
                            group_slug=group_slug,
                            layout=layout,
                            downloader=downloader,
                            actor_repo=actor_repo,
                            post_fbid=fbid,
                        )
                        if c_lead:
                            cic_found_count += 1
                            # Deduplicate comment lead by author_profile_url, comment_id, or cic_code
                            matched_c = False
                            for idx_c, ex_c in enumerate(leads):
                                if c_lead.get("author_profile_url") and ex_c.get("author_profile_url") == c_lead.get("author_profile_url"):
                                    leads[idx_c].update(c_lead)
                                    matched_c = True
                                    break
                                elif c_lead.get("comment_id") and ex_c.get("comment_id") == c_lead.get("comment_id"):
                                    leads[idx_c].update(c_lead)
                                    matched_c = True
                                    break
                                elif c_lead.get("cic_code") and ex_c.get("cic_code") == c_lead.get("cic_code"):
                                    leads[idx_c].update(c_lead)
                                    matched_c = True
                                    break
                            if not matched_c:
                                leads.append(c_lead)

                            leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e_comm:
                    logger.debug("Error checking comments for post %s: %s", post_id, e_comm)

            processed_count += 1
            if args.limit and processed_count >= args.limit:
                logger.info("Reached requested limit of %d posts. Stopping crawl for review.", args.limit)
                break
            await asyncio.sleep(random.uniform(1.2, 2.0))

        if comment_page:
            await comment_page.close()
        if photo_page:
            await photo_page.close()
        await browser.close()

        logger.info("Media Gallery Sequential Crawl Finished!")
        logger.info("Summary: Total=%d | Processed=%d | Skipped (already had CIC)=%d | New Posts=%d | CIC Reports Found=%d",
                    total_photos, processed_count, skipped_count, new_posts_count, cic_found_count)


if __name__ == "__main__":
    asyncio.run(main())
