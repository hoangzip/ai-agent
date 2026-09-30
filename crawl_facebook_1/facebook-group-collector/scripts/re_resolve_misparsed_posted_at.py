"""
scripts/re_resolve_misparsed_posted_at.py — Fix misparsed posted_at dates
where full English month names caused the year (e.g. 2024, 2025) to be ignored
and defaulted to 2026.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright
from collector.pipeline.normalizer import parse_timestamp
from collector.facebook.browser import BrowserFactory
from collector.config import load_config
from export_leads_by_rule import run_export

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FIX_POSTED_AT] %(message)s"
)
logger = logging.getLogger("fix_posted_at")


def collect_affected_posts() -> list[dict]:
    data_dir = Path("data/groups")
    now = datetime.now(timezone.utc)
    targets = []
    seen_files = set()

    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        posts_dir = gdir / "posts"
        if not posts_dir.exists():
            continue

        for pf in sorted(posts_dir.glob("*.json")):
            if str(pf) in seen_files:
                continue
            seen_files.add(str(pf))

            try:
                pd = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                continue

            ts = pd.get("posted_at")
            if not ts:
                continue

            raw_iso = ts.replace(" ", "T")
            if not ("+" in raw_iso or raw_iso.endswith("Z")):
                raw_iso += "+00:00"
            try:
                dt = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
            except Exception:
                continue

            is_future = dt > now
            sc = (pd.get("cic_data") or {}).get("scoring_date") or ""
            is_year_mismatch = (dt.year == 2026 and ("2024" in sc or "2025" in sc))

            if is_future or is_year_mismatch:
                targets.append({
                    "group": gdir.name,
                    "post_file": str(pf),
                    "author": pd.get("author_display_name"),
                    "post_url": pd.get("post_url"),
                    "old_posted_at": ts,
                    "scoring_date": sc,
                    "reason": "FUTURE" if is_future else "YEAR_MISMATCH"
                })

    return targets


async def extract_exact_timestamp(page, url: str) -> str | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(1.5)

        # Strategy 1: Find link with /posts/ or /permalink/ and hover for tooltip
        ts_link = await page.query_selector("a[href*='/posts/'], a[href*='/permalink/']")
        if ts_link:
            try:
                await ts_link.hover(timeout=2000, force=True)
                await asyncio.sleep(0.5)
                tooltips = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll("div[role='tooltip']"))
                        .map(t => t.innerText.trim())
                        .filter(Boolean);
                }""")
                if tooltips:
                    dt = parse_timestamp(None, tooltips[0])
                    if dt:
                        return dt.isoformat()
            except Exception:
                pass

            # Fallback to aria-label or inner_text
            aria = await ts_link.get_attribute("aria-label")
            txt = (await ts_link.inner_text()).strip()
            for cand in [aria, txt]:
                if cand:
                    dt = parse_timestamp(None, cand)
                    if dt:
                        return dt.isoformat()

        # Strategy 2: Look for timestamp link near author h2 header
        cand_str = await page.evaluate("""() => {
            const h2 = document.querySelector("h2");
            if (!h2) return null;
            let p = h2.parentElement;
            for (let i = 0; i < 6; i++) {
                if (!p) break;
                for (let a of p.querySelectorAll("a")) {
                    const aria = a.getAttribute("aria-label") || "";
                    const txt = a.innerText.trim();
                    const href = a.href || "";
                    if (txt === h2.innerText.trim() || href.includes("/user/")) continue;
                    if (aria && !aria.toLowerCase().includes("thông báo")) return aria;
                    if (txt && !txt.toLowerCase().includes("thông báo") && txt.length < 50) return txt;
                }
                p = p.parentElement;
            }
            return null;
        }""")

        if cand_str:
            dt = parse_timestamp(None, cand_str)
            if dt:
                return dt.isoformat()

    except Exception as e:
        logger.debug("Error loading %s: %s", url, e)

    return None


async def run_fix():
    targets = collect_affected_posts()
    logger.info("Found %d posts needing timestamp re-resolution.", len(targets))

    if not targets:
        logger.info("No affected posts found.")
        return

    config = load_config("config/crawler.yaml")
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
        context = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
        page = await context.new_page()

        success_cnt = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for idx, t in enumerate(targets, 1):
            url = t["post_url"]
            if not url:
                continue

            logger.info("[%d/%d] Fixing %s (Old: %s, Scoring: %s)...",
                        idx, len(targets), t["author"], t["old_posted_at"][:10], t["scoring_date"])

            iso_ts = await extract_exact_timestamp(page, url)
            pf = Path(t["post_file"])

            if iso_ts:
                success_cnt += 1
                logger.info("  -> FIXED: %s => %s", t["old_posted_at"][:10], iso_ts[:10])
                try:
                    pd = json.loads(pf.read_text(encoding="utf-8"))
                    pd["posted_at"] = iso_ts
                    pd["updated_at"] = now_iso
                    pf.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.warning("Error writing %s: %s", pf, e)
            else:
                # If post was deleted on Facebook and had a future date (e.g. 2026-11-23 when scoring date was 2024),
                # adjust the year logically
                try:
                    pd = json.loads(pf.read_text(encoding="utf-8"))
                    old_dt = datetime.fromisoformat(t["old_posted_at"].replace(" ", "T").replace("Z", "+00:00"))
                    if old_dt > datetime.now(timezone.utc):
                        # Decrement year to 2024 if scoring was 2024, or 2025
                        target_year = 2024 if "2024" in t["scoring_date"] else 2025
                        new_dt = old_dt.replace(year=target_year)
                        new_iso = new_dt.isoformat()
                        pd["posted_at"] = new_iso
                        pd["updated_at"] = now_iso
                        pf.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
                        logger.info("  -> LOGICAL FALLBACK (post deleted): %s => %s", t["old_posted_at"][:10], new_iso[:10])
                        success_cnt += 1
                except Exception as e:
                    logger.warning("Could not apply fallback: %s", e)

            await asyncio.sleep(1.0)

        await browser.close()
        logger.info("Re-resolution finished! Updated %d / %d posts.", success_cnt, len(targets))

    # Regenerate export files
    logger.info("Refreshing cic_leads_filtered.csv and JSON...")
    run_export()
    logger.info("Refreshed successfully!")


if __name__ == "__main__":
    asyncio.run(run_fix())
