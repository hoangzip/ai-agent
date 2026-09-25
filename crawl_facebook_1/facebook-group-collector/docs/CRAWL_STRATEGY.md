# CRAWL_STRATEGY.md
# Facebook Group Data Collector — Crawl Strategy

> **Phase 01 — Architecture Review**
> Status: DRAFT

---

## 1. Crawl Modes

The system supports 4 crawl modes. Mode is specified via CLI and stored in `crawl_runs.mode`.

### 1.1 FULL Mode
**When:** First-time crawl of a group, or forced full re-scan.

**Behavior:**
- Scroll the group feed from the beginning (newest to oldest)
- For every post discovered: `FULL_CRAWL` action (extract all comments, replies, media)
- No stop condition based on known posts
- Stop when feed is exhausted or `limits.max_posts` is reached
- Checkpoint every 20 posts or 15 seconds

**Use case:** Initial data collection; forced full refresh after long gap.

---

### 1.2 INCREMENTAL Mode
**When:** Subsequent crawl runs after initial full crawl.

**Behavior:**
- Scroll feed from newest
- For each post discovered:
  - If NEW → `FULL_CRAWL`
  - If KNOWN + refresh due → `REFRESH_COMMENTS`
  - If KNOWN + no refresh signal → `SKIP` (increment consecutive counter)
- Stop when `consecutive_known_posts >= stop_after_consecutive_known_posts` (default: 30)
- Checkpoint every 20 posts or 15 seconds

**Key invariant:** The stop counter resets to 0 when a new post is found. This handles non-chronological feed ordering.

```python
consecutive_known = 0
for post in scroll_feed():
    action = decide_action(post)
    if action == "SKIP":
        consecutive_known += 1
        if consecutive_known >= STOP_THRESHOLD:
            break
    else:
        consecutive_known = 0
        await post_queue.put(post)
```

---

### 1.3 DEEP Mode
**When:** Scheduled or manual; fills in posts discovered but not fully crawled.

**Target posts:** `crawl_status IN ('DISCOVERED', 'PARTIAL')` — posts we know about but haven't fully extracted comments/media.

**Behavior:**
- Do NOT scroll feed
- Query DB for posts with status `DISCOVERED` or `PARTIAL`
- For each: `FULL_CRAWL` action (open post URL, extract everything)
- Ordered by `next_check_at ASC` (oldest overdue first)

---

### 1.4 REFRESH Mode
**When:** Scheduled; checks for new comments on known posts.

**Target posts:** `crawl_status = 'REFRESH_DUE'` or `next_check_at <= NOW()`

**Behavior:**
- Do NOT scroll feed
- Query DB for posts scheduled for revisit
- For each: `REFRESH_COMMENTS` action (delta comment extraction)
- Update `next_check_at` based on revisit schedule after completion

---

## 2. Post Action Decision Flow

```
PostDiscoveredItem received
         |
         v
[Query DB: does this post exist?]
         |
    +----+----+
    |         |
   YES        NO
    |         |
    v         v
[Check refresh signals]   --> FULL_CRAWL
    |
    +-- next_check_at <= now()     --> REFRESH_COMMENTS
    +-- source_count > known_count --> REFRESH_COMMENTS
    +-- comments_complete == False --> REFRESH_COMMENTS
    +-- (none of above)            --> SKIP
```

### Refresh Signals (multiple, any triggers refresh)

| Signal | Description | Source |
|--------|-------------|--------|
| `next_check_at` | Scheduled revisit time has passed | DB field |
| `source_comment_count > known_comment_count` | Facebook UI shows more comments than we have | Feed card extraction |
| `comments_complete == False` | Previous crawl was partial | DB field |

Using multiple signals prevents over-reliance on a single indicator that may not always be available.

---

## 3. Post Revisit Schedule

After each successful comment crawl, `next_check_at` is computed:

| Post age | Revisit interval |
|----------|-----------------|
| < 1 day | 1 hour |
| 1–3 days | 6 hours |
| 3–7 days | 12 hours |
| 7–30 days | 24 hours |
| 30–90 days | 72 hours |
| > 90 days | 7 days (configurable max) |

```python
def compute_next_check_at(post: Post, config: RevisitConfig) -> datetime:
    age = now() - post.posted_at
    if age < timedelta(days=1):
        interval = timedelta(hours=config.interval_under_1d)  # 1h
    elif age < timedelta(days=3):
        interval = timedelta(hours=config.interval_1_to_3d)   # 6h
    elif age < timedelta(days=7):
        interval = timedelta(hours=config.interval_3_to_7d)   # 12h
    elif age < timedelta(days=30):
        interval = timedelta(hours=config.interval_7_to_30d)  # 24h
    elif age < timedelta(days=90):
        interval = timedelta(hours=config.interval_30_to_90d) # 72h
    else:
        interval = timedelta(days=config.interval_over_90d)   # 7d
    return now() + interval
```

All interval values come from `config/crawler.yaml`. Not hard-coded.

---

## 4. Comment Delta Extraction (REFRESH_COMMENTS)

**Goal:** Find only NEW comments since last crawl; avoid re-processing all comments.

**Strategy:**
1. Open post URL in browser
2. Load `last_seen_comment_id` and `last_comment_at` from DB
3. Start reading comments from newest (if Facebook allows reverse sort) or oldest
4. Maintain a sliding window of "seen" comment IDs
5. Stop when we encounter `N` consecutive comments already in our DB

```python
KNOWN_STOP_THRESHOLD = 5  # Stop after 5 consecutive known comments

consecutive_known = 0
new_comments = []

for comment in extract_comments(post_page):
    if is_comment_known(comment.facebook_comment_id):
        consecutive_known += 1
        if consecutive_known >= KNOWN_STOP_THRESHOLD:
            break
    else:
        consecutive_known = 0
        new_comments.append(comment)
        await comment_queue.put(comment)
```

**Fallback:** If `facebook_comment_id` is unavailable, use `dedupe_key` for matching.

---

## 5. Authentication & Session Management

### 5.1 Initial Setup (one-time)
```bash
# Run once to create session
python main.py auth --save-state data/browser_state/default.json
# Opens headed browser; user logs in manually
# State saved to gitignored path
```

### 5.2 Session Reuse
```python
async with async_playwright() as pw:
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        storage_state="data/browser_state/default.json"
    )
    # Session is restored; no re-login needed
```

### 5.3 Session Expiry Detection
Detect these conditions and halt with `BLOCKED_AUTH`:
- Redirect to `facebook.com/login`
- Redirect to `facebook.com/checkpoint`
- MFA prompt detected in DOM
- "Continue as..." prompt detected

```python
async def check_auth_status(page: Page) -> bool:
    url = page.url
    if any(x in url for x in ["/login", "/checkpoint"]):
        return False
    # Check DOM for login form
    login_form = await page.query_selector(SELECTORS.login_form)
    if login_form:
        return False
    return True
```

On auth failure:
1. Set `crawl_run.status = 'blocked_auth'`
2. Write checkpoint
3. Log clear error message
4. Close browser cleanly
5. Exit with code 2 (distinguishable from crash)

---

## 6. Error Handling & Recovery

### 6.1 Per-Post Error Isolation
```python
async def process_post(post_item: PostDiscoveredItem, retries=3):
    for attempt in range(retries):
        try:
            await crawl_post(post_item)
            return
        except SelectorNotFoundError:
            # DOM structure changed — mark PARTIAL, do not retry
            await db.set_post_status(post_item.id, 'PARTIAL')
            log.error("DOM drift on post %s", post_item.post_url)
            return
        except Exception as e:
            wait = 2 ** attempt + random.uniform(0, 1)  # Exponential backoff
            log.warning("Attempt %d failed for post %s: %s", attempt+1, post_item.post_url, e)
            await asyncio.sleep(wait)
    # All retries exhausted
    await db.set_post_status(post_item.id, 'FAILED')
```

### 6.2 Error Types and Responses

| Error | Response | crawl_status |
|-------|----------|-------------|
| Selector not found (DOM drift) | Mark PARTIAL, log error, continue | PARTIAL |
| Network timeout | Retry with backoff (max 3x) | FAILED if all retries fail |
| Auth expired | BLOCKED_AUTH halt | N/A (run-level) |
| Page not found (404) | Mark FAILED, continue | FAILED |
| Rate limit detected | Pause 30-60s, retry once | PARTIAL or FAILED |
| Unknown exception | Retry with backoff, log stack trace | FAILED if all fail |

### 6.3 DOM Drift Policy
- If a required selector is missing → **fail loudly** with exception
- Do NOT insert partial/wrong data silently
- Do NOT fall back to guessing field values
- Log the exact selector that failed
- Post gets `crawl_status = 'PARTIAL'` for later manual review or re-crawl

---

## 7. Incremental Discovery Stop Condition

**Default:** Stop after 30 consecutive known posts.

**Why not stop on first known post?**
Facebook feed is not strictly chronological. New promoted posts, pinned posts, or re-shared content may appear between old posts. A single known post is not a reliable stop signal.

**Why 30?**
- Provides a safety buffer for non-chronological content
- At ~3 posts/sec, 30 posts = ~10 seconds of scrolling
- Configurable: `incremental.stop_after_consecutive_known_posts: 30`

---

## 8. Checkpoint & Resume

### 8.1 Checkpoint Frequency
- Every 20 posts processed (`checkpoint.every_posts`)
- Every 15 seconds elapsed (`checkpoint.every_seconds`)
- Always on SIGTERM/SIGINT

### 8.2 Resume Behavior
On startup with `--resume` flag:
1. Find latest checkpoint for this `group_id + mode`
2. Load `last_post_time` and `consecutive_known_posts`
3. Restart feed scroll from the beginning (Facebook does not support cursor)
4. Skip posts older than `last_post_time` that are already in DB (dedup handles this)
5. Restore `consecutive_known_posts` counter for incremental mode

**Note:** Facebook does not support pagination cursors in group feeds. Resume means re-scanning from the top and relying on dedup to skip already-processed content. The checkpoint reduces re-work by providing early stop hints.

---

## 9. Media Discovery Strategy

**Browser Producer responsibility:**
- Detect image URLs visible in feed card (preview images)
- Detect video thumbnail URLs
- Push `MediaJobItem` to `media_queue`
- DO NOT download anything

**Comment Worker responsibility:**
- After opening post page: detect all full-size image URLs
- Detect images in comments
- Push `MediaJobItem` for each

**Media Worker responsibility:**
- Download, hash, store
- Set `ocr_status = pending`

**Never block browser for media.** All downloads happen asynchronously.

---

## 10. Phase 01 Acceptance Criteria

- [ ] All 4 crawl modes defined with clear triggers and behavior
- [ ] Action decision logic (FULL_CRAWL / REFRESH / SKIP) reviewed
- [ ] Multi-signal refresh detection reviewed
- [ ] Revisit schedule policy reviewed and configurable
- [ ] Comment delta extraction strategy reviewed
- [ ] Auth session management and expiry detection reviewed
- [ ] Error isolation (per-post, no crash propagation) reviewed
- [ ] DOM drift policy (fail loud, no silent wrong data) confirmed
- [ ] Incremental stop condition (30 consecutive) reviewed
- [ ] Checkpoint + resume strategy reviewed
