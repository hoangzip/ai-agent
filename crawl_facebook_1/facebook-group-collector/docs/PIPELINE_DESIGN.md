# PIPELINE_DESIGN.md
# Facebook Group Data Collector — Pipeline Design

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Pipeline Overview

The system uses an **async producer-consumer** architecture with bounded queues and backpressure. The browser is the most expensive resource and must never be blocked by downstream processing.

```
PRODUCER LAYER                  QUEUE LAYER              CONSUMER LAYER
=================               ===========              ==============

Browser Producer                post_queue               Comment Workers (N)
  - Feed scroll                  [max: 2000]  ---------> DB Writer (posts)
  - Post URL discovery                |
  - Group metadata                    |
  - NO binary downloads               v
  - NO DB waits               comment_queue               DB Writer (comments)
                                [max: 5000]  ---------> DB Writer (actors)
                                     |
                                     v
                               media_queue               Media Download Workers (N)
                                [max: 5000]  --------->  SHA-256 hash
                                                         Storage write
                                                         ocr_status = pending
```

---

## 2. Item/Message Schemas

### 2.1 `PostDiscoveredItem`
Pushed by Browser Producer into `post_queue`:

```python
@dataclass
class PostDiscoveredItem:
    # Discovery context
    discovery_run_id: str          # UUID of crawl_run
    discovered_at: datetime

    # Facebook-sourced (nullable if DOM doesn't expose)
    facebook_post_id: Optional[str]
    post_url: Optional[str]
    facebook_group_id: Optional[str]

    # Author info
    author_display_name: Optional[str]
    author_profile_url: Optional[str]
    author_facebook_user_id: Optional[str]

    # Post content (from feed card — may be truncated)
    title: Optional[str]
    title_source: Optional[str]    # 'facebook' or 'derived'
    content_preview: Optional[str] # May be truncated in feed
    posted_at: Optional[datetime]

    # Signal for action decision
    source_comment_count: Optional[int]
    media_urls_preview: list[str]  # URLs visible in feed card

    # Action override (set by scheduler if this is a refresh job)
    action: str  # 'FULL_CRAWL' | 'REFRESH_COMMENTS' | 'SKIP' | 'DISCOVER_ONLY'
```

### 2.2 `CommentItem`
Pushed by Comment Workers into `comment_queue`:

```python
@dataclass
class CommentItem:
    post_internal_id: str          # UUID of facebook_posts
    facebook_comment_id: Optional[str]
    parent_comment_id: Optional[str]  # facebook_comment_id of parent
    parent_internal_id: Optional[str] # UUID of parent comment if known

    author_display_name: Optional[str]
    author_profile_url: Optional[str]
    author_facebook_user_id: Optional[str]

    content: Optional[str]
    commented_at: Optional[datetime]
    depth: int                     # 0 = top-level, 1+ = reply

    known_reply_count: Optional[int]
    last_reply_at: Optional[datetime]

    discovered_at: datetime
    raw_payload: Optional[dict]
```

### 2.3 `MediaJobItem`
Pushed by Browser/Comment Workers into `media_queue`:

```python
@dataclass
class MediaJobItem:
    owner_type: str                # 'post' or 'comment'
    owner_id: str                  # UUID of post or comment
    source_url: str                # Original URL
    position: int                  # Order in content (0-indexed)
    media_type: str                # 'image' | 'video'
    discovered_at: datetime
    run_id: str
```

---

## 3. Queue Configuration

| Queue | Max Size | Producer | Consumers |
|-------|----------|----------|-----------|
| `post_queue` | 2,000 | Browser Producer | Comment Workers + DB Writer |
| `comment_queue` | 5,000 | Comment Workers | DB Writer |
| `media_queue` | 5,000 | Browser + Comment Workers | Media Download Workers |

All queues use `asyncio.Queue` with `maxsize` set. Producers call `await queue.put()` which naturally blocks (backpressure) when queue is full.

---

## 4. Backpressure Strategy

```
Browser Producer Loop:
  while scrolling:
    extract post from DOM
    await post_queue.put(item)   # <-- blocks here if queue is full
    continue scrolling
```

- No separate backpressure mechanism needed beyond `asyncio.Queue(maxsize=N)`
- Browser producer naturally pauses at `put()` when queue is full
- This prevents OOM from unbounded queue growth
- Queue fullness is logged as a metric (queue_depth / queue_max)

---

## 5. Worker Lifecycle

### 5.1 Startup Sequence
```
1. Load config
2. Connect to PostgreSQL (connection pool)
3. Load / create crawl_run record
4. Load checkpoint (if resume mode)
5. Start DB Writer workers (N)
6. Start Media Download workers (N)
7. Start Comment workers (N)
8. Start Browser Producer
9. Start Metrics Emitter (background loop)
10. Start Checkpoint Manager (background loop)
```

### 5.2 Shutdown Sequence (SIGTERM/SIGINT)
```
1. Signal Browser Producer to stop scrolling (set stop event)
2. Wait for Browser Producer to finish current page
3. Put sentinel values into post_queue and comment_queue
4. Workers drain queues and exit on sentinel
5. Final checkpoint write
6. Final metrics flush
7. Close DB connection pool
8. Close browser
9. Exit 0
```

### 5.3 Worker Count Defaults (from crawler.yaml)
```yaml
browser:
  context_count: 1      # Start conservative; benchmark before increasing
  feed_pages: 1
  comment_pages: 2

workers:
  comment_workers: 2    # Opens post URLs for comment extraction
  db_writers: 2         # Batch DB write workers
  media_workers: 6      # Independent file download workers
```

---

## 6. DB Writer Batch Flush Logic

```python
class BatchWriter:
    def __init__(self, batch_size: int, flush_ms: int):
        self.buffer = []
        self.batch_size = batch_size
        self.flush_ms = flush_ms
        self.last_flush = time.monotonic()

    async def add(self, item):
        self.buffer.append(item)
        if (len(self.buffer) >= self.batch_size or
                time.monotonic() - self.last_flush >= self.flush_ms / 1000):
            await self.flush()

    async def flush(self):
        if not self.buffer:
            return
        batch = self.buffer[:]
        self.buffer.clear()
        self.last_flush = time.monotonic()
        await self.upsert_batch(batch)  # Single DB round-trip
```

**Batch sizes:**
- posts: 500 rows per flush
- comments: 1,000 rows per flush
- actors: 500 rows per flush
- media metadata: 500 rows per flush
- flush_ms: 1,500ms max wait

---

## 7. Action Decision Logic

When a `PostDiscoveredItem` is dequeued by a Comment Worker:

```python
async def decide_action(post_item: PostDiscoveredItem, db: AsyncDB) -> str:
    existing = await db.get_post(
        facebook_post_id=post_item.facebook_post_id,
        post_url=post_item.post_url
    )

    if existing is None:
        return "FULL_CRAWL"

    if post_requires_refresh(existing):
        return "REFRESH_COMMENTS"

    return "SKIP"

def post_requires_refresh(post: Post) -> bool:
    # Signal 1: next_check_at has passed
    if post.next_check_at and post.next_check_at <= now():
        return True
    # Signal 2: source count > known count (new comments visible)
    if (post.source_comment_count and post.known_comment_count and
            post.source_comment_count > post.known_comment_count):
        return True
    # Signal 3: comments_complete is False (previous crawl was partial)
    if not post.comments_complete:
        return True
    return False
```

---

## 8. Comment Tree Extraction

Comments are organized as a tree (replies to replies):

```
Post
 +-- Comment A (depth=0)
 |     +-- Reply A1 (depth=1, parent=A)
 |     +-- Reply A2 (depth=1, parent=A)
 +-- Comment B (depth=0)
       +-- Reply B1 (depth=1, parent=B)
             +-- Reply B1a (depth=2, parent=B1)
```

**Strategy:**
- Extract top-level comments first; push to `comment_queue` immediately
- For each top-level comment, check if it has replies visible
- Expand replies by clicking "View replies" / scroll
- Track `depth` in `CommentItem`
- Store `parent_comment_id` linking reply to parent

**Delta detection for REFRESH:**
- Load `last_seen_comment_id` from DB
- Scroll comments until we see a comment we've already stored
- Stop scrolling after seeing N consecutive known comments

---

## 9. Media Pipeline

Browser Producer (or Comment Worker) detects media URLs:
```python
media_job = MediaJobItem(
    owner_type="post",
    owner_id=post_internal_id,
    source_url=img_url,
    position=0,
    media_type="image",
    discovered_at=now(),
    run_id=run_id
)
await media_queue.put(media_job)
# Browser continues immediately — does NOT download
```

Media Download Worker:
```python
async def process_media_job(job: MediaJobItem):
    # 1. Check if source_url already downloaded (DB lookup)
    existing = await db.get_media_by_source_url(job.source_url)
    if existing and existing.download_status == 'downloaded':
        # Just create content_media mapping record
        await db.upsert_content_media(job, existing.id)
        return

    # 2. Download file
    file_bytes = await http_client.get(job.source_url)

    # 3. Compute SHA-256
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    # 4. Check SHA-256 dedup (same file, different URL)
    existing_by_hash = await db.get_media_by_sha256(sha256)
    if existing_by_hash:
        await db.upsert_content_media(job, existing_by_hash.id)
        return

    # 5. Save to local storage
    storage_uri = await local_storage.save(sha256, file_bytes, job.media_type)

    # 6. Insert media_asset record
    asset_id = await db.insert_media_asset(
        source_url=job.source_url,
        sha256=sha256,
        storage_uri=storage_uri,
        download_status='downloaded',
        ocr_status='pending'   # Phase 13 OCR worker picks this up
    )

    # 7. Create content_media mapping
    await db.upsert_content_media(job, asset_id)
```

---

## 10. Checkpoint Strategy

**When to checkpoint:**
- Every `checkpoint.every_posts` = 20 posts processed
- Every `checkpoint.every_seconds` = 15 seconds elapsed
- NOT after every comment (too expensive)
- Always on graceful shutdown

**Checkpoint data saved:**
```python
{
    "run_id": "...",
    "group_id": "...",
    "mode": "full",
    "last_post_id": "uuid-of-last-processed-post",
    "last_post_time": "2024-01-15T10:30:00Z",
    "consecutive_known_posts": 0,
    "progress_snapshot": {
        "posts_seen": 450,
        "feed_scroll_position": "cursor_xyz"
    }
}
```

**On resume:**
1. Load checkpoint from `crawl_checkpoints` by `run_id`
2. Restore `consecutive_known_posts` counter
3. Resume feed from `last_post_time` / cursor (best effort — feed may have changed)
4. Skip posts already in DB (dedup catches them)

---

## 11. Incremental Stop Condition

```python
consecutive_known = 0
STOP_THRESHOLD = config.incremental.stop_after_consecutive_known_posts  # default: 30

for post_item in feed_scroll():
    action = await decide_action(post_item)

    if action == "SKIP":
        consecutive_known += 1
        if consecutive_known >= STOP_THRESHOLD:
            log.info("Incremental stop: %d consecutive known posts", consecutive_known)
            break
    else:
        consecutive_known = 0  # Reset on new content
        await post_queue.put(post_item)
```

**Rationale:** Facebook feed is not strictly chronological. We must not stop on the first known post — content may be interleaved with new posts. The threshold of 30 is a configurable baseline.

---

## 12. Phase 01 Acceptance Criteria

- [ ] Queue sizing and backpressure strategy reviewed
- [ ] Item schemas cover all required fields
- [ ] Action decision logic (FULL_CRAWL / REFRESH / SKIP) reviewed
- [ ] Comment tree extraction strategy reviewed
- [ ] Media pipeline (async, no blocking) reviewed
- [ ] Checkpoint data structure complete
- [ ] Incremental stop condition logic reviewed
- [ ] Worker lifecycle (startup + graceful shutdown) reviewed
