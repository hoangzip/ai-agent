"""
collector/facebook/comment_cic.py — Extract CIC Credit Score Reports from Facebook Comments.

Handles user requirements:
1. Finds comments containing photo attachments (photo.php or /photo/).
2. Extracts comment author (Commenter, NOT Post Author) with anonymity check.
3. Loads high-resolution photo from Photo Theater (preventing low-res thumbnail OCR failure).
4. Runs CICExtractor to parse score, tier, scoring_date, customer_name, total_debt, etc.
5. Captures customer phone number from comment text if not present on image.
6. Returns structured lead entries for cic_customers.json and persists media records.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Optional
import uuid

from collector.analysis.cic_extractor import CICExtractor, CICReportInfo
from collector.downloaders.media_downloader import MediaDownloader
from collector.pipeline.normalizer import clean_facebook_url, is_anonymous_user
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, CommentRepo

logger = logging.getLogger("comment_cic")
VN_PHONE_RE = re.compile(r"\b(0(?:3[2-9]|5[6-9]|7[06-9]|8[1-9]|9[0-9])[.\s-]?\d{3}[.\s-]?\d{4})\b")


async def extract_comment_photos_from_page(page) -> list[dict]:
    """
    Extract all unique comment items containing photo attachments from the currently loaded page.
    Guaranteed: ONLY extracts real comments, NEVER the main post feed card.
    """
    raw_comments = await page.evaluate("""() => {
        const results = [];
        const articles = document.querySelectorAll("div[role='article']");
        
        for (let i = 0; i < articles.length; i++) {
            const el = articles[i];
            const ariaLabel = el.getAttribute("aria-label") || "";

            // Check if this article is genuinely a comment or reply (NEVER the post card):
            // 1. Must NOT be the first article (which is always the main post card)
            // 2. aria-label starts with 'Comment by', 'Reply by', 'Bình luận của', 'Câu trả lời của'
            //    OR is inside an ancestor list container (ul)
            const isCommentByAria = /^(?:Comment by|Reply by|Bình luận của|Câu trả lời của)/i.test(ariaLabel);
            const isInsideList = Boolean(el.closest("ul, [role='list']"));
            
            // Skip the main post card or any non-comment article
            if (i === 0 && !isCommentByAria) continue;
            if (!isCommentByAria && !isInsideList) continue;

            const photoA = el.querySelector("a[href*='photo.php'], a[href*='/photo/']");
            if (!photoA) continue;

            let authorName = null;
            let authorUrl = null;

            // Strategy 1: Extract author name from aria-label (e.g. 'Comment by Phạm Bá Thức 8 weeks ago')
            const matchAria = ariaLabel.match(/^(?:Comment by|Reply by|Bình luận của|Câu trả lời của)\s+(.+?)(?:\s+\d+\s+(?:weeks?|days?|hours?|mins?|ngày|giờ|tuần|tháng|phút)|\s+about|\s+vừa xong|$)/i);
            if (matchAria && matchAria[1]) {
                authorName = matchAria[1].trim();
            }

            // Strategy 2: Look for author profile link
            for (let a of el.querySelectorAll("a[role='link'], a[href*='/user/'], a[href*='profile.php']")) {
                const href = a.href || "";
                if (href.includes("/photo") || href.includes("comment_id=") || href.includes("reply_comment_id=")) continue;
                const txt = a.innerText.trim();
                if (txt && !txt.includes('Follow') && !txt.includes('Theo dõi') && !txt.includes('Bình luận') && !txt.includes('Phản hồi') && !txt.includes('Thích')) {
                    if (!authorName) authorName = txt;
                    authorUrl = href;
                    break;
                }
            }

            let commentText = null;
            for (let d of el.querySelectorAll("div[dir='auto']")) {
                const t = d.innerText.trim();
                if (t && t !== authorName && !t.includes('Thích') && !t.includes('Phản hồi') && !t.includes('Chia sẻ')) {
                    commentText = t;
                    break;
                }
            }

            let commentId = null;
            const anyLink = el.querySelector("a[href*='comment_id='], a[href*='reply_comment_id=']");
            if (anyLink) {
                const m = anyLink.href.match(/(?:comment_id|reply_comment_id)=(\d+)/);
                if (m) commentId = m[1];
            }

            let photoFbid = null;
            const mFbid = photoA.href.match(/fbid=(\d+)/);
            if (mFbid) photoFbid = mFbid[1];

            results.push({
                photo_href: photoA.href,
                photo_fbid: photoFbid,
                author_name: authorName,
                author_url: authorUrl,
                comment_text: commentText,
                comment_id: commentId
            });
        }
        return results;
    }""")

    # Deduplicate by photo_href
    seen_urls = set()
    unique = []
    for c in raw_comments:
        href = c.get("photo_href")
        if href and href not in seen_urls:
            seen_urls.add(href)
            unique.append(c)

    return unique


def _slugify(text: str | None) -> str:
    if not text:
        return "unknown"
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    clean = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean) or "unknown"


async def process_comment_cic_photo(
    photo_page,
    comment_data: dict,
    post_uuid: str,
    facebook_post_id: str,
    post_url: str,
    group_slug: str,
    layout: StorageLayout,
    downloader: MediaDownloader,
    actor_repo: ActorRepo,
    post_fbid: Optional[str] = None,
) -> Optional[dict]:
    """
    Open comment photo in photo_page, download full resolution image,
    run OCR / CIC extraction, and return customer lead dictionary if valid CIC report.
    """
    photo_href = comment_data["photo_href"]
    c_fbid = comment_data.get("photo_fbid")

    # If photo_fbid matches the post's own photo FBID, this is the post photo, NOT a comment photo
    if post_fbid and c_fbid and str(c_fbid) == str(post_fbid):
        logger.debug("Skipping comment photo because it matches post photo FBID %s", post_fbid)
        return None
    comment_id = comment_data.get("comment_id")
    raw_author_name = comment_data.get("author_name")
    raw_author_url = comment_data.get("author_url")
    comment_text = comment_data.get("comment_text")

    try:
        await photo_page.goto(photo_href, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2.0)
    except Exception as e:
        logger.debug("Failed opening comment photo %s: %s", photo_href, e)
        return None

    # Get high-resolution image source
    img_src = await photo_page.evaluate("""() => {
        const img = document.querySelector("div[data-pagelet='MediaViewerPhoto'] img, img[data-visualcompletion='media-vc-image']");
        return img ? img.src : null;
    }""")

    if not img_src:
        return None

    try:
        res = await downloader.download(img_src)
    except Exception as e:
        logger.debug("Failed downloading comment image %s: %s", img_src, e)
        return None

    # Standard full UUID for media (like 0b7fcc64-aec0-4497-bd95-0440f413a02d)
    m_id = str(uuid.uuid4())
    img_filename = f"{m_id}.{res.ext}"
    named_dir = layout.root / "groups" / group_slug / "images" / "comments"
    named_dir.mkdir(parents=True, exist_ok=True)
    named_img_path = named_dir / img_filename
    named_img_path.write_bytes(res.content)

    # Sharded storage path
    file_path = await MediaDownloader.save_to_disk(layout, res)
    rel_uri = str(file_path.relative_to(layout.root))

    # OCR + CIC Extraction
    cic_report: CICReportInfo = await CICExtractor.extract_from_image(named_img_path)
    if not cic_report.is_cic:
        return None

    cic_dict = cic_report.to_dict()

    # Capture customer phone number from comment text if not found in image OCR
    phone_num = cic_dict.get("phone_number")
    if not phone_num and comment_text:
        m_phone = VN_PHONE_RE.search(comment_text)
        if m_phone:
            phone_num = re.sub(r"[^\d]", "", m_phone.group(1))
            cic_dict["phone_number"] = phone_num

    # Determine author anonymity
    is_anon = False
    clean_author_url = clean_facebook_url(raw_author_url) if raw_author_url else None
    if raw_author_name:
        is_anon = is_anonymous_user(raw_author_name, clean_author_url)
    if any(w in (raw_author_name or "").lower() for w in ("anonymous", "ẩn danh")):
        is_anon = True
        raw_author_name = "Anonymous participant"
        clean_author_url = None

    # Upsert comment author to ActorRepo to get standard author UUID
    author_id = None
    if raw_author_name or clean_author_url:
        fb_uid = None
        if clean_author_url and not is_anon:
            m_user = re.search(r"/(?:user|profile\.php\?id=)/(\d+)", clean_author_url)
            if m_user:
                fb_uid = m_user.group(1)
        try:
            actor_rec, _ = await actor_repo.upsert({
                "facebook_user_id": fb_uid,
                "profile_url": clean_author_url if not is_anon else None,
                "display_name": raw_author_name or "Anonymous participant",
                "is_anonymous": is_anon,
                "anonymous_scope_post_id": str(facebook_post_id) if is_anon else None,
            })
            author_id = actor_rec["id"]
        except Exception:
            pass

    # Upsert comment into CommentRepo
    comment_internal_id = m_id
    try:
        comment_repo = CommentRepo(layout, post_uuid)
        c_record, _ = await comment_repo.upsert({
            "facebook_comment_id": comment_id,
            "author_id": author_id,
            "author_display_name": raw_author_name,
            "author_profile_url": clean_author_url if not is_anon else None,
            "author_is_anonymous": is_anon,
            "content": comment_text,
            "media_urls": [photo_href],
            "media_ids": [m_id],
            "comment_url": f"{post_url}?comment_id={comment_id}" if comment_id else None,
        })
        if c_record.get("id"):
            comment_internal_id = c_record["id"]
    except Exception as e_repo:
        logger.debug("Error upserting comment record: %s", e_repo)

    # Save media metadata with user mapping
    meta_path = layout.media_meta_path(m_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_dict = {
        "id": m_id,
        "media_type": "image",
        "source_url": img_src,
        "owner_type": "comment",
        "owner_id": comment_internal_id or m_id,
        "author_id": author_id,
        "author_display_name": raw_author_name,
        "author_profile_url": clean_author_url if not is_anon else None,
        "author_is_anonymous": is_anon,
        "post_id": post_uuid,
        "facebook_post_id": str(facebook_post_id),
        "facebook_comment_id": comment_id,
        "position": 0,
        "storage_uri": str(named_img_path.relative_to(layout.root)),
        "sha256": res.sha256,
        "mime_type": res.mime_type,
        "file_size": res.file_size,
        "download_status": "downloaded",
        "ocr_status": "complete",
        "ocr_text": cic_report.raw_text[:1000] if cic_report.raw_text else None,
        "cic_data": cic_dict,
    }
    meta_path.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    lead_entry = {
        "lead_source": "comment",
        "post_id": post_uuid,
        "facebook_post_id": str(facebook_post_id),
        "post_url": post_url,
        "comment_id": comment_id,
        "comment_text": comment_text,
        "media_id": m_id,
        "image_file": img_filename,
        "image_path": f"groups/{group_slug}/images/comments/{img_filename}",
        "author_id": author_id,
        "author_display_name": raw_author_name,
        "author_profile_url": clean_author_url if not is_anon else None,
        "author_is_anonymous": is_anon,
        "customer_name": cic_dict.get("customer_name"),
        "id_card_number": cic_dict.get("id_card_number"),
        "phone_number": phone_num,
        "date_of_birth": cic_dict.get("date_of_birth"),
        "cic_code": cic_dict.get("cic_code"),
        "address": cic_dict.get("address"),
        "score": cic_dict.get("score"),
        "tier": cic_dict.get("tier"),
        "scoring_date": cic_dict.get("scoring_date"),
        "total_debt": cic_dict.get("total_debt"),
        "has_bad_debt": cic_dict.get("has_bad_debt"),
        "provider": cic_dict.get("provider"),
    }

    return lead_entry
