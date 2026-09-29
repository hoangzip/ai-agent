"""
scripts/export_leads_by_rule.py

Export leads matching:
1. Has CIC score OR has Tier (score is not None or tier is not None)
2. Marked as Post or Comment (lead_source)
3. User real OR has phone number
4. Deduplicate customers (prioritize most recent scoring_date if duplicated, merge missing contact info)

Exports:
- data/exports/cic_leads_filtered.csv (UTF-8 with BOM for Excel)
- data/exports/cic_leads_filtered.json
"""
from __future__ import annotations

import csv
from datetime import datetime
import json
import logging
from pathlib import Path
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_leads")

OUTPUT_DIR = Path("data/exports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE = OUTPUT_DIR / "cic_leads_filtered.csv"
JSON_FILE = OUTPUT_DIR / "cic_leads_filtered.json"


def clean_phone(phone: str | None) -> str:
    if not phone:
        return ""
    p = str(phone).strip()
    if p.lower() in ("none", "null", "undefined", "n/a"):
        return ""
    digits = re.sub(r"[^\d+]", "", p)
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits


def parse_date(d_str: str | None) -> datetime:
    if not d_str or not str(d_str).strip():
        return datetime.min
    s = str(d_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return datetime.min


def run_export():
    data_dir = Path("data/groups")
    raw_records = []
    seen_groups = set()

    for gdir in sorted(data_dir.iterdir()):
        if not gdir.is_dir():
            continue
        real_p = gdir.resolve()
        if real_p in seen_groups:
            continue
        seen_groups.add(real_p)

        leads_file = gdir / "cic_customers.json"
        if not leads_file.exists():
            continue

        actors_dir = gdir / "actors"
        actor_map = {}
        if actors_dir.exists():
            for af in actors_dir.glob("*.json"):
                try:
                    ad = json.loads(af.read_text(encoding="utf-8"))
                    actor_map[ad["id"]] = ad
                except Exception:
                    pass

        posts_dir = gdir / "posts"
        post_cache = {}
        if posts_dir.exists():
            for pf in posts_dir.glob("*.json"):
                try:
                    pd = json.loads(pf.read_text(encoding="utf-8"))
                    pid = pd.get("id")
                    fb_pid = pd.get("facebook_post_id")
                    ts = pd.get("posted_at") or ""
                    if pid:
                        post_cache[pid] = ts
                    if fb_pid:
                        post_cache[str(fb_pid)] = ts
                except Exception:
                    pass

        try:
            leads = json.loads(leads_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Error reading %s: %s", leads_file, e)
            continue

        for l in leads:
            score = l.get("score")
            tier = l.get("tier")
            has_score = bool(score is not None and str(score).strip() != "")
            has_tier = bool(tier is not None and str(tier).strip() != "")

            # Rule 1: Must have CIC score OR Tier
            if not (has_score or has_tier):
                continue

            raw_phone = l.get("phone_number")
            phone = clean_phone(raw_phone)
            has_phone = bool(phone)

            is_anon = bool(l.get("author_is_anonymous"))

            # Rule 3: Must be user real OR has phone
            if is_anon and not has_phone:
                continue

            aid = l.get("author_id")
            actor = actor_map.get(aid, {})

            uid = l.get("facebook_user_id") or actor.get("facebook_user_id") or ""
            purl = l.get("author_profile_url") or actor.get("profile_url") or ""
            name = l.get("author_display_name") or actor.get("display_name") or ""

            # Filter out anonymous pseudonyms without UID, URL, or phone
            if not is_anon and not uid and not purl and not has_phone:
                continue

            if is_anon:
                kh_type = "Ẩn danh (Có SĐT)"
            elif uid:
                kh_type = "User thật (Có UID)"
            elif purl:
                kh_type = "User thật (Có Link Profile)"
            else:
                kh_type = "User thật"

            # Rule 2: Post or Comment
            raw_source = (l.get("lead_source") or "post").lower()
            source_label = "Comment" if "comment" in raw_source else "Post"

            bad_debt_raw = l.get("has_bad_debt")
            if bad_debt_raw is True:
                bad_debt_str = "Có nợ xấu"
            elif bad_debt_raw is False:
                bad_debt_str = "Không nợ xấu"
            else:
                bad_debt_str = "Chưa rõ"

            post_id = l.get("post_id")
            fb_pid = str(l.get("facebook_post_id") or "")
            raw_posted = post_cache.get(post_id) or post_cache.get(fb_pid) or ""
            posted_at_clean = raw_posted.replace("T", " ")[:19] if raw_posted else ""

            raw_records.append({
                "group_slug": gdir.name,
                "lead_source": source_label,
                "customer_type": kh_type,
                "facebook_user_id": uid,
                "phone_number": phone,
                "author_display_name": name,
                "score": score if has_score else "",
                "tier": tier if has_tier else "",
                "has_bad_debt": bad_debt_str,
                "total_debt": l.get("total_debt") or "",
                "scoring_date": l.get("scoring_date") or "",
                "posted_at": posted_at_clean,
                "provider": l.get("provider") or "",
                "customer_name": l.get("customer_name") or "",
                "id_card_number": l.get("id_card_number") or "",
                "profile_url": purl,
                "post_url": l.get("post_url") or "",
                "image_path": l.get("image_path") or "",
            })

    logger.info("Total raw matching leads (Score OR Tier) before dedup: %d", len(raw_records))

    # --- Deduplication by Customer (UID / Phone / Profile URL) ---
    parent = {}
    def find(x):
        if parent.setdefault(x, x) != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for idx, r in enumerate(raw_records):
        item_id = f"item_{idx}"
        if r["facebook_user_id"]:
            union(item_id, f"uid_{r['facebook_user_id']}")
        if r["phone_number"]:
            union(item_id, f"phone_{r['phone_number']}")
        if not r["facebook_user_id"] and not r["phone_number"] and r["profile_url"]:
            union(item_id, f"url_{r['profile_url']}")

    clusters = {}
    for idx, r in enumerate(raw_records):
        item_id = f"item_{idx}"
        root = find(item_id)
        clusters.setdefault(root, []).append(r)

    deduped_records = []
    for root, items in clusters.items():
        if len(items) == 1:
            deduped_records.append(items[0])
            continue

        # Sort criteria for selecting best record:
        # 1. Most recent scoring_date
        # 2. Has phone number
        # 3. Has Facebook UID
        # 4. Has score
        # 5. Total filled fields completeness
        def sort_key(x):
            dt = parse_date(x.get("scoring_date"))
            has_p = 1 if x.get("phone_number") else 0
            has_u = 1 if x.get("facebook_user_id") else 0
            has_s = 1 if x.get("score") != "" else 0
            completeness = sum(1 for v in x.values() if v)
            return (dt, has_p, has_u, has_s, completeness)

        items_sorted = sorted(items, key=sort_key, reverse=True)
        best = dict(items_sorted[0])

        # Merge non-empty fields from duplicate records so no data is lost
        for other in items_sorted[1:]:
            for k in ["phone_number", "facebook_user_id", "score", "tier", "customer_name", "id_card_number", "total_debt", "provider", "profile_url", "posted_at"]:
                if not best.get(k) and other.get(k):
                    best[k] = other[k]

        if best.get("phone_number") and best["customer_type"] == "Ẩn danh (Chưa có SĐT)":
            best["customer_type"] = "Ẩn danh (Có SĐT)"
        elif best.get("facebook_user_id") and "UID" not in best["customer_type"]:
            best["customer_type"] = "User thật (Có UID)"

        deduped_records.append(best)

    # Sort final export: Has Phone first, then Has UID, then score descending, then date descending
    def final_sort_key(r):
        has_phone_flag = 0 if r["phone_number"] else 1
        has_uid_flag = 0 if r["facebook_user_id"] else 1
        score_val = -(r["score"]) if isinstance(r["score"], (int, float)) else -0.1 if r["score"] else 0
        date_val = parse_date(r["scoring_date"])
        date_int = -(date_val.year * 10000 + date_val.month * 100 + date_val.day)
        return (has_phone_flag, has_uid_flag, score_val, date_int)

    deduped_records.sort(key=final_sort_key)

    logger.info("Total deduplicated leads: %d (Dropped %d duplicates)",
                len(deduped_records), len(raw_records) - len(deduped_records))

    # Save to JSON
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(deduped_records, f, ensure_ascii=False, indent=2)
    logger.info("Saved JSON to %s", JSON_FILE)

    # Save to CSV (utf-8-sig for perfect Excel compatibility)
    fieldnames = [
        "STT",
        "Nguồn (Post/Comment)",
        "Loại Khách Hàng",
        "Facebook UID",
        "Số Điện Thoại",
        "Tên Facebook",
        "Điểm CIC",
        "Hạng CIC",
        "Tình Trạng Nợ Xấu",
        "Tổng Dư Nợ",
        "Ngày Chấm Điểm",
        "Ngày Đăng Bài",
        "Nguồn/Ngân Hàng",
        "Họ Tên Trên CIC",
        "Số CCCD/CMND",
        "Link Profile Facebook",
        "Link Bài Viết/Ảnh",
        "Group ID",
        "File Ảnh Báo Cáo",
    ]

    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

        for idx, r in enumerate(deduped_records, 1):
            uid_str = f"'{r['facebook_user_id']}" if r["facebook_user_id"] else ""
            phone_str = f"'{r['phone_number']}" if r["phone_number"] else ""

            writer.writerow([
                idx,
                r["lead_source"],
                r["customer_type"],
                uid_str,
                phone_str,
                r["author_display_name"],
                r["score"],
                r["tier"],
                r["has_bad_debt"],
                r["total_debt"],
                r["scoring_date"],
                r.get("posted_at") or "",
                r["provider"],
                r["customer_name"],
                r["id_card_number"],
                r["profile_url"],
                r["post_url"],
                r["group_slug"],
                r["image_path"],
            ])

    logger.info("Saved CSV to %s", CSV_FILE)
    return deduped_records


if __name__ == "__main__":
    run_export()
