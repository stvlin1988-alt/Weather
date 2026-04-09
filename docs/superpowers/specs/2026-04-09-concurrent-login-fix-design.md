# Concurrent Login Fix — Design Spec

**Date**: 2026-04-09
**Status**: Approved

---

## Problem

5-6 users logging in simultaneously from their own phones causes "連線錯誤".

**Root cause**: `face_recognition` (dlib C++) is CPU-intensive (2-5s per call) and blocks the single gevent event loop in gunicorn. Concurrent verify requests queue up, later requests timeout, and WebSocket connections drop.

**Secondary cause**: Rate limiter on `/auth/verify` is `5 per minute` per IP. Users on the same WiFi share one public IP and collectively exhaust the limit quickly.

---

## Solution: Thread Pool + Rate Limiter Fix

### 1. Offload face_recognition to Thread Pool

Move all CPU-intensive `face_recognition` calls in `_verify_face()` to a `gevent.threadpool.ThreadPoolExecutor`.

- dlib releases the GIL during C++ computation, so threads achieve true parallelism
- gevent yields while waiting for the thread result, keeping the event loop responsive
- `max_workers=3` — allows up to 3 concurrent face verifications without overwhelming CPU

**File**: `auth/routes.py`

**Changes to `_verify_face()`**:
```python
from concurrent.futures import ThreadPoolExecutor
_face_executor = ThreadPoolExecutor(max_workers=3)

def _do_face_compare(known_encoding, img_data_bytes):
    """Runs in a thread — all CPU-intensive face_recognition calls here."""
    img = face_recognition.load_image_file(io.BytesIO(img_data_bytes))
    locations = face_recognition.face_locations(img, number_of_times_to_upsample=2)
    encodings = face_recognition.face_encodings(img, locations)
    if not encodings:
        return False, 0.0, len(locations)
    distances = face_recognition.face_distance([known_encoding], encodings[0])
    match = bool(face_recognition.compare_faces([known_encoding], encodings[0], tolerance=0.45)[0])
    confidence = float(1 - distances[0])
    return match, confidence, len(locations)
```

The main `_verify_face()` function submits to the executor and awaits the result:
```python
def _verify_face(user, image_b64):
    img_data = base64.b64decode(image_b64.split(",")[-1])
    known = user.get_face_encoding()
    if known is None:
        return False, 0.0
    future = _face_executor.submit(_do_face_compare, known, img_data)
    match, confidence, num_locations = future.result(timeout=15)
    return match, confidence
```

**Also offload the "no face detected" check** in `verify()` (the fallback path when no PIN user matches):
```python
def _detect_any_face(img_data_bytes):
    """Runs in a thread."""
    img = face_recognition.load_image_file(io.BytesIO(img_data_bytes))
    return len(face_recognition.face_locations(img, number_of_times_to_upsample=2)) > 0

# In verify(), replace inline face detection with:
future = _face_executor.submit(_detect_any_face, img_data)
any_face_found = future.result(timeout=15)
```

### 2. Rate Limiter Adjustment

**File**: `auth/routes.py`

Change from `5 per minute` to `20 per minute`:
```python
@limiter.limit("20 per minute", exempt_when=lambda: current_app.config.get("TESTING"))
def verify():
```

Rationale: 5-6 users on same WiFi, each may retry 2-3 times (face angle issues, camera delay). 20/min gives comfortable headroom without opening abuse risk.

### 3. Verify loop optimization (minor)

Currently `verify()` iterates all PIN-matched users and calls `_verify_face()` sequentially. With thread pool, each call no longer blocks the event loop, but they still run serially within the request. This is acceptable — typically only 1-2 users share the same PIN prefix, so the loop is short.

No change needed here.

---

## Files Changed

| File | Change |
|------|--------|
| `auth/routes.py` | Thread pool executor for face ops, rate limit 5→20 |

## Testing

1. Verify single user login still works normally
2. Verify concurrent logins (multiple tabs/devices) don't show "連線錯誤"
3. Verify WebSocket stays responsive during face verification
4. Verify rate limit allows 20 requests/min from same IP
