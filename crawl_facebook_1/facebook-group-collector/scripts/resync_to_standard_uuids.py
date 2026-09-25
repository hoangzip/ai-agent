#!/usr/bin/env python3
"""
scripts/resync_to_standard_uuids.py — Standardize all posts, comment images,
and cic_customers.json to standard UUIDs with full user mapping.
"""
import json
from pathlib import Path
import re
import uuid

def main():
    group_slug = "978769317924542"
    base_dir = Path(f"data/groups/{group_slug}")
    posts_dir = base_dir / "posts"
    comments_img_dir = base_dir / "images" / "comments"
    posts_img_dir = base_dir / "images" / "posts"
    leads_path = base_dir / "cic_customers.json"
    actors_index_path = Path("data/index") / f"actors_{group_slug}.json"
    media_meta_dir = Path("data/media/meta")

    # Load actor index
    actors_index = json.loads(actors_index_path.read_text(encoding="utf-8")) if actors_index_path.exists() else {}

    print("Step 1: Ensuring all posts have standard UUID filenames and match facebook_post_id...")
    fb_post_to_uuid = {}
    for p in list(posts_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            fb_id = str(d.get("facebook_post_id"))
            p_id = d.get("id")
            # If p_id is not a standard UUID (contains no hyphens)
            if not p_id or len(p_id) != 36:
                p_id = str(uuid.uuid4())
                d["id"] = p_id
            
            fb_post_to_uuid[fb_id] = p_id
            target_path = posts_dir / f"{p_id}.json"
            target_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            if p != target_path:
                p.unlink()
            print(f"  Post {fb_id} -> {p_id}.json")
        except Exception as e:
            print(f"  Error on post {p.name}: {e}")

    print("\nStep 2: Standardizing comment images to full UUID and mapping with user...")
    if leads_path.exists():
        leads = json.loads(leads_path.read_text(encoding="utf-8"))
        for l in leads:
            source = l.get("lead_source") or "post"
            fb_post_id = str(l.get("facebook_post_id"))
            p_uuid = fb_post_to_uuid.get(fb_post_id) or l.get("post_id") or str(uuid.uuid4())
            l["post_id"] = p_uuid
            l["facebook_post_id"] = fb_post_id

            # User mapping
            author_url = l.get("author_profile_url")
            author_name = l.get("author_display_name")
            is_anon = l.get("author_is_anonymous", False)

            # Look up actor UUID
            author_id = None
            if author_url:
                author_id = actors_index.get(f"profile_url:{author_url}")
            if not author_id and is_anon:
                # Find matching anon key
                for k, v in actors_index.items():
                    if k.startswith(f"anon:{fb_post_id}"):
                        author_id = v
                        break
            if not author_id:
                author_id = str(uuid.uuid4())

            l["author_id"] = author_id

            if source == "comment":
                # Ensure media_id is a full standard UUID
                old_m_id = str(l.get("media_id") or "")
                if len(old_m_id) != 36 or old_m_id.startswith("comment_") or old_m_id.startswith("photo_"):
                    # Check if there is already a meta file with a UUID
                    m_uuid = None
                    for mf in media_meta_dir.glob("*.json"):
                        try:
                            md = json.loads(mf.read_text(encoding="utf-8"))
                            if md.get("owner_type") == "comment" and md.get("facebook_post_id") == fb_post_id:
                                if md.get("author_display_name") == author_name:
                                    m_uuid = md.get("id")
                                    break
                        except Exception:
                            pass
                    if not m_uuid or len(m_uuid) != 36:
                        m_uuid = str(uuid.uuid4())
                else:
                    m_uuid = old_m_id

                new_img_name = f"{m_uuid}.jpg"

                # Find existing comment image file to rename
                found_img = None
                # Check direct UUID
                if (comments_img_dir / new_img_name).exists():
                    found_img = comments_img_dir / new_img_name
                else:
                    for img_f in comments_img_dir.glob("*.jpg"):
                        # Match by prefix or old naming
                        if old_m_id and (img_f.name.startswith(old_m_id[:8]) or old_m_id in img_f.name):
                            found_img = img_f
                            break
                        if author_name and author_name.lower().replace(" ", "_") in img_f.name.lower():
                            found_img = img_f
                            break

                if found_img and found_img.exists():
                    dest_img = comments_img_dir / new_img_name
                    if found_img != dest_img:
                        found_img.rename(dest_img)
                        print(f"  Comment Image {found_img.name} -> {new_img_name}")

                l["media_id"] = m_uuid
                l["image_file"] = new_img_name
                l["image_path"] = f"groups/{group_slug}/images/comments/{new_img_name}"

                # Update or create media metadata file
                meta_file = media_meta_dir / f"{m_uuid}.json"
                meta_data = {
                    "id": m_uuid,
                    "media_type": "image",
                    "owner_type": "comment",
                    "owner_id": m_uuid,
                    "author_id": author_id,
                    "author_display_name": author_name,
                    "author_profile_url": author_url,
                    "author_is_anonymous": is_anon,
                    "post_id": p_uuid,
                    "facebook_post_id": fb_post_id,
                    "facebook_comment_id": l.get("comment_id"),
                    "position": 0,
                    "storage_uri": f"groups/{group_slug}/images/comments/{new_img_name}",
                    "download_status": "downloaded",
                    "ocr_status": "complete",
                    "cic_data": {
                        "is_cic": True,
                        "score": l.get("score"),
                        "tier": l.get("tier"),
                        "scoring_date": l.get("scoring_date"),
                        "customer_name": l.get("customer_name"),
                        "id_card_number": l.get("id_card_number"),
                        "phone_number": l.get("phone_number"),
                        "total_debt": l.get("total_debt"),
                        "has_bad_debt": l.get("has_bad_debt"),
                        "provider": l.get("provider"),
                    }
                }
                meta_file.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Updated Media Meta {m_uuid}.json (mapped to author {author_name} [{author_id}])")

            else:
                # Post lead
                p_media_id = l.get("media_id") or str(uuid.uuid4())
                if len(p_media_id) != 36:
                    p_media_id = str(uuid.uuid4())
                l["media_id"] = p_media_id
                l["image_file"] = f"{p_uuid}_0.jpg"
                l["image_path"] = f"groups/{group_slug}/images/posts/{p_uuid}_0.jpg"

        leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved {len(leads)} leads with standard UUIDs and author mapping to {leads_path}")

    print("\nResync Finished Successfully!")

if __name__ == "__main__":
    main()
