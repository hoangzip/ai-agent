#!/usr/bin/env python3
"""
scripts/migrate_to_semantic_ids.py — Standardize all IDs from random UUIDs/hashes
to human-readable, semantic Facebook IDs across posts, images, and cic_customers.json.
"""
import json
from pathlib import Path
import re
import unicodedata

def slugify(text: str | None) -> str:
    if not text:
        return "unknown"
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    clean = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean) or "unknown"

def main():
    group_slug = "978769317924542"
    base_dir = Path(f"data/groups/{group_slug}")
    posts_dir = base_dir / "posts"
    comments_img_dir = base_dir / "images" / "comments"
    posts_img_dir = base_dir / "images" / "posts"
    leads_path = base_dir / "cic_customers.json"

    print("Step 1: Renaming post JSON files to Facebook Post IDs...")
    post_uuid_to_fbid = {}
    for p in list(posts_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            fbid = d.get("facebook_post_id")
            old_id = d.get("id")
            if fbid:
                post_uuid_to_fbid[old_id] = str(fbid)
                d["id"] = str(fbid)
                new_path = posts_dir / f"{fbid}.json"
                new_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                if p != new_path:
                    p.unlink()
                print(f"  Post {p.name} -> {new_path.name}")
        except Exception as e:
            print(f"  Error processing post {p.name}: {e}")

    print("\nStep 2: Normalizing cic_customers.json and comment images...")
    if leads_path.exists():
        leads = json.loads(leads_path.read_text(encoding="utf-8"))
        for l in leads:
            source = l.get("lead_source") or "post"
            fbid = l.get("facebook_post_id")
            cid = l.get("comment_id")
            author_name = l.get("author_display_name")
            author_url = l.get("author_profile_url")
            is_anon = l.get("author_is_anonymous", False)
            old_media_id = l.get("media_id") or ""
            author_slug = slugify(author_name)

            # Determine author_id
            author_id = None
            if author_url and not is_anon:
                m_user = re.search(r"/(?:user|profile\.php\?id=)/(\d+)", author_url)
                if m_user:
                    author_id = f"user_{m_user.group(1)}"
            if not author_id:
                author_id = f"anon_p{fbid}_{author_slug}" if is_anon else f"user_{author_slug}"
            l["author_id"] = author_id

            # Standardize post_id
            l["post_id"] = str(fbid)

            if source == "comment":
                # Determine new semantic media_id & image_file
                if cid:
                    new_media_id = f"comment_{cid}"
                else:
                    new_media_id = f"comment_p{fbid}_{author_slug}"
                new_img_name = f"{new_media_id}.jpg"

                # Check if old image file exists
                old_short = old_media_id[:8]
                matched_old_file = None
                for candidate in comments_img_dir.glob("*.jpg"):
                    if old_short and candidate.name.startswith(old_short):
                        matched_old_file = candidate
                        break
                    if cid and candidate.name.startswith(cid):
                        matched_old_file = candidate
                        break

                if matched_old_file and matched_old_file.exists():
                    target_file = comments_img_dir / new_img_name
                    if matched_old_file != target_file:
                        matched_old_file.rename(target_file)
                        print(f"  Image {matched_old_file.name} -> {new_img_name}")

                l["media_id"] = new_media_id
                l["image_file"] = new_img_name
                l["image_path"] = f"groups/{group_slug}/images/comments/{new_img_name}"

            else:
                # Post lead
                new_media_id = f"post_{fbid}_0"
                new_img_name = f"{fbid}_0.jpg"
                l["media_id"] = new_media_id
                l["image_file"] = new_img_name
                l["image_path"] = f"groups/{group_slug}/images/posts/{new_img_name}"

        leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(leads)} normalized leads to {leads_path}")

    print("\nMigration to Semantic Facebook IDs Completed Successfully!")

if __name__ == "__main__":
    main()
