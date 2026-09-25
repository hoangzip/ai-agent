# ARCHITECTURE.md
# Facebook Group Data Collector — System Architecture

> **Phase 01 — Architecture Review**
> Source of truth: Facebook_Group_Collector_Performance_First_Spec.docx
> Status: DRAFT — awaiting review before coding begins

---

## 1. Goals & Non-Goals

### Goals
- Collect posts, comments, replies, actors, and media from Facebook Groups
- Support **full crawl**, **incremental crawl**, **deep crawl**, and **refresh/revisit** modes
- Idempotent: re-running the same group must not produce duplicates
- Resumable: safe to kill and restart from checkpoint
- Observable: CLI/log shows throughput, queue depth, error counts at all times
- Performance-first: browser time is the bottleneck — all other workers must not block it

### Non-Goals (Phase 01)
- No frontend / dashboard (MVP)
- No bypass of CAPTCHA, MFA, or Facebook checkpoint
- No private/internal Facebook API dependency
- No OCR in Phase 01 (planned for Phase 13)

---

## 2. High-Level System Diagram

```
+------------------------------------------------------------------+
|                        CLI / main.py                              |
|   Input: Group URL or Group ID + mode (full/incremental/refresh) |
+------------------+-----------------------------------------------+
                   |
                   v
+------------------------------------------------------------------+
|                   Orchestrator / Scheduler                        |
|  - Load config (crawler.yaml)                                     |
|  - Init crawl_run record                                          |
|  - Load checkpoint (if resuming)                                  |
|  - Decide crawl mode                                              |
|  - Manage worker lifecycle + graceful shutdown                    |
+------+------------------+-------------------+--------------------+
       |                  |                   |
       v                  v                   v
+-------------+  +--------------+  +-----------------+
| Browser     |  | Comment      |  | Media           |
| Producer    |  | Workers (N)  |  | Download Workers|
| (Feed +     |  |              |  | (N)             |
|  Post page) |  |              |  |                 |
+------+------+  +------+-------+  +--------+--------+
       |  push           |  consume           |  consume
       v                 v                    v
+----------------------------------------------------------------+
|                   Bounded In-Process Queues                     |
|  post_queue(2000) | comment_queue(5000) | media_queue(5000)    |
+----------------------------------------------------------------+
                   |
                   v
+------------------------------------------------------------------+
|              DB Writer Workers (batch flush)                      |
|  posts_batch:500 | comments_batch:1000 | actors_batch:500       |
|  flush_ms: 1500                                                   |
+------------------------------------------------------------------+
                   |
                   v
+------------------------------------------------------------------+
|              PostgreSQL (asyncpg / SQLAlchemy async)             |
|  Migrations managed by Alembic                                    |
+------------------------------------------------------------------+
```

---

## 3. Component Breakdown

### 3.1 Browser Producer
- Uses **Playwright** (async) with persistent browser storage state
- Scrolls the group feed; extracts post metadata without waiting for DB or media
- Pushes `PostDiscoveredItem` into `post_queue`
- Applies backpressure: pauses scrolling when `post_queue` is full (bounded queue)
- Selectors isolated in `collector/facebook/selectors.py`

### 3.2 Post/Comment Workers
- Consume from `post_queue`; decide action:
  - `FULL_CRAWL` -> open post URL, extract all comments/replies
  - `REFRESH_COMMENTS` -> open post, extract delta comments only
  - `SKIP` -> post known, no refresh signal
- Push `CommentItem` into `comment_queue`
- Push `MediaJobItem` into `media_queue` (URL only, no binary)
- Never wait for DB writes

### 3.3 DB Writer Workers
- Consume from `post_queue` and `comment_queue`
- Batch upsert using PostgreSQL `ON CONFLICT DO UPDATE`
- Flush on batch size OR flush_ms timeout
- In-memory dedupe cache (current run)

### 3.4 Media Download Workers
- Consume from `media_queue`
- Download file -> compute SHA-256 -> dedupe against DB
- Store file to local SSD (MVP) with path in `storage_uri`
- Set `ocr_status = pending` after download (OCR handled by separate worker, Phase 13)

### 3.5 Checkpoint Manager
- Writes progress snapshot to `crawl_checkpoints` table
- Triggers every `checkpoint.every_posts` (20) or `checkpoint.every_seconds` (15)
- On resume: reads last checkpoint, restores cursor position

### 3.6 Metrics Emitter
- No external dashboard in MVP
- Logs structured JSON stats to stdout / log file every N seconds:
  - posts_discovered, posts_new, posts/sec
  - comments_discovered, comments_new, comments/sec
  - media_discovered, media_downloaded, media/sec
  - queue depths, error count, retry count, memory RSS

---

## 4. Crawl Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| `full` | First crawl of a group | Scroll all feed; full crawl each post |
| `incremental` | Subsequent crawl | Stop after N consecutive known posts; delta comments only |
| `deep` | Scheduled / manual | Re-visit DISCOVERED posts missing comments/media |
| `refresh` | Scheduled / revisit | Delta comment check on known posts per revisit schedule |

---

## 5. Authentication Strategy

- **Manual login** once via Playwright headed browser
- Browser storage state saved to `data/browser_state/` (gitignored)
- On subsequent runs: load storage state (headless OK)
- If session expires / checkpoint / MFA detected -> set `crawl_run.status = BLOCKED_AUTH`, flush checkpoint, halt cleanly
- Auth state NEVER committed to git

---

## 6. Error Handling Philosophy

- Retry per-post/comment with exponential backoff + jitter; max 3 retries
- One failing post/comment does NOT crash the run
- DOM drift / selector miss -> fail explicitly, mark post `PARTIAL`; never silently write wrong data
- On shutdown signal (SIGTERM/SIGINT): flush queues, write checkpoint, close browser, exit 0

---

## 7. Technology Stack

| Component | Technology |
|-----------|-----------|
| Browser automation | Playwright (Python, async) |
| Async runtime | Python asyncio |
| Database | PostgreSQL 15+ |
| DB driver | asyncpg / SQLAlchemy 2.x async |
| Migrations | Alembic |
| Config | PyYAML (`config/crawler.yaml`) |
| Logging | Python `structlog` (JSON format) |
| Dedup bloom filter (optional scale) | Redis + pybloom-live |
| OCR (Phase 13) | Tesseract / EasyOCR (separate worker) |
| Packaging | `pyproject.toml` + `requirements.txt` |

---

## 8. Project Structure

```
facebook-group-collector/
+-- collector/
|   +-- facebook/
|   |   +-- browser.py        # Playwright session management
|   |   +-- group.py          # Group metadata extraction
|   |   +-- feed.py           # Feed scrolling + post discovery
|   |   +-- post.py           # Post detail extraction
|   |   +-- comments.py       # Comment/reply tree extraction
|   |   +-- media.py          # Media URL detection
|   |   +-- selectors.py      # ALL CSS/XPath selectors (single source)
|   +-- pipeline/
|   |   +-- queues.py         # Bounded asyncio.Queue wrappers
|   |   +-- normalizer.py     # Raw DOM -> internal item schema
|   |   +-- dedupe.py         # In-memory + DB dedupe logic
|   |   +-- backpressure.py   # Queue full -> producer pause
|   +-- writers/
|   |   +-- batch_writer.py   # Generic batch DB writer
|   |   +-- upsert.py         # PostgreSQL UPSERT helpers
|   +-- downloaders/
|   |   +-- media_downloader.py
|   +-- storage/
|   |   +-- local_storage.py  # File system storage (MVP)
|   +-- models/
|   |   +-- db_models.py      # SQLAlchemy ORM models
|   +-- checkpoints/
|   |   +-- checkpoint_manager.py
|   +-- metrics/
|       +-- emitter.py
+-- config/
|   +-- crawler.yaml          # All tunable params (no hard-codes)
+-- tests/
|   +-- unit/
|   +-- integration/
+-- migrations/               # Alembic migrations
+-- data/
|   +-- browser_state/        # gitignored -- auth state
|   +-- media/                # gitignored -- downloaded files
+-- main.py                   # CLI entrypoint
+-- docker-compose.yml        # PostgreSQL dev setup
+-- .env.example
+-- .gitignore
+-- README.md
```

---

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Bounded queues with backpressure | Prevent OOM; naturally throttle browser when DB is slow |
| Browser never waits for DB | Browser time is most expensive; must not be blocked |
| Batch writes only | Row-by-row inserts are too slow at scale |
| Selectors in one file | DOM drift fix requires touching only one file |
| SHA-256 for media dedup | Reuse same asset across multiple owners; avoid re-OCR |
| Idempotent upsert by Facebook ID | Primary dedup key; fallback to canonical URL hash |
| Checkpoint every 20 posts or 15s | Granular enough to minimize re-work on resume |

---

## 10. Phase 01 Acceptance Criteria

- [ ] Data model reviewed and approved (DATA_MODEL.md)
- [ ] Pipeline design reviewed (PIPELINE_DESIGN.md)
- [ ] Unique keys and indexes defined (DATABASE_STRATEGY.md)
- [ ] Idempotency strategy confirmed (DATA_MODEL.md)
- [ ] Crawl strategy reviewed (CRAWL_STRATEGY.md)
- [ ] Performance strategy reviewed (PERFORMANCE_STRATEGY.md)
- [ ] Benchmark plan reviewed (BENCHMARK_PLAN.md)
- [ ] Implementation plan reviewed (IMPLEMENTATION_PLAN.md)

**No production code is written until all 8 documents are reviewed and approved.**
