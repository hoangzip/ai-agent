"""
tests/unit/test_storage.py — Tests for file-based JSON storage layer.

Tests verify:
1. JSON read/write atomicity (temp-file rename)
2. Index creation and update
3. GroupRepo UPSERT idempotency
4. PostRepo UPSERT with facebook_post_id key
5. PostRepo UPSERT fallback to post_url
6. CommentRepo UPSERT with facebook_comment_id
7. CommentRepo dedupe_key fallback (NOT stored in facebook_comment_id)
8. MediaRepo SHA-256 dedup
9. CheckpointRepo save/load/clear
10. StorageLayout path correctness
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from collector.storage.json_store import read_index, read_json, update_index, write_json
from collector.storage.layout import StorageLayout, slugify
from collector.storage.repository import (
    ActorRepo,
    CheckpointRepo,
    CommentRepo,
    GroupRepo,
    MediaRepo,
    PostRepo,
    RunRepo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_root(tmp_path):
    """Temporary data root directory."""
    return tmp_path


@pytest.fixture
def layout(tmp_root):
    return StorageLayout(root_dir=tmp_root)


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_extracts_group_id_from_url(self):
        slug = slugify("https://www.facebook.com/groups/my_group_123")
        assert slug == "my_group_123"

    def test_handles_plain_id(self):
        slug = slugify("123456789")
        assert "123456789" in slug

    def test_safe_characters_only(self):
        slug = slugify("Some Group! @#$%")
        assert all(c.isalnum() or c in "-_" for c in slug)

    def test_max_length(self):
        slug = slugify("a" * 200)
        assert len(slug) <= 80


# ---------------------------------------------------------------------------
# json_store — atomic write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_json_creates_file(tmp_path):
    path = tmp_path / "test.json"
    await write_json(path, {"key": "value"})
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["key"] == "value"


@pytest.mark.asyncio
async def test_write_json_no_tmp_file_on_success(tmp_path):
    """After write, .tmp file must not exist."""
    path = tmp_path / "test.json"
    await write_json(path, {"x": 1})
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.asyncio
async def test_read_json_returns_none_for_missing(tmp_path):
    result = await read_json(tmp_path / "nonexistent.json")
    assert result is None


@pytest.mark.asyncio
async def test_update_index_merges(tmp_path):
    path = tmp_path / "index.json"
    await update_index(path, {"a": "1"})
    await update_index(path, {"b": "2"})
    idx = await read_index(path)
    assert idx["a"] == "1"
    assert idx["b"] == "2"


@pytest.mark.asyncio
async def test_update_index_overwrites_existing_key(tmp_path):
    path = tmp_path / "index.json"
    await update_index(path, {"key": "old"})
    await update_index(path, {"key": "new"})
    idx = await read_index(path)
    assert idx["key"] == "new"


# ---------------------------------------------------------------------------
# StorageLayout
# ---------------------------------------------------------------------------

class TestStorageLayout:
    def test_group_meta_path(self, layout, tmp_root):
        path = layout.group_meta_path("mygroup")
        assert path == tmp_root / "groups" / "mygroup" / "meta.json"

    def test_post_path(self, layout, tmp_root):
        path = layout.post_path("mygroup", "post-uuid-123")
        assert path == tmp_root / "groups" / "mygroup" / "posts" / "post-uuid-123.json"

    def test_comment_path(self, layout, tmp_root):
        path = layout.comment_path("post-uuid", "comment-uuid")
        assert path == tmp_root / "comments" / "post-uuid" / "comment-uuid.json"

    def test_media_file_path_sharded(self, layout, tmp_root):
        sha256 = "abcdef1234567890" + "0" * 48
        path = layout.media_file_path(sha256, "jpg")
        # First 2 + next 2 chars as shard dirs
        assert "ab" in str(path)
        assert "cd" in str(path)

    def test_checkpoint_path(self, layout, tmp_root):
        path = layout.checkpoint_path("mygroup", "full")
        assert path == tmp_root / "checkpoints" / "mygroup_full.json"

    def test_ensure_dirs_creates_structure(self, layout, tmp_root):
        layout.ensure_dirs("testgroup")
        assert (tmp_root / "groups" / "testgroup").exists()
        assert (tmp_root / "groups" / "testgroup" / "posts").exists()
        assert (tmp_root / "media" / "assets").exists()
        assert (tmp_root / "checkpoints").exists()
        assert (tmp_root / "index").exists()


# ---------------------------------------------------------------------------
# GroupRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_repo_create(layout):
    repo = GroupRepo(layout)
    record, is_new = await repo.upsert({
        "facebook_group_id": "123456",
        "group_name": "Test Group",
        "group_url": "https://facebook.com/groups/testgroup",
    })
    assert is_new is True
    assert record["facebook_group_id"] == "123456"
    assert record["group_name"] == "Test Group"
    assert record["id"]  # UUID assigned


@pytest.mark.asyncio
async def test_group_repo_upsert_idempotent(layout):
    repo = GroupRepo(layout)
    r1, new1 = await repo.upsert({"facebook_group_id": "123", "group_name": "G", "group_url": "https://fb.com/groups/g"})
    r2, new2 = await repo.upsert({"facebook_group_id": "123", "group_name": "G Updated", "group_url": "https://fb.com/groups/g"})
    assert new1 is True
    assert new2 is False
    assert r1["id"] == r2["id"]  # Same internal ID
    assert r2["group_name"] == "G Updated"  # Updated


# ---------------------------------------------------------------------------
# PostRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_repo_create_by_fb_id(layout):
    repo = PostRepo(layout, "testgroup")
    layout.ensure_dirs("testgroup")
    record, is_new = await repo.upsert({
        "facebook_post_id": "post_abc",
        "post_url": "https://fb.com/groups/testgroup/posts/post_abc",
        "content": "Hello world",
    })
    assert is_new is True
    assert record["facebook_post_id"] == "post_abc"


@pytest.mark.asyncio
async def test_post_repo_upsert_idempotent_by_fb_id(layout):
    repo = PostRepo(layout, "testgroup")
    layout.ensure_dirs("testgroup")
    r1, n1 = await repo.upsert({"facebook_post_id": "post_xyz", "content": "v1"})
    r2, n2 = await repo.upsert({"facebook_post_id": "post_xyz", "content": "v2"})
    assert n1 is True
    assert n2 is False
    assert r1["id"] == r2["id"]


@pytest.mark.asyncio
async def test_post_repo_fallback_to_url(layout):
    """When facebook_post_id is None, dedup by post_url."""
    repo = PostRepo(layout, "testgroup")
    layout.ensure_dirs("testgroup")
    url = "https://fb.com/permalink/123"
    r1, n1 = await repo.upsert({"facebook_post_id": None, "post_url": url})
    r2, n2 = await repo.upsert({"facebook_post_id": None, "post_url": url})
    assert n1 is True
    assert n2 is False
    assert r1["id"] == r2["id"]


@pytest.mark.asyncio
async def test_post_repo_exists(layout):
    repo = PostRepo(layout, "testgroup")
    layout.ensure_dirs("testgroup")
    assert not await repo.exists("post_99", None)
    await repo.upsert({"facebook_post_id": "post_99"})
    assert await repo.exists("post_99", None)


@pytest.mark.asyncio
async def test_post_repo_status_update(layout):
    repo = PostRepo(layout, "testgroup")
    layout.ensure_dirs("testgroup")
    r, _ = await repo.upsert({"facebook_post_id": "post_status"})
    await repo.update_status(r["id"], "COMPLETE")
    updated = await repo.get(r["id"])
    assert updated["crawl_status"] == "COMPLETE"


# ---------------------------------------------------------------------------
# CommentRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comment_repo_create(layout):
    repo = CommentRepo(layout, "post-uuid-001")
    record, is_new = await repo.upsert({
        "facebook_comment_id": "cmt_abc",
        "content": "Great post!",
        "depth": 0,
    })
    assert is_new is True
    assert record["facebook_comment_id"] == "cmt_abc"
    assert record["depth"] == 0


@pytest.mark.asyncio
async def test_comment_repo_idempotent_by_fb_id(layout):
    repo = CommentRepo(layout, "post-uuid-001")
    r1, n1 = await repo.upsert({"facebook_comment_id": "cmt_001", "content": "v1"})
    r2, n2 = await repo.upsert({"facebook_comment_id": "cmt_001", "content": "v2"})
    assert n1 is True
    assert n2 is False
    assert r1["id"] == r2["id"]


@pytest.mark.asyncio
async def test_comment_dedupe_key_is_not_facebook_id(layout):
    """
    CRITICAL: dedupe_key must NEVER be stored in facebook_comment_id.
    When facebook_comment_id is unavailable, it stays None.
    """
    repo = CommentRepo(layout, "post-uuid-002")
    record, _ = await repo.upsert({
        "facebook_comment_id": None,
        "content": "A comment without FB ID",
        "author_profile_url": "https://fb.com/user/john",
        "commented_at": "2024-01-01T10:00:00",
        "depth": 0,
    })
    # facebook_comment_id must remain None
    assert record["facebook_comment_id"] is None
    # dedupe_key must be a hash (not None)
    assert record["dedupe_key"] is not None
    assert len(record["dedupe_key"]) == 32  # 32-char hex


@pytest.mark.asyncio
async def test_comment_dedupe_key_fallback_idempotency(layout):
    """Same comment without FB ID must not create duplicate via dedupe_key."""
    repo = CommentRepo(layout, "post-uuid-003")
    data = {
        "facebook_comment_id": None,
        "content": "Dedupe me",
        "author_profile_url": "https://fb.com/user/jane",
        "commented_at": "2024-01-02T12:00:00",
        "depth": 0,
    }
    r1, n1 = await repo.upsert(data)
    r2, n2 = await repo.upsert(data)
    assert n1 is True
    assert n2 is False
    assert r1["id"] == r2["id"]


# ---------------------------------------------------------------------------
# MediaRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_media_repo_create_pending(layout):
    repo = MediaRepo(layout)
    layout.ensure_dirs("testgroup")
    record, is_new = await repo.upsert_by_url({
        "source_url": "https://cdn.fb.com/image.jpg",
        "owner_type": "post",
        "owner_id": "post-uuid-001",
        "position": 0,
    })
    assert record["download_status"] == "pending"
    assert record["sha256"] is None
    assert record["ocr_status"] == "pending"


@pytest.mark.asyncio
async def test_media_repo_sha256_dedup(layout):
    """Same file from two different URLs should only be stored once."""
    repo = MediaRepo(layout)
    layout.ensure_dirs("testgroup")

    r1, _ = await repo.upsert_by_url({"source_url": "https://cdn.fb.com/a.jpg", "owner_type": "post", "owner_id": "p1", "position": 0})
    r2, _ = await repo.upsert_by_url({"source_url": "https://cdn.fb.com/b.jpg", "owner_type": "post", "owner_id": "p1", "position": 1})

    sha256 = "abc123" + "0" * 58

    # Mark first as downloaded
    dup_id = await repo.mark_downloaded(r1["id"], sha256, "/path/to/file.jpg")
    assert dup_id is None  # First time — not a dup

    # Mark second with same SHA-256 — should return existing media_id
    dup_id2 = await repo.mark_downloaded(r2["id"], sha256, "/path/to/file.jpg")
    assert dup_id2 == r1["id"]  # Dedup: points to first asset


# ---------------------------------------------------------------------------
# CheckpointRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checkpoint_save_and_load(layout):
    repo = CheckpointRepo(layout)
    checkpoint = {
        "run_id": "run-001",
        "group_id": "grp-001",
        "mode": "full",
        "last_post_id": "post-050",
        "consecutive_known_posts": 5,
    }
    await repo.save("testgroup", "full", checkpoint)
    loaded = await repo.load("testgroup", "full")
    assert loaded["last_post_id"] == "post-050"
    assert loaded["consecutive_known_posts"] == 5
    assert loaded["updated_at"]  # timestamp added


@pytest.mark.asyncio
async def test_checkpoint_load_none_if_missing(layout):
    repo = CheckpointRepo(layout)
    result = await repo.load("nonexistent", "full")
    assert result is None


@pytest.mark.asyncio
async def test_checkpoint_clear(layout):
    repo = CheckpointRepo(layout)
    await repo.save("g1", "full", {"data": "x"})
    await repo.clear("g1", "full")
    assert await repo.load("g1", "full") is None


# ---------------------------------------------------------------------------
# RunRepo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_repo_create_and_finish(layout):
    repo = RunRepo(layout)
    run = await repo.create("run-abc", "testgroup", "grp-001", "full")
    assert run["status"] == "running"
    assert run["posts_found"] == 0

    await repo.finish("run-abc", "complete")
    loaded = await repo.get("run-abc")
    assert loaded["status"] == "complete"
    assert loaded["finished_at"] is not None
