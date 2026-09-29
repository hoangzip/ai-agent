"""
scripts/backfill_posted_at_targeted.py — Backfill posted_at strictly for posts
with CIC score OR tier from real (non-anonymous) authors.

Scope: ~224 target posts across all groups.
Runtime: ~7-8 minutes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright
from collector.pipeline.normalizer import parse_timestamp
from collector.facebook.browser import BrowserFactory
from collector.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [POSTED_AT_BACKFILL] %(message)s"
)
logger = logging.getLogger("posted_at_backfill")


def collect_target_posts() -> list[dict]:
    data_dir = Path("data/groups")
    seen_groups = set()
    targets = []

    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        real_p = gdir.resolve()
        if real_p in seen_groups:
            continue
        seen_groups.add(real_p)

        leads_file = gdir / "cic_customers.json"
        posts_dir = gdir / "posts"
        if not leads_file.exists() or not posts_dir.exists():
            continue

        try:
            leads = json.loads(leads_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for l in leads:
            s, t = l.get("score"), l.get("tier")
            if not (s or t):
                continue
            is_anon = bool(l.get("author_is_anonymous"))
            has_phone = bool(l.get("phone_number"))
            if is_anon and not has_phone:
                continue

            post_id = l.get("post_id")
            pf = posts_dir / f"{post_id}.json"
            if not pf.exists():
                for cand in posts_dir.glob("*.json"):
                    try:
                        pd = json.loads(cand.read_text(encoding="utf-8"))
                        if pd.get("id") == post_id or pd.get("facebook_post_id") == str(l.get("facebook_post_id")):
                            pf = cand
                            break
                    except Exception:
                        pass

            if pf.exists():
                try:
                    pd = json.loads(pf.read_text(encoding="utf-8"))
                    if not pd.get("posted_at"):
                        targets.append({
                            "group": gdir.name,
                            "post_file": str(pf),
                            "post_id": pd.get("id"),
                            "fb_post_id": pd.get("facebook_post_id"),
                            "post_url": pd.get("post_url") or l.get("post_url"),
                            "author": pd.get("author_display_name") or l.get("author_display_name"),
                            "score": s,
                            "tier": t,
                        })
                except Exception:
                    pass

    # Deduplicate targets by post_file
    unique_map = {}
    for t in targets:
        unique_map[t["post_file"]] = t
    return list(unique_map.values())


async def extract_post_timestamp(page, url: str) -> str | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(1.8)

        # Dismiss notification dialogs
        await page.evaluate("""() => {
            for (let d of document.querySelectorAll("div[role='dialog'], div[role='region']")) {
                const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                const txt = (d.innerText || '').toLowerCase();
                if (aria.includes('notification') || txt.includes('notification') || txt.includes('turn on')) {
                    d.remove();
                }
            }
        }""")

        # Strategy 1: Find link with /posts/ or /permalink/ and hover for tooltip
        ts_link = await page.query_selector("a[href*='/posts/'], a[href*='/permalink/']")
        if ts_link:
            try:
                await ts_link.hover(timeout=2000, force=True)
                await asyncio.sleep(0.6)
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
                    // Skip author link
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

        # Strategy 3: Check abbr tags
        abbr_cand = await page.evaluate("""() => {
            for (let el of document.querySelectorAll("abbr")) {
                const aria = el.getAttribute("aria-label");
                const txt = el.innerText.trim();
                if (aria && !aria.toLowerCase().includes("thông báo")) return aria;
                if (txt && !txt.toLowerCase().includes("thông báo")) return txt;
            }
            return null;
        }""")
        if abbr_cand:
            dt = parse_timestamp(None, abbr_cand)
            if dt:
                return dt.isoformat()

    except Exception as e:
        logger.debug("Error extracting timestamp for %s: %s", url, e)

    return None


async def run_backfill():
    targets = collect_target_posts()
    logger.info("Found %d target posts with Score/Tier from Real authors needing posted_at.", len(targets))

    if not targets:
        logger.info("All target posts already have posted_at! Nothing to do.")
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

            logger.info("[%d/%d] Resolving posted_at for %s (%s, Group %s)...",
                        idx, len(targets), t["author"], url[:60], t["group"])

            iso_ts = await extract_post_timestamp(page, url)
            if iso_ts:
                success_cnt += 1
                logger.info("  -> SUCCESS: %s = %s", t["author"], iso_ts)

                # Update post file
                pf = Path(t["post_file"])
                try:
                    pd = json.loads(pf.read_text(encoding="utf-8"))
                    pd["posted_at"] = iso_ts
                    pd["updated_at"] = now_iso
                    pf.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.warning("Error writing %s: %s", pf, e)

            else:
                logger.warning("  -> NOT FOUND for %s (%s)", t["author"], url)

            await asyncio.sleep(1.2)

        await browser.close()
        logger.info("Finished backfill! Successfully resolved posted_at for %d / %d posts.",
                    success_cnt, len(targets))

    # Also re-run export to refresh the CSV with any updated dates
    try:
        from export_leads_by_rule import run_export
        run_export()
        logger.info("Successfully refreshed cic_leads_filtered.csv!")
    except Exception as e:
        logger.warning("Could not refresh export CSV: %s", e)


if __name__ == "__main__":
    asyncio.run(run_backfill())
