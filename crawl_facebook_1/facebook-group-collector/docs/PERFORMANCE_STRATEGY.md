# PERFORMANCE_STRATEGY.md
# Facebook Group Data Collector — Performance Strategy

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Performance Philosophy

> **"Correctness and observability before micro-optimization.
> Measure first. Optimize only the real bottleneck."**

The following constraints drive every performance decision:

1. **Browser is the bottleneck** — Playwright DOM interaction is 10-100x slower than DB writes or HTTP downloads. All other components must move at browser speed or faster.
2. **No blind concurrency scaling** — More browser contexts ≠ faster. Each context adds overhead and instability. Benchmark before increasing.
3. **No row-by-row inserts** — Batch writes are mandatory.
4. **No blocking the browser** — DB writes, media downloads, and OCR run in parallel, never in browser's critical path.
5. **Measure before tuning** — Every tuning decision requires a benchmark result, not a guess.

---

## 2. Component Performance Budget

| Component | Target | Bottleneck risk |
|-----------|--------|----------------|
| Feed scroll + post card parsing | ~3-5 posts/sec | Playwright page load, DOM query |
| Post page open + comment extract | ~2-4 posts/sec (with comments) | Browser wait, page render |
| DB batch write (posts) | < 50ms per 500-row batch | PostgreSQL index maintenance |
| DB batch write (comments) | < 100ms per 1000-row batch | FK resolution, index |
| Media download | ~5-10 files/sec (6 workers) | Network bandwidth, CDN rate limit |
| In-memory dedupe lookup | < 1ms | Python dict lookup |
| SHA-256 hash (image) | < 5ms for typical image | CPU, image size |

---

## 3. Strategy 1 — Async Producer-Consumer

**Problem:** If browser waits for DB write → browser is idle 50-80% of the time.

**Solution:** Separate every stage into independent async workers connected by bounded queues.

```
Browser Producer (1 task)
    |-- pushes PostDiscoveredItem --> post_queue [bounded]
    
Comment Workers (N tasks)  <-- consume from post_queue
    |-- pushes CommentItem -------> comment_queue [bounded]
    |-- pushes MediaJobItem ------> media_queue [bounded]

DB Writer Workers (N tasks) <-- consume from post_queue + comment_queue
    |-- batch upsert to PostgreSQL

Media Workers (N tasks) <-- consume from media_queue
    |-- download + hash + store
```

**Result:** Browser never waits. DB and media run at their own pace. Queues absorb bursts.

---

## 4. Strategy 2 — Batch Database Writes

**Problem:** `INSERT ... VALUES (single_row)` is 100x slower than batched inserts at scale.

**Solution:**
- Buffer items in memory
- Flush on batch_size OR flush_ms timeout
- Single `INSERT ... ON CONFLICT DO UPDATE` per batch

```sql
-- Example: batch upsert 500 posts in one round-trip
INSERT INTO facebook_posts (id, facebook_post_id, group_id, ...)
VALUES ($1,$2,$3,...), ($4,$5,$6,...), ...  -- 500 rows
ON CONFLICT (facebook_post_id) DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    source_comment_count = EXCLUDED.source_comment_count,
    updated_at = NOW()
WHERE facebook_posts.updated_at < EXCLUDED.updated_at;
```

**Batch configuration:**
```yaml
database:
  posts_batch: 500
  comments_batch: 1000
  actors_batch: 500
  media_batch: 500
  flush_ms: 1500
```

---

## 5. Strategy 3 — Bounded Queues + Backpressure

**Problem:** If browser is faster than DB, unbounded queue grows to OOM.

**Solution:** `asyncio.Queue(maxsize=N)` — `put()` blocks when full.

```python
post_queue = asyncio.Queue(maxsize=2000)

# Producer (browser)
await post_queue.put(item)   # Blocks when queue is full
# This is natural backpressure — no extra code needed

# Consumer (comment worker)
item = await post_queue.get()
# Process...
post_queue.task_done()
```

**Queue sizing rationale:**
- `post_queue=2000`: Enough to buffer ~10 min of feed scroll at 3 posts/sec
- `comment_queue=5000`: Comments arrive faster than posts; larger buffer
- `media_queue=5000`: Media URLs accumulate rapidly

**Monitoring:** Log `queue.qsize() / queue.maxsize` every N seconds. Consistent > 80% → downstream bottleneck.

---

## 6. Strategy 4 — Browser Concurrency (Conservative)

**Default:** 1 browser context, 1 feed page, 2 comment pages.

**Why conservative:**
- Multiple contexts increase memory (each context = full browser profile)
- Facebook may fingerprint unusual multi-context patterns
- Benchmark at context_count=1 first; measure posts/sec

**Scale-up decision process:**
```
1. Run benchmark_100_posts at context_count=1
2. Record posts/sec and memory usage
3. If posts/sec < target AND memory < 2GB → try context_count=2
4. Re-run benchmark; compare delta
5. Only increase if measurable improvement AND stable
```

---

## 7. Strategy 5 — Resource Loading Optimization

**Potential savings:** Block unnecessary resources to reduce page load time.

**Safe to block (after benchmarking):**
- Video/audio streams (not needed for text/image extraction)
- Web fonts (cosmetic only)
- Analytics/tracking pixels

**DO NOT block without benchmarking:**
- JavaScript (required for React-based Facebook DOM)
- XHR/fetch (may be required for lazy-loading content)
- CSS (may affect layout/visibility detection)

**Implementation:** Playwright route interception. Only apply after proving it does NOT break lazy-load or extraction. Measure page load time before/after.

```python
# Example — block video streams only if benchmarked safe
async def route_handler(route):
    if route.request.resource_type in ("media",):
        await route.abort()
    else:
        await route.continue_()

await page.route("**/*", route_handler)
```

---

## 8. Strategy 6 — In-Memory Dedup Cache

**Problem:** Checking DB for every item is expensive at high throughput.

**Solution:** Maintain an in-memory set of seen IDs for the current run.

```python
class InMemoryDedupeCache:
    def __init__(self):
        self._post_ids: set[str] = set()
        self._comment_ids: set[str] = set()
        self._actor_ids: set[str] = set()

    def is_post_seen(self, facebook_post_id: str) -> bool:
        return facebook_post_id in self._post_ids

    def mark_post_seen(self, facebook_post_id: str):
        self._post_ids.add(facebook_post_id)
```

**Scale option:** If set grows beyond acceptable memory (~50M IDs), replace with Redis Bloom filter (`pybloom-live`). False positive rate ~ 0.1% acceptable (DB upsert is the authoritative dedup).

---

## 9. Strategy 7 — Connection Pooling

```python
# asyncpg pool — reuse connections across workers
pool = await asyncpg.create_pool(
    dsn=config.database.url,
    min_size=5,
    max_size=20,  # Tune based on worker count
    command_timeout=30
)
```

- DB writers share the pool; no connection creation overhead per batch
- Pool size = (db_writers + comment_workers + media_workers) * 2 as starting point

---

## 10. Performance Monitoring (No Dashboard)

All metrics emitted to stdout as structured JSON or human-readable log lines every 10 seconds:

```
[METRICS] posts_discovered=1420 posts_new=312 posts_per_sec=3.8
          comments_discovered=8210 comments_new=2102 comments_per_sec=18.4
          media_discovered=830 media_downloaded=798 media_per_sec=5.3
          post_queue=420/2000 comment_queue=830/5000 media_queue=1201/5000
          errors=14 retries=9 memory_mb=1400 elapsed=00:12:41
```

**Alert thresholds (log WARN):**
- `post_queue > 80%` full → downstream bottleneck
- `errors > 50` in last 100 items → possible DOM drift
- `memory_rss > 3GB` → possible memory leak
- `posts_per_sec < 0.5` for > 60s → browser stall

---

## 11. Known Performance Risks

| Risk | Mitigation |
|------|-----------|
| Facebook rate limiting | Randomized scroll delays (0.5-2s); not tunable to zero |
| DOM structure changes | Selectors in single file; fail fast with PARTIAL status |
| Session expiry mid-crawl | BLOCKED_AUTH detection + safe checkpoint + halt |
| Queue starvation (empty post_queue) | Comment workers wait on queue with timeout; don't busy-loop |
| Memory growth from large in-memory cache | Monitor set size; add cache eviction if needed |
| asyncio event loop blocking | Ensure no sync I/O in async context; use `run_in_executor` for CPU-bound tasks |

---

## 12. Phase 01 Acceptance Criteria

- [ ] All 7 performance strategies understood and agreed upon
- [ ] Conservative browser concurrency defaults confirmed
- [ ] Batch write configuration values reviewed
- [ ] Queue sizes and backpressure mechanism reviewed
- [ ] Metrics output format approved
- [ ] Resource blocking strategy: only after benchmarking, not by default
- [ ] No optimization decisions made without benchmark data
