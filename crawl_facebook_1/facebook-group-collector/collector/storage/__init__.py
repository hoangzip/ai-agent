"""
collector/storage — File-based JSON storage layer.

Replaces PostgreSQL in MVP. Same data model and idempotency semantics.
Migrate to PostgreSQL by swapping repository.py implementations.

Layout:
    data/
    ├── groups/{slug}/
    │   ├── meta.json
    │   ├── posts/{post_id}.json
    │   └── actors/{actor_id}.json
    ├── comments/{post_id}/{comment_id}.json
    ├── media/assets/{sha[:2]}/{sha[2:4]}/{sha}.ext
    ├── media/meta/{media_id}.json
    ├── runs/{run_id}.json
    ├── checkpoints/{group_slug}_{mode}.json
    └── index/
        ├── posts_{slug}.json       ← fb_post_id → internal post_id
        ├── comments_{post_id}.json ← fb_comment_id → internal comment_id
        ├── actors_{slug}.json      ← profile_url → internal actor_id
        └── media_sha256.json       ← sha256 → media_id
"""
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

__all__ = [
    "StorageLayout",
    "slugify",
    "GroupRepo",
    "ActorRepo",
    "PostRepo",
    "CommentRepo",
    "MediaRepo",
    "RunRepo",
    "CheckpointRepo",
]
