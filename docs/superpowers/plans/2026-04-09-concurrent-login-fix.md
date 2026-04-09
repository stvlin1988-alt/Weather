# Concurrent Login Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix "連線錯誤" when 5-6 users login simultaneously by offloading face_recognition to a thread pool and relaxing the rate limiter.

**Architecture:** Extract CPU-intensive face_recognition calls into standalone functions, run them via `concurrent.futures.ThreadPoolExecutor(max_workers=3)`. dlib releases the GIL so threads achieve real parallelism. Gevent event loop stays unblocked.

**Tech Stack:** Python `concurrent.futures.ThreadPoolExecutor`, existing `face_recognition`/dlib, Flask rate limiter

---

### Task 1: Extract face operations into thread-safe functions

**Files:**
- Modify: `auth/routes.py:147-168` (`_verify_face`) and lines `118-123` (inline face detection)

- [ ] **Step 1: Add ThreadPoolExecutor and helper functions at module level**

Add after the existing imports (after line 19) in `auth/routes.py`:

```python
from concurrent.futures import ThreadPoolExecutor

_face_executor = ThreadPoolExecutor(max_workers=3)


def _do_face_compare(known_encoding, img_data_bytes):
    """Run in thread — CPU-intensive face_recognition calls."""
    img = face_recognition.load_image_file(io.BytesIO(img_data_bytes))
    locations = face_recognition.face_locations(img, number_of_times_to_upsample=2)
    encodings = face_recognition.face_encodings(img, locations)
    if not encodings:
        return False, 0.0
    distances = face_recognition.face_distance([known_encoding], encodings[0])
    match = bool(face_recognition.compare_faces([known_encoding], encodings[0], tolerance=0.45)[0])
    confidence = float(1 - distances[0])
    return match, confidence


def _do_detect_any_face(img_data_bytes):
    """Run in thread — check if any face exists in image."""
    img = face_recognition.load_image_file(io.BytesIO(img_data_bytes))
    return len(face_recognition.face_locations(img, number_of_times_to_upsample=2)) > 0
```

- [ ] **Step 2: Rewrite `_verify_face()` to use thread pool**

Replace the existing `_verify_face` function (lines 147-168) with:

```python
def _verify_face(user: User, image_b64: str):
    """Returns (match: bool, confidence: float). Face ops run in thread pool."""
    try:
        img_data = base64.b64decode(image_b64.split(",")[-1])
        known = user.get_face_encoding()
        if known is None:
            return False, 0.0
        logger.warning("_verify_face: submitting to thread pool for user=%s", user.username)
        future = _face_executor.submit(_do_face_compare, known, img_data)
        match, confidence = future.result(timeout=15)
        logger.warning("_verify_face: user=%s match=%s confidence=%.3f", user.username, match, confidence)
        return match, confidence
    except Exception as e:
        logger.warning("_verify_face exception: user=%s error=%s", user.username, e)
        return False, 0.0
```

- [ ] **Step 3: Rewrite inline face detection in `verify()` to use thread pool**

Replace lines 118-123 (the `try` block that checks for any face in the image) with:

```python
    try:
        img_data = base64.b64decode(face_image.split(",")[-1])
        future = _face_executor.submit(_do_detect_any_face, img_data)
        any_face_found = future.result(timeout=15)
    except Exception:
        any_face_found = False
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

Run: `cd /home/hirain0126/projects/webapp/app_unified && python -m pytest tests/test_auth.py -v`

Expected: All tests PASS (tests mock face_recognition, so thread pool is transparent)

- [ ] **Step 5: Commit**

```bash
git add auth/routes.py
git commit -m "feat: offload face_recognition to thread pool (max_workers=3) to prevent gevent blocking"
```

---

### Task 2: Relax rate limiter on /auth/verify

**Files:**
- Modify: `auth/routes.py:65`

- [ ] **Step 1: Change rate limit from 5 to 20 per minute**

Replace line 65:
```python
@limiter.limit("5 per minute", exempt_when=lambda: current_app.config.get("TESTING"))
```
with:
```python
@limiter.limit("20 per minute", exempt_when=lambda: current_app.config.get("TESTING"))
```

- [ ] **Step 2: Run tests**

Run: `cd /home/hirain0126/projects/webapp/app_unified && python -m pytest tests/test_auth.py -v`

Expected: All tests PASS (rate limiter is disabled in test config)

- [ ] **Step 3: Commit**

```bash
git add auth/routes.py
git commit -m "fix: relax /auth/verify rate limit from 5 to 20 per minute for shared WiFi scenarios"
```

---

### Task 3: Full test suite verification

- [ ] **Step 1: Run all tests**

Run: `cd /home/hirain0126/projects/webapp/app_unified && python -m pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 2: Verify ThreadPoolExecutor import doesn't break production startup**

Run: `cd /home/hirain0126/projects/webapp/app_unified && python -c "from auth.routes import auth_bp; print('import OK')"`

Expected: `import OK`
