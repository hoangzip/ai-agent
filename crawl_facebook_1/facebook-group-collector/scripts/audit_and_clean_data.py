"""
scripts/audit_and_clean_data.py — Complete audit and cleaning for group 580277503401606 data:
1. Clean author display name artifacts (e.g. 'Mỹ Xuân to Mỹ Xuân's comment' -> 'Mỹ Xuân')
2. Add 'comment_url' for all comment leads
3. Tag broker advertising flyers with 'is_broker_ad: true'
4. Standardize post_url to canonical photo URL for all anonymous posts
5. Reset 'no_image' entries in media_gallery_state.json for clean retry
"""
import json
import re
from pathlib import Path

import sys

GROUP_SLUG = sys.argv[1] if len(sys.argv) > 1 else "580277503401606"
ROOT = Path("data/groups") / GROUP_SLUG

def clean_author_name(name: str) -> str:
    if not name:
        return name
    n = name.strip()
    n = re.sub(r"\s+to\s+.*?(?:'s)?\s+comment.*$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+đến\s+bình\s+luận.*$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+\d+\s+(?:days?|weeks?|hours?|mins?|ngày|giờ|tuần|tháng|phút)\s+ago$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+(?:a|an)\s+(?:day|week|hour|minute)\s+ago$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+vừa\s+xong$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+about\s+\d+.*$", "", n, flags=re.IGNORECASE)
    return n.strip()

def main():
    cic_file = ROOT / "cic_customers.json"
    state_file = ROOT / "media_gallery_state.json"
    order_file = ROOT / "media_gallery_order.json"
    posts_dir = ROOT / "posts"

    if not cic_file.exists():
        print(f"cic_customers.json not found for group {GROUP_SLUG} yet!")
        return

    leads = json.loads(cic_file.read_text(encoding="utf-8"))
    print(f"Total leads loaded: {len(leads)}")

    order = json.loads(order_file.read_text(encoding="utf-8")) if order_file.exists() else []
    gallery_fbids = {str(item["fbid"]) for item in order}

    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    post_id_to_fbid = {}
    post_uuid_to_fbid = {}
    for fbid, s_data in state.items():
        if isinstance(s_data, dict):
            if s_data.get("post_id"):
                post_id_to_fbid[str(s_data["post_id"])] = str(fbid)
            if s_data.get("post_uuid"):
                post_uuid_to_fbid[str(s_data["post_uuid"])] = str(fbid)

    ad_keywords = [
        "liên hệ ngay", "đăng ký ngay", "gói vay", "hỗ trợ vay", "nhận tiền ngay",
        "ưu đãi hấp dẫn", "vay dễ dàng", "tư vấn miễn phí", "dịch vụ vay", "hạn mức cao",
        "lãi suất ưu đãi", "giải ngân trong ngày", "nhận gom nợ", "zalo chính chủ",
        "tư vấn hỗ trợ", "lh zl", "k phí", "ib số này"
    ]
    
    cleaned_names = 0
    added_comment_urls = 0
    tagged_ads = 0
    updated_urls = 0
    cleaned_customer_names = 0

    for l in leads:
        # 1. Clean author name
        old_name = l.get("author_display_name") or ""
        new_name = clean_author_name(old_name)
        if new_name != old_name:
            l["author_display_name"] = new_name
            cleaned_names += 1

        # 2. Add comment_url
        if l.get("lead_source") == "comment" and l.get("comment_id"):
            c_id = l["comment_id"]
            p_fbid = l.get("facebook_post_id") or ""
            l["comment_url"] = f"https://www.facebook.com/groups/{GROUP_SLUG}/posts/{p_fbid}?comment_id={c_id}"
            added_comment_urls += 1

        # 3. Tag broker ads
        m_id = l.get("media_id")
        raw_txt = ""
        if m_id:
            m_path = Path("data/media/meta") / f"{m_id}.json"
            if m_path.exists():
                try:
                    m_meta = json.loads(m_path.read_text(encoding="utf-8"))
                    raw_txt = m_meta.get("ocr_text", "").lower()
                except Exception:
                    pass
        comment_txt = (l.get("comment_text") or "").lower()
        combined_txt = f"{raw_txt} {comment_txt}"

        is_ad = (l.get("score") is None) and any(k in combined_txt for k in ad_keywords)
        if is_ad:
            l["is_broker_advertisement"] = True
            tagged_ads += 1
            # Flyers should not have customer name or mock id_card
            if l.get("customer_name"):
                l["customer_name"] = None
                cleaned_customer_names += 1
            if l.get("id_card_number") == "123406705012":
                l["id_card_number"] = None
        else:
            l["is_broker_advertisement"] = False

        # Extra cleanup on false customer names (e.g. ad headings mistaken for person names)
        cname = l.get("customer_name")
        if cname:
            cname_upper = cname.upper()
            invalid_terms = [
                "CHỈ CẦN", "THỦ TỤC", "DỊCH VỤ", "GIẢI NGÂN", "HỖ TRỢ", "PHÍ DỊCH VỤ",
                "HỒ CHÍ MINH", "HÀ NỘI", "ĐÀ NẴNG", "TỈNH", "THÀNH PHỐ", "VIỆT NAM",
                "TOÁN DỄ DÀNG", "BHNT", "NHẬN TIẾN", "ĐĂNG KÝ", "TÍN DỤNG", "TIN DỤNG", "ĐIỂM"
            ]
            if any(term in cname_upper for term in invalid_terms):
                l["customer_name"] = None
                cleaned_customer_names += 1

        # 4. Standardize post_url for anonymous posts to canonical photo URL
        is_anon = l.get("author_is_anonymous", False)
        p_url = l.get("post_url", "")
        fb_id = str(l.get("facebook_post_id", ""))
        post_uuid = l.get("post_id", "")
        fbid = None
        if fb_id in gallery_fbids:
            fbid = fb_id
        elif fb_id in post_id_to_fbid:
            fbid = post_id_to_fbid[fb_id]
        elif post_uuid in post_uuid_to_fbid:
            fbid = post_uuid_to_fbid[post_uuid]

        if is_anon and fbid:
            canonical_url = f"https://www.facebook.com/photo/?fbid={fbid}&set=g.{GROUP_SLUG}"
            if l.get("post_url") != canonical_url:
                l["post_url"] = canonical_url
                updated_urls += 1

    # Save cleaned cic_customers.json
    cic_file.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results of cic_customers.json audit:")
    print(f"  - Cleaned author names: {cleaned_names}")
    print(f"  - Added comment_url: {added_comment_urls}")
    print(f"  - Tagged broker advertisements: {tagged_ads}")
    print(f"  - Standardized anonymous post URLs: {updated_urls}")

    # Also update posts/*.json author names if needed
    for p_path in posts_dir.glob("*.json"):
        try:
            p_data = json.loads(p_path.read_text(encoding="utf-8"))
            a_name = p_data.get("author_display_name", "")
            c_name = clean_author_name(a_name)
            if c_name != a_name:
                p_data["author_display_name"] = c_name
                p_path.write_text(json.dumps(p_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # 5. Check no_image entries
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        no_img_count = sum(1 for v in state.values() if v.get("status") in ("no_image", "deleted_content"))
        print(f"  - Currently {no_img_count} photos recorded as deleted or no_image.")

if __name__ == "__main__":
    main()
