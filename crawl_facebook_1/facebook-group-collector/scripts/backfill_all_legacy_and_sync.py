"""
scripts/backfill_all_legacy_and_sync.py

1. Automatically discovers all groups with real actors needing browser UID resolution.
2. Resolves vanity profile URLs to real Facebook numeric UIDs via authenticated browser session.
3. Performs a global synchronization of actor UIDs to cic_customers.json across ALL groups.
4. Generates a comprehensive verification audit report across all 12 groups.
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

# Ensure scripts dir and project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backfill_user_ids import (
    backfill_group,
    extract_fast_uid_and_username,
    resolve_uid_via_browser,
    SELF_UID,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MASTER_AUDIT] %(message)s"
)
logger = logging.getLogger("master_audit")

# Known crawler artifacts that are not real persons
PARSER_ARTIFACT_NAMES = {"Today", "Unknown", "Facebook Menu", ""}


def sync_all_leads_with_actors():
    """Sync all resolved actor facebook_user_ids into cic_customers.json for every group."""
    data_dir = Path("data/groups")
    total_leads_updated = 0
    
    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        actors_dir = gdir / "actors"
        leads_file = gdir / "cic_customers.json"
        if not actors_dir.exists() or not leads_file.exists():
            continue
            
        actor_uids = {}
        for af in actors_dir.glob("*.json"):
            try:
                ad = json.loads(af.read_text(encoding="utf-8"))
                uid = ad.get("facebook_user_id")
                if uid:
                    actor_uids[ad["id"]] = uid
            except Exception:
                pass
                
        try:
            leads = json.loads(leads_file.read_text(encoding="utf-8"))
            updated = 0
            for lead in leads:
                aid = lead.get("author_id")
                if aid in actor_uids and not lead.get("facebook_user_id"):
                    lead["facebook_user_id"] = actor_uids[aid]
                    updated += 1
            if updated > 0:
                leads_file.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info("Group %s: Synced %d leads in cic_customers.json", gdir.name, updated)
                total_leads_updated += updated
        except Exception as e:
            logger.warning("Group %s: Error updating cic_customers.json: %s", gdir.name, e)
            
    logger.info("Global lead sync completed! Total leads updated: %d", total_leads_updated)
    return total_leads_updated


def print_audit_report():
    data_dir = Path("data/groups")
    print("\n" + "=" * 105)
    print("                              CRAWLER DATA AUDIT REPORT ACROSS ALL GROUPS")
    print("=" * 105)
    print(f"{'Group Slug/ID':<22} | {'Actors':<8} | {'Act.UID':<8} | {'Act.Wait':<9} | {'Artifact':<9} | {'Leads':<7} | {'Lead.UID':<9} | {'Lead.Anon':<9}")
    print("-" * 105)

    tot_actors = 0
    tot_act_uid = 0
    tot_act_wait = 0
    tot_artifacts = 0
    tot_leads = 0
    tot_lead_uid = 0
    tot_lead_anon = 0

    seen = set()
    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        real_p = gdir.resolve()
        is_symlink = gdir.is_symlink()
        
        actors_dir = gdir / "actors"
        leads_file = gdir / "cic_customers.json"
        
        num_actors = 0
        act_uid = 0
        act_wait = 0
        act_artifact = 0
        if actors_dir.exists():
            for af in actors_dir.glob("*.json"):
                num_actors += 1
                try:
                    d = json.loads(af.read_text(encoding="utf-8"))
                    if d.get("is_anonymous"):
                        continue
                    if d.get("facebook_user_id"):
                        act_uid += 1
                    elif d.get("profile_url"):
                        act_wait += 1
                    else:
                        act_artifact += 1
                except Exception:
                    pass

        num_leads = 0
        lead_uid = 0
        lead_anon = 0
        if leads_file.exists():
            try:
                leads = json.loads(leads_file.read_text(encoding="utf-8"))
                num_leads = len(leads)
                lead_uid = sum(1 for l in leads if l.get("facebook_user_id"))
                lead_anon = sum(1 for l in leads if l.get("author_is_anonymous"))
            except Exception:
                pass

        if real_p not in seen:
            tot_actors += num_actors
            tot_act_uid += act_uid
            tot_act_wait += act_wait
            tot_artifacts += act_artifact
            tot_leads += num_leads
            tot_lead_uid += lead_uid
            tot_lead_anon += lead_anon
            seen.add(real_p)

        tag = " (symlink)" if is_symlink else ""
        print(f"{gdir.name + tag:<22} | {num_actors:<8} | {act_uid:<8} | {act_wait:<9} | {act_artifact:<9} | {num_leads:<7} | {lead_uid:<9} | {lead_anon:<9}")

    print("-" * 105)
    print(f"{'TOTAL (Distinct)':<22} | {tot_actors:<8} | {tot_act_uid:<8} | {tot_act_wait:<9} | {tot_artifacts:<9} | {tot_leads:<7} | {tot_lead_uid:<9} | {tot_lead_anon:<9}")
    print("=" * 105 + "\n")


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-only", action="store_true", help="Only sync without browser resolution")
    args = parser.parse_args()

    if args.sync_only:
        sync_all_leads_with_actors()
        print_audit_report()
        return

    # Automatically discover all groups that have any actors needing browser resolution
    data_dir = Path("data/groups")
    target_groups = []
    seen = set()
    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        real_p = gdir.resolve()
        if real_p in seen:
            continue
        actors_dir = gdir / "actors"
        if not actors_dir.exists():
            continue
        
        has_needing = False
        for af in actors_dir.glob("*.json"):
            try:
                ad = json.loads(af.read_text(encoding="utf-8"))
                if not ad.get("is_anonymous") and not ad.get("facebook_user_id") and ad.get("profile_url"):
                    has_needing = True
                    break
            except Exception:
                pass
        if has_needing:
            seen.add(real_p)
            target_groups.append(gdir.name)

    logger.info("Found %d groups needing UID resolution: %s", len(target_groups), target_groups)

    if target_groups:
        config = load_config("config/crawler.yaml")
        async with async_playwright() as p:
            browser = await BrowserFactory.launch_browser(p, config.browser, headless=True)
            context = await BrowserFactory.create_context(browser, config.browser, "data/browser_state/default.json")
            page = await context.new_page()

            for g in target_groups:
                await backfill_group(g, page=page)

            await browser.close()

    # After browser pass, sync leads everywhere
    sync_all_leads_with_actors()
    print_audit_report()


if __name__ == "__main__":
    asyncio.run(main())
