# DATA_MODEL.md
# Facebook Group Data Collector — Data Model

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Overview

All Facebook-sourced identifiers are **nullable** because Facebook does not always expose IDs in the DOM. Internal UUIDs are always the primary keys. Idempotency is guaranteed by unique constraints on Facebook IDs or fallback dedupe keys.

---

## 2. Entity Relationship Diagram

```
facebook_groups (1)
    |
    +--< facebook_posts (N)
    |         |
    |         +--< facebook_comments (N, tree via parent_comment_id)
    |         |         |
    |         |         +--< content_media (N)
    |         |
    |         +--< content_media (N)
    |
    +--< crawl_runs (N)
              |
              +--< crawl_jobs (N)
              +--< crawl_checkpoints (N)

facebook_actors (1) <--- facebook_posts (N)  [author]
facebook_actors (1) <--- facebook_comments (N) [author]

media_assets (1) <--- content_media (N) [many-to-many bridge]
```

---

## 3. Table Definitions

### 3.1 `facebook_groups`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK, default gen_random_uuid() | Internal primary key |
| facebook_group_id | TEXT | UNIQUE, nullable | Facebook Group ID; null if not extractable |
| group_name | TEXT | NOT NULL | Group display name |
| group_url | TEXT | UNIQUE NOT NULL | Canonical group URL (normalized) |
| description | TEXT | nullable | Group description if available |
| member_count | INTEGER | nullable | Member count if visible |
| first_seen_at | TIMESTAMPTZ | NOT NULL | First time this group was seen |
| last_seen_at | TIMESTAMPTZ | NOT NULL | Most recent crawl that saw this group |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | DB record creation |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | DB record last update |

**Indexes:**
- `UNIQUE (facebook_group_id)` where facebook_group_id IS NOT NULL
- `UNIQUE (group_url)`

**Idempotency:** UPSERT on `facebook_group_id` if available; fallback UPSERT on `group_url`.

---

### 3.2 `facebook_actors`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | Internal primary key |
| facebook_user_id | TEXT | UNIQUE, nullable | Facebook User/Page ID; null if not in DOM |
| username | TEXT | nullable | Username/slug from profile URL |
| display_name | TEXT | nullable | Display name as shown in post/comment |
| profile_url | TEXT | UNIQUE, nullable | Canonical profile URL |
| first_seen_at | TIMESTAMPTZ | NOT NULL | |
| last_seen_at | TIMESTAMPTZ | NOT NULL | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:**
- `UNIQUE (facebook_user_id)` where NOT NULL
- `UNIQUE (profile_url)` where NOT NULL
- `INDEX (username)`

**Idempotency:**
1. Primary: UPSERT on `facebook_user_id`
2. Fallback: UPSERT on `profile_url`
3. Last resort: UPSERT on `username` (if profile_url absent)

---

### 3.3 `facebook_posts`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | Internal primary key |
| facebook_post_id | TEXT | UNIQUE, nullable | Facebook Post ID if extractable |
| group_id | UUID | FK -> facebook_groups.id, NOT NULL | |
| author_id | UUID | FK -> facebook_actors.id, nullable | |
| post_url | TEXT | UNIQUE, nullable | Permalink |
| title | TEXT | nullable | Facebook title or derived |
| title_source | TEXT | nullable | `facebook` or `derived` |
| content | TEXT | nullable | Post text content |
| posted_at | TIMESTAMPTZ | nullable | When post was made |
| content_hash | TEXT | nullable | SHA-256 of content for change detection |
| first_seen_at | TIMESTAMPTZ | NOT NULL | |
| last_seen_at | TIMESTAMPTZ | NOT NULL | |
| last_crawled_at | TIMESTAMPTZ | nullable | Last time this post page was crawled |
| last_comments_crawled_at | TIMESTAMPTZ | nullable | Last time comments were crawled |
| known_comment_count | INTEGER | NOT NULL, default 0 | Comments we have in DB |
| source_comment_count | INTEGER | nullable | Comment count shown in Facebook UI |
| last_comment_at | TIMESTAMPTZ | nullable | Timestamp of newest comment we have |
| last_seen_comment_id | TEXT | nullable | FB comment ID of newest seen comment |
| comments_complete | BOOLEAN | NOT NULL, default false | All visible comments fetched on last crawl |
| next_check_at | TIMESTAMPTZ | nullable | Scheduled revisit time |
| crawl_status | TEXT | NOT NULL, default 'DISCOVERED' | See enum below |
| raw_payload | JSONB | nullable | Normalized raw payload if useful |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

**crawl_status enum:** `DISCOVERED`, `CRAWLING`, `COMPLETE`, `PARTIAL`, `REFRESH_DUE`, `FAILED`

**Indexes:**
- `UNIQUE (facebook_post_id)` where NOT NULL
- `UNIQUE (post_url)` where NOT NULL
- `INDEX (group_id, posted_at DESC)` — feed order queries
- `INDEX (crawl_status, next_check_at)` — scheduler queries
- `INDEX (group_id, crawl_status)` — incremental mode

**Idempotency:**
1. Primary: UPSERT on `facebook_post_id`
2. Fallback: UPSERT on `post_url`

---

### 3.4 `facebook_comments`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | Internal primary key |
| facebook_comment_id | TEXT | UNIQUE, nullable | FB Comment ID if extractable |
| post_id | UUID | FK -> facebook_posts.id, NOT NULL | |
| parent_comment_id | UUID | FK -> facebook_comments.id, nullable | NULL = top-level comment |
| author_id | UUID | FK -> facebook_actors.id, nullable | |
| comment_url | TEXT | nullable | Permalink if available |
| content | TEXT | nullable | Comment/reply text |
| commented_at | TIMESTAMPTZ | nullable | When comment was made |
| depth | INTEGER | NOT NULL, default 0 | 0 = top-level comment; 1+ = reply |
| dedupe_key | TEXT | UNIQUE, nullable | Fallback: hash(post_id+profile_url+normalized_text+commented_at) |
| first_seen_at | TIMESTAMPTZ | NOT NULL | |
| last_seen_at | TIMESTAMPTZ | NOT NULL | |
| known_reply_count | INTEGER | nullable | Reply count from UI if available |
| last_reply_at | TIMESTAMPTZ | nullable | If determinable |
| raw_payload | JSONB | nullable | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:**
- `UNIQUE (facebook_comment_id)` where NOT NULL
- `UNIQUE (dedupe_key)` where NOT NULL
- `INDEX (post_id, depth, commented_at)` — tree query
- `INDEX (post_id, facebook_comment_id)` — delta detection

**Idempotency:**
1. Primary: UPSERT on `facebook_comment_id`
2. Fallback: UPSERT on `dedupe_key` = hash(post_id + profile_url + normalized_text + commented_at)

> **IMPORTANT:** `dedupe_key` is an internal fallback hash. It is NEVER stored in `facebook_comment_id`. Do not conflate internal hashes with Facebook IDs.

---

### 3.5 `media_assets`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| media_type | TEXT | NOT NULL | `image`, `video` (MVP: image priority) |
| source_url | TEXT | NOT NULL | Original URL discovered by browser |
| storage_uri | TEXT | nullable | Local path or object storage URI after download |
| sha256 | TEXT | UNIQUE, nullable | File hash; set after download; enables dedup |
| mime_type | TEXT | nullable | e.g. `image/jpeg` |
| file_size | BIGINT | nullable | Bytes |
| width | INTEGER | nullable | |
| height | INTEGER | nullable | |
| download_status | TEXT | NOT NULL, default 'pending' | `pending`, `downloading`, `downloaded`, `error` |
| ocr_status | TEXT | NOT NULL, default 'pending' | `pending`, `processing`, `done`, `error` (Phase 13) |
| ocr_text | TEXT | nullable | OCR output (Phase 13) |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:**
- `UNIQUE (sha256)` where NOT NULL — file-level dedup
- `INDEX (download_status)` — worker queue
- `INDEX (ocr_status)` — OCR worker queue (Phase 13)
- `INDEX (source_url)` — lookup by URL

**Storage:** Binary files stored on local SSD (MVP) or object storage (scale). PostgreSQL stores only metadata + `storage_uri`.

---

### 3.6 `content_media` (bridge table)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| owner_type | TEXT | NOT NULL | `post` or `comment` |
| owner_id | UUID | NOT NULL | UUID of the post or comment |
| media_id | UUID | FK -> media_assets.id, NOT NULL | |
| position | INTEGER | NOT NULL | Order of image in content (0-indexed) |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:**
- `UNIQUE (owner_type, owner_id, position)` — prevent duplicate position
- `INDEX (owner_type, owner_id)` — fetch all media for a post/comment
- `INDEX (media_id)` — reverse lookup

---

### 3.7 `crawl_runs`

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| group_id | UUID | FK -> facebook_groups.id |
| mode | TEXT | `full`, `incremental`, `deep`, `refresh` |
| started_at | TIMESTAMPTZ | |
| finished_at | TIMESTAMPTZ | nullable |
| status | TEXT | `running`, `complete`, `partial`, `blocked_auth`, `failed` |
| posts_found | INTEGER | default 0 |
| posts_new | INTEGER | default 0 |
| comments_found | INTEGER | default 0 |
| comments_new | INTEGER | default 0 |
| media_found | INTEGER | default 0 |
| media_downloaded | INTEGER | default 0 |
| error_message | TEXT | nullable |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

### 3.8 `crawl_jobs`

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| run_id | UUID | FK -> crawl_runs.id |
| job_type | TEXT | `FULL_POST_CRAWL`, `REFRESH_POST_COMMENTS`, `DEEP_POST_CRAWL`, `MEDIA_DOWNLOAD`, `LOW_PRIORITY_REVISIT` |
| post_id | UUID | FK -> facebook_posts.id, nullable |
| priority | INTEGER | 100=highest (see job priority table) |
| scheduled_at | TIMESTAMPTZ | When job should be picked up |
| started_at | TIMESTAMPTZ | nullable |
| finished_at | TIMESTAMPTZ | nullable |
| status | TEXT | `pending`, `running`, `done`, `failed`, `skipped` |
| attempts | INTEGER | default 0 |
| last_error | TEXT | nullable |
| created_at | TIMESTAMPTZ | |

**Job Priority Table:**

| Job type | Priority | Purpose |
|----------|----------|---------|
| FULL_POST_CRAWL | 100 | New post — highest priority |
| REFRESH_POST_COMMENTS | 70-90 | Known post with new activity signal |
| DEEP_POST_CRAWL | 50 | Fill in missing comments/media |
| MEDIA_DOWNLOAD | 40 | Download queued images |
| LOW_PRIORITY_REVISIT | 10-30 | Scheduled revisit of old posts |

---

### 3.9 `crawl_checkpoints`

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| run_id | UUID | FK -> crawl_runs.id, UNIQUE |
| group_id | UUID | FK -> facebook_groups.id |
| mode | TEXT | Crawl mode at time of checkpoint |
| last_post_id | UUID | nullable — last fully processed post |
| last_post_time | TIMESTAMPTZ | nullable — posted_at of last seen post |
| consecutive_known_posts | INTEGER | default 0 — for incremental stop condition |
| progress_snapshot | JSONB | Arbitrary progress state (cursor, feed position, etc.) |
| updated_at | TIMESTAMPTZ | |

---

## 4. Idempotency Summary

| Entity | Primary dedup key | Fallback dedup key |
|--------|------------------|--------------------|
| facebook_groups | facebook_group_id | group_url |
| facebook_actors | facebook_user_id | profile_url -> username |
| facebook_posts | facebook_post_id | post_url |
| facebook_comments | facebook_comment_id | dedupe_key (internal hash) |
| media_assets | sha256 (post-download) | source_url (pre-download) |

**Three-tier dedup strategy:**
1. In-memory cache (current run) — fastest, no DB round-trip
2. Optional Redis Bloom filter (scale) — sub-millisecond lookup
3. Database UNIQUE constraint + UPSERT — authoritative source of truth

---

## 5. Revisit Policy

| Post age | Default revisit interval |
|----------|------------------------|
| < 1 day | ~1 hour |
| 1-3 days | ~6 hours |
| 3-7 days | ~12 hours |
| 7-30 days | ~24 hours |
| 30-90 days | ~72 hours |
| > 90 days | ~7 days (configurable) |

These are **baseline values** stored in `config/crawler.yaml`. Must be configurable; not hard-coded.

---

## 6. Phase 01 Acceptance Criteria

- [ ] All tables defined with correct types and constraints
- [ ] All unique keys identified (no missing dedup paths)
- [ ] Fallback dedup keys do NOT contaminate facebook_*_id fields
- [ ] Revisit policy defined and configurable
- [ ] Storage strategy confirmed (no binary in PostgreSQL)
- [ ] All FK relationships correct and complete
