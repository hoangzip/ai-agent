"""
scripts/fix_photo_urls.py — Comprehensive fix for all post URLs across all crawled groups:
- Converts anonymous post URLs to canonical 'photo/?fbid={photo_fbid}&set=g.{group_slug}' to avoid Facebook modal crash
- Fixes 'recover/initiate' or root homepage URLs
- Fixes broken /posts/ links
"""
import json
import sys
from pathlib import Path

GROUPS_DIR = Path("data/groups")

def process_group(group_dir: Path):
    group_slug = group_dir.name
    print(f"\nProcessing group: {group_slug}...")
    
    gallery_order_path = group_dir / "media_gallery_order.json"
    if not gallery_order_path.exists():
        print(f"  media_gallery_order.json not found in {group_dir}, skipping.")
        return

    gallery_order = json.loads(gallery_order_path.read_text(encoding="utf-8"))
    gallery_fbids = {str(item["fbid"]) for item in gallery_order}
    print(f"  Loaded {len(gallery_fbids)} gallery photo FBIDs.")

    # Build mapping from post_id / post_uuid / fbid to photo_fbid
    state_file = group_dir / "media_gallery_state.json"
    post_id_to_fbid = {}
    post_uuid_to_fbid = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for fbid, s_data in state.items():
                if isinstance(s_data, dict):
                    pid = s_data.get("post_id")
                    puuid = s_data.get("post_uuid")
                    if pid:
                        post_id_to_fbid[str(pid)] = str(fbid)
                    if puuid:
                        post_uuid_to_fbid[str(puuid)] = str(fbid)
        except Exception:
            pass

    posts_dir = group_dir / "posts"
    fixed_posts = 0

    if posts_dir.exists():
        for p_path in sorted(posts_dir.glob("*.json")):
            try:
                data = json.loads(p_path.read_text(encoding="utf-8"))
                p_url = data.get("post_url", "")
                fb_id = str(data.get("facebook_post_id", ""))
                post_uuid = data.get("id", "")
                is_anon = data.get("author_is_anonymous", False)
                
                # Determine associated photo fbid
                fbid = None
                if fb_id in gallery_fbids:
                    fbid = fb_id
                elif fb_id in post_id_to_fbid:
                    fbid = post_id_to_fbid[fb_id]
                elif post_uuid in post_uuid_to_fbid:
                    fbid = post_uuid_to_fbid[post_uuid]
                else:
                    for m_id in data.get("media_ids", []):
                        m_path = Path("data/media/meta") / f"{m_id}.json"
                        if m_path.exists():
                            try:
                                m_meta = json.loads(m_path.read_text(encoding="utf-8"))
                                cand = str(m_meta.get("photo_fbid", ""))
                                if cand in gallery_fbids:
                                    fbid = cand
                                    break
                            except Exception:
                                pass

                # If anonymous post or standalone photo or bad URL, use canonical photo URL
                needs_canonical = (
                    is_anon or
                    not p_url or
                    p_url.rstrip("/") in ("https://www.facebook.com", "https://web.facebook.com") or
                    "recover/initiate" in p_url or
                    p_url.endswith("/posts/") or
                    p_url.endswith("/posts") or
                    (fb_id in gallery_fbids and ("/posts/" in p_url or "/permalink/" in p_url))
                )

                if needs_canonical and fbid:
                    canonical_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{group_slug}"
                    if data.get("post_url") != canonical_url:
                        data["post_url"] = canonical_url
                        p_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        fixed_posts += 1
            except Exception as e:
                print(f"  Error reading {p_path}: {e}")

        print(f"  Updated {fixed_posts} post JSON files to canonical photo URLs.")

    # Update cic_customers.json
    cic_file = group_dir / "cic_customers.json"
    fixed_cic = 0
    if cic_file.exists():
        leads = json.loads(cic_file.read_text(encoding="utf-8"))
        for lead in leads:
            p_url = lead.get("post_url", "")
            fb_id = str(lead.get("facebook_post_id", ""))
            post_uuid = lead.get("post_id", "")
            is_anon = lead.get("author_is_anonymous", False)
            
            fbid = None
            if fb_id in gallery_fbids:
                fbid = fb_id
            elif fb_id in post_id_to_fbid:
                fbid = post_id_to_fbid[fb_id]
            elif post_uuid in post_uuid_to_fbid:
                fbid = post_uuid_to_fbid[post_uuid]
            else:
                m_id = lead.get("media_id")
                if m_id:
                    m_path = Path("data/media/meta") / f"{m_id}.json"
                    if m_path.exists():
                        try:
                            m_meta = json.loads(m_path.read_text(encoding="utf-8"))
                            cand = str(m_meta.get("photo_fbid", ""))
                            if cand in gallery_fbids:
                                fbid = cand
                        except Exception:
                            pass

            needs_canonical = (
                is_anon or
                not p_url or
                p_url.rstrip("/") in ("https://www.facebook.com", "https://web.facebook.com") or
                "recover/initiate" in p_url or
                p_url.endswith("/posts/") or
                p_url.endswith("/posts") or
                (fb_id in gallery_fbids and ("/posts/" in p_url or "/permalink/" in p_url))
            )

            if needs_canonical and fbid:
                canonical_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{group_slug}"
                if lead.get("post_url") != canonical_url:
                    lead["post_url"] = canonical_url
                    fixed_cic += 1
        
        cic_file.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Updated {fixed_cic} leads in cic_customers.json.")

def main():
    if not GROUPS_DIR.exists():
        print("data/groups directory does not exist.")
        return

    target_groups = [p for p in GROUPS_DIR.iterdir() if p.is_dir()]
    for g_dir in sorted(target_groups):
        process_group(g_dir)
    print("\nAll groups processed successfully!")

if __name__ == "__main__":
    main()
