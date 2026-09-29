"""
scripts/backfill_upgraded_cic.py — Backfill newly recognized debt/CIC posts and leads.
"""
import json
import os
from glob import glob
from pathlib import Path
from collector.analysis.cic_extractor import CICExtractor

def backfill_group(group_slug: str):
    base = Path(f"data/groups/{group_slug}")
    posts_dir = base / "posts"
    leads_path = base / "cic_customers.json"
    state_file = base / "media_gallery_state.json"

    leads = json.loads(leads_path.read_text(encoding="utf-8")) if leads_path.exists() else []
    existing_lead_post_ids = {l.get("post_id") for l in leads if l.get("post_id")}
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

    upgraded_count = 0
    new_leads_added = 0

    for pf in sorted(posts_dir.glob("*.json")):
        try:
            d = json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not d.get("cic_data"):
            media_ids = d.get("media_ids") or []
            if not media_ids:
                continue
            mid = media_ids[0]
            meta_path = Path(f"data/media/meta/{mid}.json")
            if not meta_path.exists():
                continue

            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            ocr_text = meta.get("ocr_text")
            if not ocr_text:
                continue

            res = CICExtractor.parse_text(ocr_text)
            if res.is_cic:
                cic_dict = res.to_dict()
                d["cic_data"] = cic_dict
                pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

                meta["cic_data"] = cic_dict
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

                upgraded_count += 1

                # Update gallery state
                fbid = str(d.get("facebook_post_id") or "")
                if fbid in state:
                    state[fbid]["status"] = "crawled_cic_found"

                # Add to cic_customers if not already present
                post_uuid = d.get("id")
                if post_uuid and post_uuid not in existing_lead_post_ids:
                    lead_entry = {
                        "lead_source": "post",
                        "post_id": post_uuid,
                        "facebook_post_id": fbid,
                        "post_url": d.get("post_url"),
                        "media_id": mid,
                        "image_file": f"{post_uuid}_0.jpg",
                        "image_path": f"groups/{group_slug}/images/posts/{post_uuid}_0.jpg",
                        "author_id": d.get("author_id"),
                        "author_display_name": d.get("author_display_name"),
                        "author_profile_url": d.get("author_profile_url"),
                        "author_is_anonymous": d.get("author_is_anonymous", False),
                        "customer_name": cic_dict.get("customer_name"),
                        "id_card_number": cic_dict.get("id_card_number"),
                        "phone_number": cic_dict.get("phone_number"),
                        "date_of_birth": cic_dict.get("date_of_birth"),
                        "cic_code": cic_dict.get("cic_code"),
                        "address": cic_dict.get("address"),
                        "score": cic_dict.get("score"),
                        "tier": cic_dict.get("tier"),
                        "scoring_date": cic_dict.get("scoring_date"),
                        "total_debt": cic_dict.get("total_debt"),
                        "has_bad_debt": cic_dict.get("has_bad_debt"),
                        "provider": cic_dict.get("provider", "CIC"),
                        "is_broker_advertisement": False
                    }
                    leads.append(lead_entry)
                    existing_lead_post_ids.add(post_uuid)
                    new_leads_added += 1

    leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Group {group_slug}:")
    print(f"  - Upgraded {upgraded_count} posts with CIC/debt data")
    print(f"  - Added {new_leads_added} new leads to cic_customers.json (Total leads: {len(leads)})")

if __name__ == "__main__":
    for g in ["1793269141356323", "3508387292634958"]:
        backfill_group(g)
