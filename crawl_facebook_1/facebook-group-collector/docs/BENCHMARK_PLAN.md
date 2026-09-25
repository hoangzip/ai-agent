# BENCHMARK_PLAN.md
# Facebook Group Data Collector — Benchmark Plan

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Why Benchmark First?

The spec mandates: **"Chỉ tối ưu component thực sự là bottleneck."** (Only optimize the real bottleneck.)

We cannot know which component is the bottleneck without measurement. This plan defines:
1. What to measure
2. How to measure it repeatably
3. What the results tell us
4. What actions to take based on results

---

## 2. Mandatory Benchmark: 100 Posts

### 2.1 Definition of "Benchmark 100 Posts"

A reproducible test run that crawls exactly ~100 posts from a target Facebook Group, capturing timing data broken down by component.

**Target group:** A group with at least 500 posts and active comments. Use a group you control or have permission to crawl.

**Test conditions:**
- Fresh PostgreSQL database (clean state)
- Default config from `crawler.yaml` (no tuning applied yet)
- Single browser context (context_count=1)
- Comment workers: 2
- Media workers: 6
- DB writer batch size: 500 posts, 1000 comments
- Network: stable broadband (document baseline)
- Hardware: document CPU/RAM/SSD specs

### 2.2 What to Record

| Metric | Unit | Notes |
|--------|------|-------|
| Total elapsed time | seconds | Wall clock from start to 100 posts complete |
| Posts/sec | posts/sec | = 100 / total_elapsed |
| Comments discovered | count | Total comments seen |
| Comments new | count | Comments inserted |
| Comments/sec | comments/sec | |
| Media discovered | count | Media URLs found |
| Media downloaded | count | Files actually downloaded |
| Media/sec | files/sec | Download throughput |
| Browser DOM time | ms/post | Time Playwright spends per post (feed scroll + parse) |
| Comment extraction time | ms/post | Time to open post URL and extract all comments |
| DB write time | ms/batch | Time per batch flush |
| Media download time | ms/file | Average per file |
| Peak memory RSS | MB | Maximum memory usage during run |
| Peak post_queue depth | count | Max queue depth observed |
| Peak comment_queue depth | count | Max queue depth observed |
| Peak media_queue depth | count | Max queue depth observed |
| Error count | count | Total errors (not retries) |
| Retry count | count | Total retries (per-attempt) |

### 2.3 Timing Instrumentation Points

```python
# In browser producer (feed.py)
with timer("browser.feed_scroll_per_post"):
    post_item = await extract_post_card(element)

# In comment worker (comments.py)
with timer("browser.post_page_open"):
    await page.goto(post_url)

with timer("browser.comment_extraction"):
    comments = await extract_comments(page)

# In DB writer (batch_writer.py)
with timer("db.batch_flush_posts"):
    await batch_upsert_posts(pool, batch)

# In media worker (media_downloader.py)
with timer("media.download"):
    file_bytes = await http_client.get(url)

with timer("media.sha256"):
    sha256 = hashlib.sha256(file_bytes).hexdigest()

with timer("media.storage_write"):
    await local_storage.save(sha256, file_bytes)
```

---

## 3. Benchmark Output Format

After completing the benchmark run, the CLI produces a report:

```
============================================================
 BENCHMARK REPORT — Facebook Group Collector
============================================================
 Target Group : <group_name> (<group_id>)
 Mode         : full
 Crawl Date   : 2024-01-15 10:00:00 UTC
 Hardware     : MacBook Pro M3, 32GB RAM, 1TB SSD
 Config       : context_count=1, comment_workers=2, media_workers=6

 THROUGHPUT
 ----------
 Posts discovered       : 100
 Posts new              : 100
 Posts/sec              : 3.8
 Comments discovered    : 4,210
 Comments new           : 4,210
 Comments/sec           : 18.4
 Media discovered       : 830
 Media downloaded       : 798
 Media/sec              : 5.3

 TIMING BREAKDOWN (per post)
 ----------------------------
 Browser: feed scroll + parse : 180 ms/post (avg)
 Browser: post page open      : 2,100 ms/post (avg)
 Browser: comment extraction  : 1,800 ms/post (avg)   <-- LIKELY BOTTLENECK
 DB: batch flush (posts)      : 12 ms/batch
 DB: batch flush (comments)   : 28 ms/batch
 Media: download (per file)   : 890 ms/file
 Media: sha256 (per file)     : 2 ms/file
 Media: storage write         : 5 ms/file

 QUEUE DEPTHS (peak)
 -------------------
 post_queue    : 42 / 2000 (2%)   OK
 comment_queue : 830 / 5000 (17%) OK
 media_queue   : 1,201 / 5000 (24%) OK

 RELIABILITY
 -----------
 Errors        : 2
 Retries       : 5
 PARTIAL posts : 0
 FAILED posts  : 0

 RESOURCES
 ---------
 Peak memory RSS : 1,400 MB
 Elapsed time    : 00:26:21
============================================================
```

---

## 4. Benchmark Interpretation & Decision Table

| Finding | Diagnosis | Action |
|---------|-----------|--------|
| `browser.post_page_open > 3000 ms` avg | Page load is bottleneck | Try resource blocking (video/fonts) after verifying correctness |
| `browser.comment_extraction > 2000 ms` avg | DOM comment parsing is slow | Optimize selector queries; check for unnecessary `page.wait_for_selector` calls |
| `DB batch flush > 200 ms` avg | DB write is bottleneck | Check index health; try increasing batch size; check for lock contention |
| `post_queue consistently > 80%` full | DB/comment workers too slow | Increase db_writers or comment_workers (with caution) |
| `media_queue consistently > 80%` full | Media workers too slow | Increase media_workers |
| `Peak memory > 3 GB` | Possible queue/cache leak | Check queue maxsize; profile in-memory cache growth |
| `Error count > 5%` of items | DOM drift or network issue | Check selectors; investigate error logs |
| `comments/sec << posts/sec * avg_comments` | Comment extraction is a bottleneck | Profile comment_extraction time; check pagination |

**Rule:** Do NOT increase `context_count` or workers without first identifying the bottleneck from this table.

---

## 5. Benchmark Test Suite (Phase 11)

In Phase 11, after implementation is complete, run these benchmarks:

### 5.1 Baseline Full Crawl (100 posts)
- Mode: full
- Group: standard test group
- Config: defaults
- Expected: >3 posts/sec, <2GB memory

### 5.2 Incremental Crawl (after full)
- Mode: incremental
- Same group; crawl again immediately
- Expected: Stop after ~30 consecutive known posts in <60 seconds
- Expected: 0 new posts inserted (all known)

### 5.3 Deduplication Verification
- Mode: full on same group again
- Expected: 0 new posts, 0 new comments, 0 new media
- Expected: All items correctly skipped via dedupe

### 5.4 Comment Delta Detection
- Wait 1 hour; new comments added manually to test group
- Mode: refresh
- Expected: Only NEW comments inserted; known comments skipped

### 5.5 Checkpoint + Resume
- Start full crawl; kill process at post #50
- Restart with `--resume`
- Expected: Crawl continues from approximately post #50
- Expected: No duplicates in DB

### 5.6 Soak Test (Phase 14)
- Mode: full on a large group (>1000 posts)
- Duration: 2+ hours
- Expected: Memory RSS stable (no unbounded growth)
- Expected: Error rate < 2%

---

## 6. Benchmark Tooling

| Tool | Purpose |
|------|---------|
| Python `time.perf_counter()` | Precise timing within process |
| `psutil.Process().memory_info().rss` | Memory monitoring |
| Structured JSON logs | Machine-readable metrics export |
| `python -m cProfile` | CPU profiling when needed (Phase 12) |
| `asyncio.Queue.qsize()` | Queue depth monitoring |
| PostgreSQL `pg_stat_activity` | DB connection monitoring |
| PostgreSQL `EXPLAIN ANALYZE` | Query plan analysis when DB is bottleneck |

---

## 7. Benchmark Configuration Baseline

```yaml
# config/crawler.yaml — benchmark defaults
crawler:
  mode: full

browser:
  context_count: 1
  feed_pages: 1
  comment_pages: 2

workers:
  comment_workers: 2
  db_writers: 2
  media_workers: 6

queues:
  posts: 2000
  comments: 5000
  media: 5000

database:
  posts_batch: 500
  comments_batch: 1000
  actors_batch: 500
  media_batch: 500
  flush_ms: 1500

checkpoint:
  every_posts: 20
  every_seconds: 15

incremental:
  stop_after_consecutive_known_posts: 30

limits:
  max_posts: 100   # For benchmark runs; null for production
```

---

## 8. Phase 01 Acceptance Criteria

- [ ] Benchmark definition (100 posts, clean DB, documented hardware) reviewed
- [ ] All timing instrumentation points identified
- [ ] Benchmark output format approved
- [ ] Decision table (bottleneck -> action) reviewed
- [ ] All 6 benchmark test scenarios (5.1-5.6) reviewed
- [ ] Tooling list reviewed
- [ ] Baseline config confirmed as starting point for benchmarks
- [ ] Rule confirmed: no tuning without benchmark data
