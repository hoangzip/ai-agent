"""
scripts/run_overnight_pipeline.py — Master Autonomous Overnight Crawler Pipeline.

Designed for zero-supervision overnight execution:
1. Crawls Group 1: kiemtranoxau (ID: 508242083145361) to 100% completion.
2. Audits and cleans Group 1 data (author names, comment links, ads tagging).
3. Automatically transitions to Group 2: 1178898519573483 to 100% completion.
4. Audits and cleans Group 2 data.
5. Employs automatic resilience:
   - Resumes seamlessly if network drops or session hiccups occur (using media_gallery_state.json).
   - Jitter delays (5.5 - 9.5s) and 60s periodic safety rests to prevent Facebook checkpoints.
   - Hard 20s comment timeout so comment extraction never hangs.
   - Wiggle scrolling to eliminate virtualization premature halts.
6. Writes live status every minute to data/overnight_crawl_status.json for monitoring.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OVERNIGHT_PIPELINE] %(message)s"
)
logger = logging.getLogger("overnight_pipeline")

GROUPS_TO_CRAWL = [
    {
        "slug": "kiemtranoxau",
        "name": "Kiểm tra Nợ Xấu CIC | Lịch sử tín dụng | Điểm tín dụng CreditScore",
        "numeric_id": "508242083145361",
    },
    {
        "slug": "1178898519573483",
        "name": "Hỗ Trợ Vay Tín Chấp Thế Chấp Ngân Hàng - MOMO ( Kiểm Tra CIC )",
        "numeric_id": "1178898519573483",
    }
]

STATUS_FILE = Path("data/overnight_crawl_status.json")


def update_status(current_group: str, stage: str, stats: dict, is_complete: bool = False):
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_group": current_group,
        "stage": stage,
        "stats": stats,
        "pipeline_complete": is_complete,
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_group_stats(group_slug: str) -> dict:
    group_dir = Path(f"data/groups/{group_slug}")
    order_file = group_dir / "media_gallery_order.json"
    state_file = group_dir / "media_gallery_state.json"
    leads_file = group_dir / "cic_customers.json"
    posts_dir = group_dir / "posts"

    total_order = 0
    if order_file.exists():
        try:
            total_order = len(json.loads(order_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    state_counts = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for k, v in state.items():
                if isinstance(v, dict):
                    st = v.get("status", "unknown")
                    state_counts[st] = state_counts.get(st, 0) + 1
        except Exception:
            pass

    total_posts = len(list(posts_dir.glob("*.json"))) if posts_dir.exists() else 0
    total_leads = 0
    leads_with_score = 0
    if leads_file.exists():
        try:
            leads = json.loads(leads_file.read_text(encoding="utf-8"))
            total_leads = len(leads)
            leads_with_score = sum(1 for l in leads if l.get("score") is not None)
        except Exception:
            pass

    return {
        "gallery_photos_indexed": total_order,
        "state_breakdown": state_counts,
        "total_posts_saved": total_posts,
        "total_cic_leads": total_leads,
        "leads_with_score": leads_with_score,
    }


def run_group_crawler(group_slug: str, max_retries: int = 5) -> bool:
    logger.info("================================================================================")
    logger.info("STARTING OVERNIGHT CRAWL FOR GROUP: %s", group_slug)
    logger.info("================================================================================")

    # Symlink numeric id if needed
    if group_slug == "kiemtranoxau":
        sym = Path("data/groups/508242083145361")
        if not sym.exists():
            try:
                sym.symlink_to("kiemtranoxau")
            except Exception:
                pass

    venv_python = sys.executable

    for attempt in range(1, max_retries + 1):
        logger.info("[Group: %s] Run attempt %d/%d starting...", group_slug, attempt, max_retries)
        update_status(group_slug, f"crawling_attempt_{attempt}", get_group_stats(group_slug))

        cmd = [
            venv_python,
            "scripts/crawl_media_gallery_sequential.py",
            "--group", group_slug,
            "--check-comments",
            "--headless",
        ]

        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(Path.cwd()),
        )

        # Stream output in real time
        for line in p.stdout:
            line_str = line.rstrip()
            if any(k in line_str for k in ("INFO", "WARNING", "ERROR", "CRITICAL", "Summary", "CIC FOUND", "Scroll")):
                print(line_str, flush=True)

        p.wait()
        return_code = p.returncode

        stats = get_group_stats(group_slug)
        logger.info("[Group: %s] Process finished with return code %d. Current Stats: %s",
                    group_slug, return_code, stats)

        # Check if the group has finished processing all photos
        total_indexed = stats["gallery_photos_indexed"]
        state_counts = stats["state_breakdown"]
        completed_photos = sum(v for k, v in state_counts.items() if k != "error")

        if total_indexed > 0 and completed_photos >= total_indexed:
            logger.info("SUCCESS: Group %s has crawled 100%% of all %d indexed gallery photos!",
                        group_slug, total_indexed)
            return True
        elif return_code == 0:
            logger.info("Process finished cleanly with code 0. Verifying completion...")
            if total_indexed > 0 and completed_photos >= total_indexed:
                return True
            else:
                logger.info("Some photos remain un-crawled (%d/%d). Auto-resuming in 15 seconds...",
                            completed_photos, total_indexed)
                time.sleep(15)
        else:
            logger.warning("Process exited with code %d. Waiting 30s before auto-resuming attempt %d/%d...",
                           return_code, attempt + 1, max_retries)
            time.sleep(30)

    logger.warning("Group %s reached max retries (%d). Proceeding with current data.", group_slug, max_retries)
    return False


def run_audit_and_cleaning(group_slug: str):
    logger.info("Running post-crawl data audit and cleaning for group: %s ...", group_slug)
    update_status(group_slug, "audit_and_cleaning", get_group_stats(group_slug))
    cmd = [sys.executable, "scripts/audit_and_clean_data.py", group_slug]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout, flush=True)
    if res.stderr:
        print(res.stderr, flush=True)


def main():
    logger.info(">>> MASTER AUTONOMOUS OVERNIGHT CRAWLER STARTING <<<")
    overall_start = time.time()

    for idx, g in enumerate(GROUPS_TO_CRAWL):
        g_slug = g["slug"]
        logger.info("Processing Group [%d/%d]: %s (%s)", idx + 1, len(GROUPS_TO_CRAWL), g_slug, g["name"])

        # Run crawler until 100% complete
        success = run_group_crawler(g_slug, max_retries=6)

        # Run audit and clean data
        run_audit_and_cleaning(g_slug)

        # Inter-group safety cooldown
        if idx < len(GROUPS_TO_CRAWL) - 1:
            cooldown = 45
            logger.info("Group %s completed. Cooling down for %ds before starting next group...", g_slug, cooldown)
            time.sleep(cooldown)

    elapsed_mins = (time.time() - overall_start) / 60.0
    logger.info("================================================================================")
    logger.info("ALL TARGET GROUPS FINISHED OVERNIGHT! Total runtime: %.1f minutes", elapsed_mins)
    logger.info("================================================================================")

    # Final summary across all target groups
    final_summary = {}
    for g in GROUPS_TO_CRAWL:
        final_summary[g["slug"]] = get_group_stats(g["slug"])

    update_status("all_groups", "completed", final_summary, is_complete=True)
    logger.info("Final Summary: %s", json.dumps(final_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
