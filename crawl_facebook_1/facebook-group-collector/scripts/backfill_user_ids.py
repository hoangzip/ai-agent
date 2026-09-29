"""
scripts/backfill_user_ids.py — Resolve and backfill facebook_user_id and username for real actors.

Resolves:
1. Instant regex extraction from profile_url:
   - /people/<name>/<numeric_id>
   - /user/<numeric_id>
   - profile.php?id=<numeric_id>
2. High-precision browser resolution for vanity profile URLs (e.g. facebook.com/cuongtran668):
   - Extracts numeric UID from profile DOM / "profile_owner":{"id":"..."} / "userID":"..."
3. Updates actors/*.json, cic_customers.json, and posts/*.json.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sys

from playwright.async_api import async_playwright
from collector.facebook.browser import BrowserFactory
from collector.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [UID_BACKFILL] %(message)s"
)
logger = logging.getLogger("uid_backfill")

# Ignore our own crawler account UID if found in global page scope
SELF_UID = "61594991450953"

UID_PATTERNS = [
    r"\"profile_owner\":\{\"id\":\"(\d+)\"",
    r"\"userID\":\"(\d+)\"",
    r"\"entity_id\":\"(\d+)\"",
    r"\"user\":\{\"id\":\"(\d+)\"",
    r"fb://profile/(\d+)",
    r"/profile\.php\?id=(\d+)",
    r"/user/(\d+)",
]


def extract_fast_uid_and_username(url: str) -> tuple[str | None, str | None]:
    if not url:
        return None, None

    # 1. Check numeric UID in URL
    m_user = re.search(r"/user/(\d+)", url)
    m_php = re.search(r"profile\.php\?id=(\d+)", url)
    m_people = re.search(r"/people/[^/]+/(\d+)", url)

    uid = None
    if m_user:
        uid = m_user.group(1)
    elif m_php:
        uid = m_php.group(1)
    elif m_people:
        uid = m_people.group(1)

    # 2. Extract username if present (vanity)
    username = None
    m_uname = re.search(r"facebook\.com/([^/?#]+)", url)
    if m_uname:
        cand = m_uname.group(1)
        if cand not in ("people", "profile.php", "groups", "user") and not cand.startswith("pfbid"):
            username = cand

    return uid, username


async def resolve_uid_via_browser(page, url: str) -> str | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(1.8)

        # Check if URL redirected to numeric profile
        cur_url = page.url
        m_redirect = re.search(r"(?:/user/|profile\.php\?id=|/people/[^/]+/)(\d+)", cur_url)
        if m_redirect and m_redirect.group(1) != SELF_UID:
            return m_redirect.group(1)

        content = await page.content()

        for pat in UID_PATTERNS:
            matches = set(re.findall(pat, content))
            valid = [m for m in matches if m != SELF_UID and len(m) >= 8]
            if valid:
                return valid[0]

    except Exception as e:
        logger.warning("Failed resolving UID for %s: %s", url, e)

    return None


async def backfill_group(group_slug: str, page=None):
    group_dir = Path(f"data/groups/{group_slug}")
    actors_dir = group_dir / "actors"
    leads_file = group_dir / "cic_customers.json"
    posts_dir = group_dir / "posts"

    if not actors_dir.exists():
        logger.info("No actors directory for group %s. Skipping.", group_slug)
        return

    actor_files = list(actors_dir.glob("*.json"))
    logger.info("Processing %d actors in group %s...", len(actor_files), group_slug)

    resolved_map = {}  # actor_id -> (uid, username)
    fast_count = 0
    browser_count = 0

    # Step 1: Fast regex pass
    actors_needing_browser = []
    for af in actor_files:
        try:
            d = json.loads(af.read_text(encoding="utf-8"))
        except Exception:
            continue

        if d.get("is_anonymous"):
            continue

        cur_uid = d.get("facebook_user_id")
        cur_uname = d.get("username")
        url = d.get("profile_url") or ""

        fast_uid, fast_uname = extract_fast_uid_and_username(url)

        updated = False
        if not cur_uid and fast_uid:
            d["facebook_user_id"] = fast_uid
            cur_uid = fast_uid
            updated = True
            fast_count += 1

        if not cur_uname and fast_uname:
            d["username"] = fast_uname
            updated = True

        if updated:
            d["updated_at"] = datetime.now(timezone.utc).isoformat()
            af.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

        if cur_uid:
            resolved_map[d.get("id")] = (cur_uid, d.get("username"))
        elif url and page:
            actors_needing_browser.append((af, d, url))

    logger.info("Group %s: Fast extracted %d UIDs without network.", group_slug, fast_count)

    # Step 2: Browser pass for remaining vanity/pfbid URLs
    if page and actors_needing_browser:
        logger.info("Group %s: Resolving %d vanity actors via browser session...", group_slug, len(actors_needing_browser))
        for idx, (af, d, url) in enumerate(actors_needing_browser, 1):
            name = d.get("display_name")
            logger.info("  [%d/%d] Resolving UID for: %s (%s)", idx, len(actors_needing_browser), name, url)

            uid = await resolve_uid_via_browser(page, url)
            if uid:
                d["facebook_user_id"] = uid
                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                af.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                resolved_map[d.get("id")] = (uid, d.get("username"))
                browser_count += 1
                logger.info("    -> SUCCESS: %s = %s", name, uid)
            else:
                logger.warning("    -> NOT FOUND for %s", name)

            await asyncio.sleep(1.5)

    logger.info("Group %s: Total resolved %d (Fast: %d, Browser: %d)",
                group_slug, fast_count + browser_count, fast_count, browser_count)

    # Step 3: Update cic_customers.json
    if leads_file.exists() and resolved_map:
        try:
            leads = json.loads(leads_file.read_text(encoding="utf-8"))
            updated_leads = 0
            for lead in leads:
                aid = lead.get("author_id")
                if aid in resolved_map:
                    uid, uname = resolved_map[aid]
                    if not lead.get("facebook_user_id"):
                        lead["facebook_user_id"] = uid
                        updated_leads += 1
            if updated_leads > 0:
                leads_file.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info("Updated %d leads in cic_customers.json with facebook_user_id", updated_leads)
        except Exception as e:
            logger.warning("Error updating cic_customers.json: %s", e)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", type=str, default="3508387292634958")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--fast-only", action="store_true", help="Only run regex without opening browser")
    args = parser.parse_args()

    groups = ["1793269141356323", "3508387292634958", "1741651903956682"] if args.all else [args.group]

    if args.fast_only:
        for g in groups:
            await backfill_group(g, page=None)
        return

    config = load_config("config/crawler.yaml")
    async with async_playwright() as p:
        browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
        context = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
        page = await context.new_page()

        for g in groups:
            await backfill_group(g, page=page)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
