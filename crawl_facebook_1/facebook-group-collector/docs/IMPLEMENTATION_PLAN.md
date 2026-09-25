# IMPLEMENTATION_PLAN.md
# Facebook Group Data Collector — Implementation Plan

> **Phase 01 — Architecture Review**
> Status: DRAFT
>
> This document defines the vertical-slice implementation sequence.
> **Each phase must PASS before the next begins.**

---

## 0. Prerequisites

Before any coding:
- [ ] All 8 Phase 01 documents reviewed and approved
- [ ] PostgreSQL available (docker-compose up)
- [ ] Python 3.11+ environment
- [ ] Playwright installed (`playwright install chromium`)
- [ ] pyproject.toml and requirements.txt created

---

## Phase 02 — Async Producer-Consumer Infrastructure

**Duration estimate:** 1–2 days
**Deliverables:**
- `collector/pipeline/queues.py` — bounded `asyncio.Queue` wrappers
- `collector/pipeline/backpressure.py` — pause/resume logic
- Basic orchestrator skeleton in `main.py`
- Worker lifecycle: startup, graceful shutdown on SIGTERM/SIGINT
- Sentinel-based queue drain on shutdown
- Tests: queue bounded (put blocks at maxsize), sentinel drain, shutdown within 5s

**PASS criteria:**
- Queue blocks producer when full (backpressure verified)
- Workers exit cleanly on shutdown signal
- No sentinel leak; all workers terminate
- Unit tests PASS

---

## Phase 03 — Authenticated Browser Session

**Duration estimate:** 1 day
**Deliverables:**
- `collector/facebook/browser.py` — Playwright context factory
- `main.py auth` command — headed browser for manual login
- Session state save/load from `data/browser_state/` (gitignored)
- Auth status check (detect login redirect, checkpoint, MFA prompt)
- `BLOCKED_AUTH` halt with checkpoint flush

**PASS criteria:**
- Manual login → state saved to gitignored path
- Subsequent run loads state headless — no re-login
- Auth failure correctly detected and halts with `BLOCKED_AUTH`
- Auth state NOT in git
- Tests: auth detection logic tested with mocked page URLs

---

## Phase 04 — Group + Post Discovery

**Duration estimate:** 2–3 days
**Deliverables:**
- `collector/facebook/selectors.py` — all selectors (single source)
- `collector/facebook/group.py` — group metadata extraction
- `collector/facebook/feed.py` — feed scroll + post card extraction
- `collector/facebook/post.py` — post detail page extraction
- `collector/pipeline/normalizer.py` — raw DOM → `PostDiscoveredItem`
- Integration: browser pushes to `post_queue`

**PASS criteria:**
- Given Group URL or Group ID → correctly identifies group
- Scrolls feed; extracts ~100 posts with metadata
- `PostDiscoveredItem` fields populated correctly (nulls where FB doesn't expose)
- No data invented for missing fields
- Selector failures → `PARTIAL` status, not silent wrong data
- Manual inspection of 10 sample items confirms accuracy

---

## Phase 05 — Batch PostgreSQL Persistence

**Duration estimate:** 2 days
**Deliverables:**
- `migrations/versions/001_initial_schema.py` — all 9 tables
- `migrations/versions/002_indexes.py` — all indexes
- `collector/models/db_models.py` — SQLAlchemy models
- `collector/writers/batch_writer.py` — flush on size OR timeout
- `collector/writers/upsert.py` — UPSERT SQL for all entities
- Actor resolution: upsert actor before post (FK dependency)
- `docker-compose.yml` with PostgreSQL

**PASS criteria:**
- `alembic upgrade head` creates all tables and indexes
- 100 posts inserted in < 5 seconds (batch, not row-by-row)
- Re-running same 100 posts → 0 new rows (idempotent)
- No row-by-row inserts in hot path (verified by code review)
- Unit tests: batch flush on size, flush on timeout

---

## Phase 06 — Independent Comment Workers

**Duration estimate:** 2–3 days
**Deliverables:**
- `collector/facebook/comments.py` — comment/reply tree extraction
- Comment workers: consume from `post_queue`, push to `comment_queue`
- Action decision logic: `FULL_CRAWL` / `REFRESH_COMMENTS` / `SKIP`
- Reply tree extraction with `depth` tracking
- `parent_comment_id` correctly linked
- Comment batch persistence

**PASS criteria:**
- Feed does NOT wait for comment extraction (verified: browser continues scrolling)
- Comment tree extracted: top-level + replies with correct `depth`
- `parent_comment_id` links correctly
- Comments batch-upserted with idempotency
- 100-post benchmark: comments/sec metric captured

---

## Phase 07 — Independent Media Download Workers

**Duration estimate:** 2 days
**Deliverables:**
- `collector/facebook/media.py` — media URL detection in DOM
- `collector/downloaders/media_downloader.py` — async download + hash
- `collector/storage/local_storage.py` — file save with path structure
- SHA-256 dedup logic
- `content_media` mapping creation
- `ocr_status = pending` set after download

**PASS criteria:**
- Browser/Comment worker only pushes URL — never downloads
- Media worker downloads independently
- SHA-256 dedup: same file from different URLs stored once
- `content_media` mapping correct (owner_type, owner_id, position)
- `ocr_status = pending` set correctly (Phase 13 will pick up)
- Media NOT stored as binary in PostgreSQL

---

## Phase 08 — Deduplication

**Duration estimate:** 1–2 days
**Deliverables:**
- `collector/pipeline/dedupe.py` — in-memory cache + DB fallback
- Verified idempotency for all entity types

**PASS criteria:**
- Re-run same group → 0 new posts, 0 new comments, 0 new media
- In-memory cache correctly skips DB lookups for current-run duplicates
- Fallback to DB dedup works when cache misses
- No wrong data silently inserted

---

## Phase 09 — Checkpoint + Resume

**Duration estimate:** 1–2 days
**Deliverables:**
- `collector/checkpoints/checkpoint_manager.py`
- Checkpoint write: every 20 posts + every 15s + on shutdown
- Resume: load checkpoint, restore counter, re-use dedup to skip already-processed

**PASS criteria:**
- Kill process at post #50 → restart → continues from approximately post #50
- No duplicates after resume
- Final stats accurate (not double-counted from re-scanned items)
- Checkpoint written on SIGTERM within 2 seconds

---

## Phase 10 — Incremental Crawl + Revisit

**Duration estimate:** 2 days
**Deliverables:**
- Incremental mode: stop after 30 consecutive known posts
- Revisit schedule: `next_check_at` computed per post age
- REFRESH_COMMENTS action: delta comment extraction
- `crawl_status` state machine correct

**PASS criteria:**
- Incremental on already-crawled group → stops in < 2 minutes
- Stop count resets correctly when new content appears
- Revisit schedule computed correctly for posts of different ages
- REFRESH_COMMENTS: only new comments inserted, known comments skipped

---

## Phase 11 — Benchmark + Metrics

**Duration estimate:** 1–2 days
**Deliverables:**
- `collector/metrics/emitter.py` — periodic structured log output
- `main.py benchmark` command — runs 100-post test, produces report
- Timing instrumentation at all key points
- Full benchmark report as specified in BENCHMARK_PLAN.md

**PASS criteria:**
- Benchmark report produced with all metrics from BENCHMARK_PLAN.md Section 2.2
- All 6 benchmark scenarios from BENCHMARK_PLAN.md Section 5 run and documented
- Bottleneck identified (if any)
- Report committed to `docs/benchmark_results/` directory

---

## Phase 12 — Performance Tuning (data-driven only)

**Duration estimate:** 1–3 days (based on benchmark results)

**Approach:**
1. Read Phase 11 benchmark report
2. Identify the single largest bottleneck from BENCHMARK_PLAN.md decision table
3. Implement one optimization
4. Re-run benchmark
5. Compare delta
6. Repeat only if still below target throughput

**Examples of data-driven tuning:**
- If `browser.post_page_open > 3s`: try blocking non-essential resources
- If `db.batch_flush > 200ms`: try increasing batch size or using COPY
- If `comment_queue > 80%`: try increasing comment_workers

**PASS criteria:**
- Every tuning decision has a before/after benchmark result
- No "blind" changes to concurrency or batch sizes
- Throughput target: >3 posts/sec (posts with comments)

---

## Phase 13 — OCR Worker

**Duration estimate:** 1–2 days
**Deliverables:**
- `collector/workers/ocr_worker.py`
- Polls `media_assets WHERE ocr_status = 'pending' AND download_status = 'downloaded'`
- Runs OCR (Tesseract/EasyOCR) in separate process/executor
- Writes `ocr_text`, sets `ocr_status = 'done'`
- OCR NEVER blocks crawler or media downloader

**PASS criteria:**
- OCR runs independently; crawler throughput unchanged
- `ocr_status` transitions: `pending` → `processing` → `done` / `error`
- Failed OCR marked `error` with message; not retried infinitely

---

## Phase 14 — Long-Run Reliability (Soak Test)

**Duration estimate:** 3–5 days (including test run time)
**Deliverables:**
- Soak test script: 2+ hour full crawl on large group
- Memory profile over time
- Error rate analysis

**PASS criteria:**
- Memory RSS stable over 2+ hours (no unbounded growth)
- Error rate < 2% of items processed
- Checkpoint + resume works after simulated crash mid-soak
- No duplicate data after soak test

---

## Summary: Phase Completion Checklist

| Phase | Focus | Key PASS Criterion |
|-------|-------|-------------------|
| 01 | Architecture docs | All 8 docs reviewed ← **YOU ARE HERE** |
| 02 | Async queues | Bounded queues + graceful shutdown |
| 03 | Auth session | Manual login + session reuse + BLOCKED_AUTH |
| 04 | Post discovery | 100 posts discovered + normalized |
| 05 | DB persistence | Batch upsert; idempotent; no row-by-row |
| 06 | Comments | Feed doesn't wait; tree correct; batch |
| 07 | Media download | Async; SHA-256 dedup; no binary in PG |
| 08 | Deduplication | Re-run same group → 0 duplicates |
| 09 | Checkpoint | Kill → resume → no duplicates |
| 10 | Incremental | Stop at N known; delta comments only |
| 11 | Benchmark | Full report with bottleneck identified |
| 12 | Tuning | Data-driven; before/after benchmark |
| 13 | OCR | Async; doesn't block crawler |
| 14 | Soak test | Memory stable; error rate < 2% |

---

## Development Rules (from spec section 18)

1. **Correctness and observability before micro-optimization**
2. **No UI until backend is stable**
3. **No invented Facebook IDs or missing data**
4. **No private/internal APIs; no CAPTCHA bypass**
5. **No commit of auth state, cookies, tokens**
6. **Every change must have tests + doc/config update**
7. **No blind concurrency increase; always benchmark**
8. **DOM changes → fix selectors only; do not touch storage layer**
9. **End of each phase: report implemented, tests, benchmark (if any), known issues, next phase**
