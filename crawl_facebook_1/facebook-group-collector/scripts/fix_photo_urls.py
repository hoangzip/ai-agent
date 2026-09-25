"""
scripts/fix_photo_urls.py — Comprehensive fix for invalid/incomplete post URLs:
- 'https://www.facebook.com/' or root homepage URLs
- 'recover/initiate' banner links
- Truncated '/posts/' without ID
- Using photo FBID in '/posts/{photo_fbid}' format instead of canonical 'photo/?fbid={photo_fbid}&set=g.{group_slug}'
"""
import json
from pathlib import Path

GROUP_SLUG = "978769317924542"
ROOT = Path("data/groups") / GROUP_SLUG

def is_invalid_url(url: str, fb_id: str, gallery_fbids: set) -> bool:
    if not url:
        return True
    u = url.strip()
    u_clean = u.rstrip('/')
    if u_clean in ("https://www.facebook.com", "https://web.facebook.com", "http://www.facebook.com", "http://web.facebook.com"):
        return True
    if "recover/initiate" in u:
        return True
    if u.endswith("/posts/") or u.endswith("/posts") or u.endswith("/permalink/") or u.endswith("/permalink"):
        return True
    if fb_id in gallery_fbids and ("/posts/" in u or "/permalink/" in u):
        return True
    return False

def main():
    gallery_order_path = ROOT / "media_gallery_order.json"
    if not gallery_order_path.exists():
        print("media_gallery_order.json not found!")
        return

    gallery_order = json.loads(gallery_order_path.read_text(encoding="utf-8"))
    gallery_fbids = {str(item["fbid"]) for item in gallery_order}
    print(f"Loaded {len(gallery_fbids)} gallery photo FBIDs.")

    posts_dir = ROOT / "posts"
    fixed_posts = 0

    # Map photo_fbid to correct canonical URL
    for p_path in sorted(posts_dir.glob("*.json")):
        try:
            data = json.loads(p_path.read_text(encoding="utf-8"))
            p_url = data.get("post_url", "")
            fb_id = str(data.get("facebook_post_id", ""))
            
            # Find photo fbid if not in gallery_fbids directly
            fbid = None
            if fb_id in gallery_fbids:
                fbid = fb_id
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

            if is_invalid_url(p_url, fb_id, gallery_fbids):
                target_fbid = fbid or fb_id
                if target_fbid:
                    canonical_url = f"https://www.facebook.com/photo/?fbid={target_fbid}&set=g.{GROUP_SLUG}"
                    data["post_url"] = canonical_url
                    p_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    fixed_posts += 1
        except Exception as e:
            print(f"Error reading {p_path}: {e}")

    print(f"Updated {fixed_posts} post JSON files to canonical photo URLs.")

    # Update cic_customers.json
    cic_file = ROOT / "cic_customers.json"
    fixed_cic = 0
    if cic_file.exists():
        leads = json.loads(cic_file.read_text(encoding="utf-8"))
        for lead in leads:
            p_url = lead.get("post_url", "")
            fb_id = str(lead.get("facebook_post_id", ""))
            if is_invalid_url(p_url, fb_id, gallery_fbids):
                target_fbid = fb_id
                if not target_fbid or target_fbid not in gallery_fbids:
                    # check if post JSON has fbid
                    post_uuid = lead.get("post_id")
                    if post_uuid:
                        post_json_path = posts_dir / f"{post_uuid}.json"
                        if post_json_path.exists():
                            try:
                                post_json = json.loads(post_json_path.read_text(encoding="utf-8"))
                                cand = str(post_json.get("facebook_post_id", ""))
                                if cand in gallery_fbids:
                                    target_fbid = cand
                            except Exception:
                                pass
                if target_fbid:
                    lead["post_url"] = f"https://www.facebook.com/photo/?fbid={target_fbid}&set=g.{GROUP_SLUG}"
                    fixed_cic += 1
        
        cic_file.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Updated {fixed_cic} leads in cic_customers.json.")

if __name__ == "__main__":
    main()
