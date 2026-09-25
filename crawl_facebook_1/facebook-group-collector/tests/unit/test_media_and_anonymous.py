"""
tests/unit/test_media_and_anonymous.py — Comprehensive tests for:
1. Anonymous user vs. real user classification.
2. Cross-post anonymous actor scoping (preventing accidental identity merge).
3. Post and Comment storage of author_is_anonymous & image attachments.
4. MediaWorker saving to human-readable group images folder & linking.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from collector.config import MediaConfig
from collector.downloaders.media_downloader import DownloadResult
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import MediaJobItem
from collector.pipeline.normalizer import is_anonymous_user
from collector.storage.layout import StorageLayout
from collector.storage.repository import ActorRepo, CommentRepo, PostRepo
from collector.workers.media_worker import MediaWorker


def test_is_anonymous_user_detection():
    # Vietnamese keywords
    assert is_anonymous_user("Người tham gia ẩn danh") is True
    assert is_anonymous_user("Thành viên ẩn danh") is True
    assert is_anonymous_user("Người dùng ẩn danh") is True

    # English keywords
    assert is_anonymous_user("Anonymous participant") is True
    assert is_anonymous_user("Anonymous member") is True
    assert is_anonymous_user("Anonymous") is True

    # Generated pseudonym patterns (Adjective + Animal/Noun + digits)
    assert is_anonymous_user("StunningDachshund8945") is True
    assert is_anonymous_user("ArticulateFrog1260") is True
    assert is_anonymous_user("PositiveHummingbird3334") is True
    assert is_anonymous_user("Anonymous participant 714") is True

    # Real users
    assert is_anonymous_user("Nguyen Thao") is False
    assert is_anonymous_user("TRANGVCB1986.") is False
    assert is_anonymous_user("Ngô Hoàng Khôi") is False
    assert is_anonymous_user(None) is False
    assert is_anonymous_user("") is False


@pytest.mark.asyncio
async def test_actor_anonymous_scoping_prevents_cross_post_merge(tmp_path: Path):
    """
    Ensure 2 anonymous posts across different posts get distinct Actor IDs,
    while comments under the same post with the same alias reuse the same Actor ID.
    Real users across different posts are merged by facebook_user_id or profile_url.
    """
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)
    actor_repo = ActorRepo(layout, group_slug)

    # 1. Anonymous user in Post 1
    actor1, is_new1 = await actor_repo.upsert({
        "display_name": "Anonymous participant",
        "is_anonymous": True,
        "anonymous_scope_post_id": "post_111",
    })
    assert is_new1 is True
    assert actor1["is_anonymous"] is True
    assert actor1["anonymous_scope_post_id"] == "post_111"

    # 2. Anonymous user in Post 2 (same display name!)
    actor2, is_new2 = await actor_repo.upsert({
        "display_name": "Anonymous participant",
        "is_anonymous": True,
        "anonymous_scope_post_id": "post_222",
    })
    assert is_new2 is True
    assert actor2["is_anonymous"] is True
    assert actor2["anonymous_scope_post_id"] == "post_222"
    # MUST NOT MERGE!
    assert actor1["id"] != actor2["id"]

    # 3. Same anonymous user posting comment in Post 1 -> reuses actor1
    actor1_repeat, is_new3 = await actor_repo.upsert({
        "display_name": "Anonymous participant",
        "is_anonymous": True,
        "anonymous_scope_post_id": "post_111",
    })
    assert is_new3 is False
    assert actor1_repeat["id"] == actor1["id"]

    # 4. Real user across Post 1 and Post 2 -> MUST MERGE!
    real1, rnew1 = await actor_repo.upsert({
        "display_name": "Nguyen Thao",
        "facebook_user_id": "1000123456",
        "profile_url": "https://facebook.com/nguyenthao",
        "is_anonymous": False,
        "anonymous_scope_post_id": "post_111",
    })
    real2, rnew2 = await actor_repo.upsert({
        "display_name": "Nguyen Thao Updated",
        "facebook_user_id": "1000123456",
        "profile_url": "https://facebook.com/nguyenthao",
        "is_anonymous": False,
        "anonymous_scope_post_id": "post_222",
    })
    assert rnew1 is True
    assert rnew2 is False
    assert real1["id"] == real2["id"]
    assert real2["is_anonymous"] is False


@pytest.mark.asyncio
async def test_post_and_comment_anonymous_and_media_fields(tmp_path: Path):
    """Verify PostRepo and CommentRepo persist author_is_anonymous and media attachments."""
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    post_repo = PostRepo(layout, group_slug)
    post_rec, _ = await post_repo.upsert({
        "facebook_post_id": "fb_post_999",
        "author_display_name": "Anonymous participant",
        "author_is_anonymous": True,
        "content": "Bài viết ẩn danh cần tư vấn vay vốn",
    })
    assert post_rec["author_is_anonymous"] is True
    assert post_rec["author_display_name"] == "Anonymous participant"

    comment_repo = CommentRepo(layout, post_rec["id"])
    cmt_rec, _ = await comment_repo.upsert({
        "facebook_comment_id": "fb_cmt_001",
        "author_display_name": "ArticulateFrog1260",
        "author_is_anonymous": True,
        "content": "Bn vay AEON có thẩm định j ko b",
        "media_urls": ["https://scontent.fbcdn.net/v/cmt_img1.jpg"],
    })
    assert cmt_rec["author_is_anonymous"] is True
    assert cmt_rec["author_display_name"] == "ArticulateFrog1260"
    assert cmt_rec["media_urls"] == ["https://scontent.fbcdn.net/v/cmt_img1.jpg"]


@pytest.mark.asyncio
async def test_media_worker_stores_images_in_human_folder_and_links(tmp_path: Path):
    """
    Verify MediaWorker stores images in data/groups/{group_slug}/images/{posts,comments}/
    and properly updates post and comment records with media_ids.
    """
    layout = StorageLayout(str(tmp_path))
    group_slug = "test_group"
    layout.ensure_dirs(group_slug)

    post_repo = PostRepo(layout, group_slug)
    post_rec, _ = await post_repo.upsert({
        "facebook_post_id": "post_cic_101",
        "author_display_name": "Anonymous participant",
        "author_is_anonymous": True,
        "content": "Vừa mới vay bên aeon 10tr...",
    })
    post_id = post_rec["id"]

    comment_repo = CommentRepo(layout, post_id)
    cmt_rec, _ = await comment_repo.upsert({
        "facebook_comment_id": "cmt_proof_202",
        "author_display_name": "Anonymous participant 714",
        "author_is_anonymous": True,
        "content": "Để lại sdt mình kb zalo",
    })
    comment_id = cmt_rec["id"]

    counters = MetricsCounters()
    mock_downloader = MagicMock()

    img_post_bytes = b"IMAGE_POST_BYTES_12345"
    img_cmt_bytes = b"IMAGE_COMMENT_BYTES_67890"

    async def mock_download(url: str):
        if "post" in url:
            data = img_post_bytes
        else:
            data = img_cmt_bytes
        sha = hashlib.sha256(data).hexdigest()
        return DownloadResult(
            content=data,
            sha256=sha,
            file_size=len(data),
            mime_type="image/jpeg",
            ext="jpg",
        )

    mock_downloader.download = AsyncMock(side_effect=mock_download)

    worker = MediaWorker(
        name="test-worker",
        queue=asyncio.Queue(),
        counters=counters,
        layout=layout,
        group_slug=group_slug,
        config=MediaConfig(),
        downloader=mock_downloader,
    )

    # 1. Download Post Media
    job_post = MediaJobItem(
        owner_type="post",
        owner_id=post_id,
        post_id=post_id,
        source_url="https://scontent.fbcdn.net/v/t39/post_screenshot.jpg",
        position=0,
    )
    await worker.process_item(job_post)

    # 2. Download Comment Media
    job_cmt = MediaJobItem(
        owner_type="comment",
        owner_id=comment_id,
        post_id=post_id,
        source_url="https://scontent.fbcdn.net/v/t39/comment_photo.jpg",
        position=0,
    )
    await worker.process_item(job_cmt)

    # Verify dedicated human-inspectable image files exist on disk
    post_img_path = layout.group_post_image_path(group_slug, post_id, 0, "jpg")
    cmt_img_path = layout.group_comment_image_path(group_slug, comment_id, 0, "jpg")

    assert post_img_path.exists(), f"Post image not found at {post_img_path}"
    assert post_img_path.read_bytes() == img_post_bytes

    assert cmt_img_path.exists(), f"Comment image not found at {cmt_img_path}"
    assert cmt_img_path.read_bytes() == img_cmt_bytes

    # Verify post and comment media_ids linking
    updated_post = await post_repo.get(post_id)
    assert len(updated_post["media_ids"]) == 1

    updated_cmt = await comment_repo.get(comment_id)
    assert len(updated_cmt["media_ids"]) == 1
