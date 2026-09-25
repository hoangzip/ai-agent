"""
scripts/backfill_missing_media.py — Re-visit posts with empty media_ids,
extract their photos with the fixed MediaDetector, download images,
and run OCR + CIC/debt extraction.
"""
import asyncio
import json
import logging
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import load_config
from collector.facebook.browser import BrowserFactory
from collector.facebook.media import MediaDetector
from collector.pipeline.normalizer import parse_timestamp, clean_facebook_url
from collector.analysis.cic_extractor import CICExtractor
from collector.downloaders.media_downloader import MediaDownloader
from collector.storage.layout import StorageLayout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")

GROUP_SLUG = "978769317924542"


async def main():
    config = load_config("config/crawler.yaml")
    layout = StorageLayout("data")
    posts_dir = layout.group_posts_dir(GROUP_SLUG)
    leads_path = layout.group_cic_leads_path(GROUP_SLUG)

    leads = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []

    # Identify posts that need media inspection
    target_posts = []
    for p in sorted(posts_dir.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("media_ids") and d.get("post_url"):
            target_posts.append((p, d))

    logger.info("Found %d posts with empty media_ids needing inspection", len(target_posts))
    if not target_posts:
        logger.info("All posts already have media_ids!")
        return

    downloader = MediaDownloader()
    browser_state = "data/browser_state/default.json"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser)
        context = await BrowserFactory.create_context(browser, config.browser, browser_state)
        page = await context.new_page()

        total_new_media = 0
        total_cic_found = 0

        for idx, (post_path, post_data) in enumerate(target_posts):
            post_id = post_data["id"]
            fb_id = post_data.get("facebook_post_id")
            post_url = post_data["post_url"]

            logger.info("[%d/%d] Inspecting post fb_id=%s...", idx + 1, len(target_posts), fb_id)

            try:
                await page.goto(post_url, wait_until="commit", timeout=25_000)
                await asyncio.sleep(2.5)
            except Exception as e:
                logger.warning("Goto timeout/error for %s: %s — continuing", post_url, e)

            # 1. Extract post media
            discovered_media = []
            try:
                discovered_media = await MediaDetector.extract_post_media(page)
            except Exception as e:
                logger.warning("Media detection error on %s: %s", post_url, e)

            # 2. Extract timestamp if missing
            if not post_data.get("posted_at"):
                try:
                    time_cands = await page.query_selector_all("abbr, a[role='link'] span, a[href*='/posts/'] span, a[href*='/permalink/'] span")
                    for tc in time_cands:
                        aria = await tc.get_attribute("aria-label") or ""
                        txt = (await tc.inner_text()).strip()
                        cand = aria or txt
                        if cand and any(w in cand.lower() for w in ("tháng", "ngày", "giờ", "phút", "hôm", "ago", "w", "d", "h", "m")):
                            parsed_ts = parse_timestamp(None, cand)
                            if parsed_ts:
                                post_data["posted_at"] = parsed_ts.isoformat()
                                break
                except Exception:
                    pass

            # 3. Extract author if missing
            if not post_data.get("author_display_name") and not post_data.get("author_is_anonymous"):
                try:
                    author_cands = await page.query_selector_all("h2 a, h3 a, strong a, div[role='article'] h2, div[role='article'] strong")
                    for a in author_cands:
                        txt = (await a.inner_text()).strip()
                        if txt and txt != "CHECK CIC - HỖ TRỢ VAY NGÂN HÀNG" and len(txt) > 2:
                            post_data["author_display_name"] = txt
                            break
                except Exception:
                    pass

            if not discovered_media:
                # Post truly has no media
                post_path.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
                continue

            logger.info("  -> Found %d media items for post %s!", len(discovered_media), fb_id)

            # 4. Download and process media
            media_ids = list(post_data.get("media_ids") or [])
            merged_cic = dict(post_data.get("cic_data") or {})

            for pos, m in enumerate(discovered_media):
                src = m["source_url"]
                try:
                    res = await downloader.download(src)
                    total_new_media += 1

                    # Save to group images folder
                    named_image_path = layout.group_post_image_path(GROUP_SLUG, post_id, pos, res.ext)
                    named_image_path.parent.mkdir(parents=True, exist_ok=True)
                    named_image_path.write_bytes(res.content)

                    # Save to sharded disk path
                    file_path = await MediaDownloader.save_to_disk(layout, res)
                    rel_uri = str(file_path.relative_to(layout.root))

                    # Run CIC extraction
                    info = await CICExtractor.extract_from_image(named_image_path)

                    # Generate media record
                    import uuid
                    m_id = str(uuid.uuid4())
                    meta_path = layout.media_meta_path(m_id)
                    meta_path.parent.mkdir(parents=True, exist_ok=True)

                    meta_dict = {
                        "id": m_id,
                        "media_type": m.get("media_type", "image"),
                        "source_url": src,
                        "owner_type": "post",
                        "owner_id": post_id,
                        "position": pos,
                        "storage_uri": rel_uri,
                        "sha256": res.sha256,
                        "mime_type": res.mime_type,
                        "file_size": res.file_size,
                        "download_status": "downloaded",
                        "ocr_status": "complete",
                        "ocr_text": info.raw_text[:1000] if info.raw_text else None,
                    }

                    if info.is_cic:
                        total_cic_found += 1
                        cic_dict = info.to_dict()
                        meta_dict["cic_data"] = cic_dict
                        logger.info("  -> [CIC REPORT] score=%s tier=%s customer=%s cccd=%s debt=%s",
                                    info.score, info.tier, info.customer_name, info.id_card_number, info.total_debt)

                        # Merge into post cic_data
                        for k, v in cic_dict.items():
                            if k not in merged_cic or (merged_cic[k] is None and v is not None):
                                merged_cic[k] = v
                            elif k in ("score", "tier", "total_debt", "has_bad_debt", "customer_name", "id_card_number") and v is not None:
                                merged_cic[k] = v

                        # Upsert into cic_customers.json
                        if any(merged_cic.get(k) for k in ("customer_name", "id_card_number", "cic_code", "score")):
                            lead_entry = {
                                "post_id": post_id,
                                "post_url": post_url,
                                "media_id": m_id,
                                "customer_name": merged_cic.get("customer_name"),
                                "date_of_birth": merged_cic.get("date_of_birth"),
                                "cic_code": merged_cic.get("cic_code"),
                                "address": merged_cic.get("address"),
                                "phone_number": merged_cic.get("phone_number"),
                                "id_card_number": merged_cic.get("id_card_number"),
                                "score": merged_cic.get("score"),
                                "tier": merged_cic.get("tier"),
                                "scoring_date": merged_cic.get("scoring_date"),
                                "provider": merged_cic.get("provider"),
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

                    meta_path.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")
                    if m_id not in media_ids:
                        media_ids.append(m_id)

                except Exception as e:
                    logger.warning("Error downloading/processing media for post %s: %s", fb_id, e)

            post_data["media_ids"] = media_ids
            if merged_cic:
                post_data["cic_data"] = merged_cic

            post_path.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
            leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

        await browser.close()

    logger.info("=== BACKFILL FINISHED ===")
    logger.info("Total new media downloaded: %d", total_new_media)
    logger.info("Total CIC/debt reports extracted: %d", total_cic_found)
    logger.info("Total leads in cic_customers.json: %d", len(leads))


if __name__ == "__main__":
    asyncio.run(main())
