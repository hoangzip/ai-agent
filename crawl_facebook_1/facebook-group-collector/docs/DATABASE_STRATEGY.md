# DATABASE_STRATEGY.md
# Facebook Group Data Collector — Database Strategy

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Database Choice: PostgreSQL 15+

**Rationale:**
- Native UUID support (`gen_random_uuid()`)
- JSONB for raw payloads with GIN indexing
- `INSERT ... ON CONFLICT DO UPDATE` (UPSERT) — required for idempotency
- Partial indexes (`WHERE col IS NOT NULL`) — efficient nullable unique constraints
- `asyncpg` driver for high-performance async Python access
- Alembic for migration management

---

## 2. Connection Strategy

```yaml
# config/crawler.yaml
database:
  url: "postgresql+asyncpg://user:pass@localhost:5432/fb_collector"
  pool_min: 5
  pool_max: 20
  command_timeout_sec: 30
  statement_timeout_ms: 10000
```

**Pool sizing formula:**
```
pool_max = (comment_workers + db_writers + media_workers) * 2 + 5 (headroom)
# Default: (2 + 2 + 6) * 2 + 5 = 25 -> set pool_max=20 conservatively
```

---

## 3. Migration Strategy (Alembic)

```
migrations/
    env.py
    versions/
        001_initial_schema.py      # All 9 tables
        002_add_indexes.py         # All performance indexes
        003_add_partial_indexes.py # Unique WHERE NOT NULL
```

**Rules:**
- Every schema change requires a new Alembic migration
- Migrations are reversible (downgrade function always implemented)
- Production migration applied with `alembic upgrade head`
- Development: `alembic upgrade head` in docker-compose startup

---

## 4. Index Strategy

### 4.1 Primary Unique Constraints (Idempotency)

```sql
-- facebook_groups
CREATE UNIQUE INDEX idx_groups_fb_id ON facebook_groups(facebook_group_id)
    WHERE facebook_group_id IS NOT NULL;
CREATE UNIQUE INDEX idx_groups_url ON facebook_groups(group_url);

-- facebook_actors
CREATE UNIQUE INDEX idx_actors_fb_user_id ON facebook_actors(facebook_user_id)
    WHERE facebook_user_id IS NOT NULL;
CREATE UNIQUE INDEX idx_actors_profile_url ON facebook_actors(profile_url)
    WHERE profile_url IS NOT NULL;

-- facebook_posts
CREATE UNIQUE INDEX idx_posts_fb_post_id ON facebook_posts(facebook_post_id)
    WHERE facebook_post_id IS NOT NULL;
CREATE UNIQUE INDEX idx_posts_url ON facebook_posts(post_url)
    WHERE post_url IS NOT NULL;

-- facebook_comments
CREATE UNIQUE INDEX idx_comments_fb_id ON facebook_comments(facebook_comment_id)
    WHERE facebook_comment_id IS NOT NULL;
CREATE UNIQUE INDEX idx_comments_dedupe_key ON facebook_comments(dedupe_key)
    WHERE dedupe_key IS NOT NULL;

-- media_assets
CREATE UNIQUE INDEX idx_media_sha256 ON media_assets(sha256)
    WHERE sha256 IS NOT NULL;

-- content_media
CREATE UNIQUE INDEX idx_content_media_owner_pos ON content_media(owner_type, owner_id, position);
```

### 4.2 Performance Indexes (Query Patterns)

```sql
-- Feed order + crawl status queries
CREATE INDEX idx_posts_group_posted ON facebook_posts(group_id, posted_at DESC);
CREATE INDEX idx_posts_status_check ON facebook_posts(crawl_status, next_check_at)
    WHERE crawl_status IN ('REFRESH_DUE', 'PARTIAL', 'DISCOVERED');

-- Incremental crawl: find known posts in group
CREATE INDEX idx_posts_group_status ON facebook_posts(group_id, crawl_status);

-- Comment tree traversal
CREATE INDEX idx_comments_post_depth ON facebook_comments(post_id, depth, commented_at);
CREATE INDEX idx_comments_parent ON facebook_comments(parent_comment_id)
    WHERE parent_comment_id IS NOT NULL;

-- Media worker queue
CREATE INDEX idx_media_download_status ON media_assets(download_status)
    WHERE download_status IN ('pending', 'error');
CREATE INDEX idx_media_ocr_status ON media_assets(ocr_status)
    WHERE ocr_status = 'pending';

-- Lookup by source URL (avoid re-download)
CREATE INDEX idx_media_source_url ON media_assets(source_url);

-- Content media: reverse lookup
CREATE INDEX idx_content_media_media_id ON content_media(media_id);
CREATE INDEX idx_content_media_owner ON content_media(owner_type, owner_id);

-- Crawl job scheduler
CREATE INDEX idx_jobs_status_priority ON crawl_jobs(status, priority DESC, scheduled_at)
    WHERE status = 'pending';
```

---

## 5. UPSERT Patterns

### 5.1 Post Upsert

```sql
-- Primary: upsert on facebook_post_id
INSERT INTO facebook_posts (
    id, facebook_post_id, group_id, author_id, post_url,
    title, content, posted_at, content_hash,
    first_seen_at, last_seen_at, source_comment_count, crawl_status
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
ON CONFLICT (facebook_post_id) WHERE facebook_post_id IS NOT NULL
DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    source_comment_count = EXCLUDED.source_comment_count,
    updated_at = NOW()
WHERE facebook_posts.last_seen_at < EXCLUDED.last_seen_at;

-- Fallback: upsert on post_url
INSERT INTO facebook_posts (...) VALUES (...)
ON CONFLICT (post_url) WHERE post_url IS NOT NULL
DO UPDATE SET ...;
```

### 5.2 Comment Upsert

```sql
-- Primary: upsert on facebook_comment_id
INSERT INTO facebook_comments (
    id, facebook_comment_id, post_id, parent_comment_id,
    author_id, content, commented_at, depth, dedupe_key,
    first_seen_at, last_seen_at
)
VALUES (...)
ON CONFLICT (facebook_comment_id) WHERE facebook_comment_id IS NOT NULL
DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    known_reply_count = EXCLUDED.known_reply_count,
    updated_at = NOW();

-- Fallback: upsert on dedupe_key
INSERT INTO facebook_comments (...) VALUES (...)
ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL
DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at;
```

### 5.3 Actor Upsert

```sql
INSERT INTO facebook_actors (
    id, facebook_user_id, username, display_name, profile_url,
    first_seen_at, last_seen_at
)
VALUES (...)
ON CONFLICT (facebook_user_id) WHERE facebook_user_id IS NOT NULL
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    last_seen_at = EXCLUDED.last_seen_at,
    updated_at = NOW();
```

---

## 6. Batch Write Implementation

All writes use `asyncpg` executemany for batch efficiency:

```python
async def batch_upsert_posts(pool: asyncpg.Pool, posts: list[dict]):
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO facebook_posts (id, facebook_post_id, group_id, ...)
            VALUES ($1, $2, $3, ...)
            ON CONFLICT (facebook_post_id) WHERE facebook_post_id IS NOT NULL
            DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at, ...
            """,
            [(p["id"], p["facebook_post_id"], p["group_id"], ...) for p in posts]
        )
```

**Alternative for large batches:** Use `COPY` protocol for pure inserts (no conflict handling). Use for initial bulk load if dedup is pre-handled in Python.

---

## 7. Database Schema SQL (Reference)

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- facebook_groups
CREATE TABLE facebook_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facebook_group_id TEXT,
    group_name TEXT NOT NULL,
    group_url TEXT NOT NULL,
    description TEXT,
    member_count INTEGER,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- facebook_actors
CREATE TABLE facebook_actors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facebook_user_id TEXT,
    username TEXT,
    display_name TEXT,
    profile_url TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- facebook_posts
CREATE TABLE facebook_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facebook_post_id TEXT,
    group_id UUID NOT NULL REFERENCES facebook_groups(id),
    author_id UUID REFERENCES facebook_actors(id),
    post_url TEXT,
    title TEXT,
    title_source TEXT CHECK (title_source IN ('facebook', 'derived')),
    content TEXT,
    posted_at TIMESTAMPTZ,
    content_hash TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_crawled_at TIMESTAMPTZ,
    last_comments_crawled_at TIMESTAMPTZ,
    known_comment_count INTEGER NOT NULL DEFAULT 0,
    source_comment_count INTEGER,
    last_comment_at TIMESTAMPTZ,
    last_seen_comment_id TEXT,
    comments_complete BOOLEAN NOT NULL DEFAULT FALSE,
    next_check_at TIMESTAMPTZ,
    crawl_status TEXT NOT NULL DEFAULT 'DISCOVERED'
        CHECK (crawl_status IN ('DISCOVERED','CRAWLING','COMPLETE','PARTIAL','REFRESH_DUE','FAILED')),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- facebook_comments
CREATE TABLE facebook_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facebook_comment_id TEXT,
    post_id UUID NOT NULL REFERENCES facebook_posts(id),
    parent_comment_id UUID REFERENCES facebook_comments(id),
    author_id UUID REFERENCES facebook_actors(id),
    comment_url TEXT,
    content TEXT,
    commented_at TIMESTAMPTZ,
    depth INTEGER NOT NULL DEFAULT 0,
    dedupe_key TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    known_reply_count INTEGER,
    last_reply_at TIMESTAMPTZ,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- media_assets
CREATE TABLE media_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video', 'document')),
    source_url TEXT NOT NULL,
    storage_uri TEXT,
    sha256 TEXT,
    mime_type TEXT,
    file_size BIGINT,
    width INTEGER,
    height INTEGER,
    download_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_status IN ('pending', 'downloading', 'downloaded', 'error')),
    ocr_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (ocr_status IN ('pending', 'processing', 'done', 'error', 'skipped')),
    ocr_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- content_media
CREATE TABLE content_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type TEXT NOT NULL CHECK (owner_type IN ('post', 'comment')),
    owner_id UUID NOT NULL,
    media_id UUID NOT NULL REFERENCES media_assets(id),
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- crawl_runs
CREATE TABLE crawl_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES facebook_groups(id),
    mode TEXT NOT NULL CHECK (mode IN ('full', 'incremental', 'deep', 'refresh')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'complete', 'partial', 'blocked_auth', 'failed')),
    posts_found INTEGER NOT NULL DEFAULT 0,
    posts_new INTEGER NOT NULL DEFAULT 0,
    comments_found INTEGER NOT NULL DEFAULT 0,
    comments_new INTEGER NOT NULL DEFAULT 0,
    media_found INTEGER NOT NULL DEFAULT 0,
    media_downloaded INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- crawl_jobs
CREATE TABLE crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES crawl_runs(id),
    job_type TEXT NOT NULL CHECK (job_type IN (
        'FULL_POST_CRAWL', 'REFRESH_POST_COMMENTS', 'DEEP_POST_CRAWL',
        'MEDIA_DOWNLOAD', 'LOW_PRIORITY_REVISIT'
    )),
    post_id UUID REFERENCES facebook_posts(id),
    priority INTEGER NOT NULL DEFAULT 50,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed', 'skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- crawl_checkpoints
CREATE TABLE crawl_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES crawl_runs(id),
    group_id UUID NOT NULL REFERENCES facebook_groups(id),
    mode TEXT NOT NULL,
    last_post_id UUID REFERENCES facebook_posts(id),
    last_post_time TIMESTAMPTZ,
    consecutive_known_posts INTEGER NOT NULL DEFAULT 0,
    progress_snapshot JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 8. Phase 01 Acceptance Criteria

- [ ] All 9 tables defined with correct types and constraints
- [ ] All UNIQUE indexes identified (partial WHERE IS NOT NULL)
- [ ] All performance indexes defined for known query patterns
- [ ] UPSERT patterns defined for all entity types
- [ ] Batch write mechanism reviewed
- [ ] Migration strategy (Alembic) confirmed
- [ ] Connection pool sizing formula reviewed
- [ ] No binary data stored in PostgreSQL (storage_uri only)
