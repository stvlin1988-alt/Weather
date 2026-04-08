# Nine Feature Changes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 9 feature changes covering AI summary time logic, UI adjustments, filter overhaul, stealth vault timing, admin permissions, user management, and multi-user device login.

**Architecture:** All changes are in the existing Flask app at `/home/hirain0126/projects/webapp/app_unified/`. Backend changes touch `notes/routes.py`, `notes/ws.py`, `device/routes.py`, `admin/routes.py`, and `wasm/src/lib.rs`. Frontend changes touch templates in `templates/notes/` and `templates/admin/`. The changes are mostly independent and can be implemented sequentially.

**Tech Stack:** Python/Flask, Jinja2 templates, vanilla JS, Rust/WASM, PostgreSQL via SQLAlchemy

---

### Task 1: Business Day Time Logic (08:00-08:00)

**Files:**
- Modify: `app_unified/notes/routes.py:21-27` (`_date_filter` function)
- Modify: `app_unified/notes/routes.py:329-372` (`notes_ai_summary` function)
- Modify: `app_unified/notes/ws.py:51-57` (ws `_list_notes` date logic)
- Modify: `app_unified/templates/notes/index.html:230-237` (`saveSummaryAsNote` date title)

- [ ] **Step 1: Add business day helper function in notes/routes.py**

Add this function after the `RANGE_DAYS` dict (line 11), before `_ai_tasks`:

```python
from datetime import datetime, timedelta, timezone

_TW = timezone(timedelta(hours=8))


def _get_business_day_range():
    """Return (start, end) in UTC for the current business day (08:00-08:00 TW time).
    If now (TW) >= 08:00: today 08:00 ~ tomorrow 08:00
    If now (TW) < 08:00: yesterday 08:00 ~ today 08:00
    """
    now_tw = datetime.now(_TW)
    if now_tw.hour >= 8:
        start_tw = now_tw.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        start_tw = (now_tw - timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    end_tw = start_tw + timedelta(days=1)
    # Convert to UTC for DB queries
    start_utc = start_tw.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_tw.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _get_business_day_label():
    """Return the business day date string (YYYY-MM-DD) for display."""
    now_tw = datetime.now(_TW)
    if now_tw.hour >= 8:
        return now_tw.strftime("%Y-%m-%d")
    else:
        return (now_tw - timedelta(days=1)).strftime("%Y-%m-%d")
```

- [ ] **Step 2: Update `_date_filter` to use business day for "today"**

Replace the existing `_date_filter` function:

```python
def _date_filter(query, range_param):
    days = RANGE_DAYS.get(range_param, 3)
    if days == 0:
        start_utc, end_utc = _get_business_day_range()
        return query.filter(Note.updated_at >= start_utc, Note.updated_at < end_utc)
    else:
        since = datetime.utcnow() - timedelta(days=days)
        return query.filter(Note.updated_at >= since)
```

- [ ] **Step 3: Update `notes_ai_summary` to use business day for days=1**

In `notes_ai_summary()`, replace:
```python
    since = datetime.utcnow() - timedelta(days=days)
```
with:
```python
    if days == 1:
        start_utc, end_utc = _get_business_day_range()
    else:
        start_utc = datetime.utcnow() - timedelta(days=days)
        end_utc = None
```

And update the query from:
```python
    query = Note.query.filter(Note.updated_at >= since)
```
to:
```python
    query = Note.query.filter(Note.updated_at >= start_utc)
    if end_utc:
        query = query.filter(Note.updated_at < end_utc)
```

- [ ] **Step 4: Update WebSocket `_list_notes` date logic**

In `notes/ws.py`, update the `_list_notes` function. Replace lines 51-57:

```python
        range_days = {'today': 0, '3d': 3, '5d': 5, '7d': 7}
        days = range_days.get(range_param, 3)
        if days == 0:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Note.updated_at >= since)
```

with:

```python
        from notes.routes import _get_business_day_range
        range_days = {'today': 0, '3d': 3, '5d': 5, '7d': 7}
        days = range_days.get(range_param, 3)
        if days == 0:
            start_utc, end_utc = _get_business_day_range()
            query = query.filter(Note.updated_at >= start_utc, Note.updated_at < end_utc)
        else:
            since = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Note.updated_at >= since)
```

- [ ] **Step 5: Update `saveSummaryAsNote` date title in frontend**

In `templates/notes/index.html`, replace the `saveSummaryAsNote` function's date logic (lines 234-237):

```javascript
  var today = new Date();
  var dateStr = today.getFullYear() + '-' +
    String(today.getMonth() + 1).padStart(2, '0') + '-' +
    String(today.getDate()).padStart(2, '0');
```

with:

```javascript
  var now = new Date();
  var twHour = (now.getUTCHours() + 8) % 24;
  var bizDate = new Date(now.getTime() + 8 * 3600000);
  if (twHour < 8) bizDate.setDate(bizDate.getDate() - 1);
  var dateStr = bizDate.getFullYear() + '-' +
    String(bizDate.getMonth() + 1).padStart(2, '0') + '-' +
    String(bizDate.getDate()).padStart(2, '0');
```

- [ ] **Step 6: Commit**

```bash
git add app_unified/notes/routes.py app_unified/notes/ws.py app_unified/templates/notes/index.html
git commit -m "feat: AI摘要與筆記列表「今天」改為營業日 08:00-08:00"
```

---

### Task 2: Enlarge Author/Time in Notes UI

**Files:**
- Modify: `app_unified/templates/notes/index.html:10,134`
- Modify: `app_unified/templates/notes/editor.html:41`

- [ ] **Step 1: Enlarge note card author/time meta**

In `templates/notes/index.html`, change line 134:

```html
      <span style="font-size:.72rem;color:#bbb;">{{ note.author.username if note.author else '—' }} · {{ note.created_at | fmt_date }}</span>
```

to:

```html
      <span style="font-size:.85rem;color:#888;font-weight:600;">{{ note.author.username if note.author else '—' }} · {{ note.created_at | fmt_date }}</span>
```

- [ ] **Step 2: Enlarge editor updated-by info**

In `templates/notes/editor.html`, change line 41:

```css
.updated-by-info { font-size: .78rem; color: #aaa; margin-bottom: .5rem; }
```

to:

```css
.updated-by-info { font-size: .85rem; color: #888; margin-bottom: .5rem; }
```

- [ ] **Step 3: Commit**

```bash
git add app_unified/templates/notes/index.html app_unified/templates/notes/editor.html
git commit -m "feat: 放大筆記卡片作者/時間字體至 0.85rem"
```

---

### Task 3: Mutually Exclusive Filters (Priority / Date Range / Status)

**Files:**
- Modify: `app_unified/notes/routes.py:30-54` (`index` function)
- Modify: `app_unified/notes/routes.py:68-95` (`list_notes` function)
- Modify: `app_unified/templates/notes/index.html:98-117` (filter tabs)

- [ ] **Step 1: Update backend `index()` to support mutually exclusive filters**

Replace the `index()` function body (after `query = Note.query`) with filter logic that checks which filter group is active. The active filter is determined by which query param is present: `priority`, `status`, or `range`.

In `notes/routes.py`, replace the `index` function:

```python
@notes_bp.route("/")
@login_required
def index():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "")
    priority_filter = request.args.get("priority", "")
    stores = _get_stores()

    query = Note.query

    # Store scoping (always applied)
    if current_user.is_super_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    elif current_user.is_admin():
        query = query.filter_by(store=current_user.store)
    else:
        query = query.filter_by(store=current_user.store)

    # Mutually exclusive filters: priority, status, or date range
    # Determine active filter: if priority is set, ignore others; if status is set, ignore others; else use range
    active_filter = None
    if priority_filter and priority_filter in PRIORITY_CHOICES:
        active_filter = 'priority'
        query = query.filter_by(priority=priority_filter)
    elif status_filter and status_filter in STATUS_CHOICES:
        active_filter = 'status'
        query = query.filter_by(status=status_filter)
    else:
        active_filter = 'range'
        if not range_param:
            range_param = 'today'
        query = _date_filter(query, range_param)

    notes = query.order_by(Note.updated_at.desc()).all()

    return render_template("notes/index.html", notes=notes, stores=stores,
                           current_store=store_filter,
                           current_status=status_filter,
                           current_range=range_param,
                           current_priority=priority_filter,
                           active_filter=active_filter,
                           status_choices=STATUS_CHOICES,
                           priority_choices=PRIORITY_CHOICES)
```

- [ ] **Step 2: Update `list_notes` API similarly**

Replace the `list_notes` function:

```python
@notes_bp.route("/api", methods=["GET"])
@login_required
def list_notes():
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "")
    range_param = request.args.get("range", "")
    priority_filter = request.args.get("priority", "")
    stores = _get_stores()

    query = Note.query
    if current_user.is_super_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    elif current_user.is_admin():
        query = query.filter_by(store=current_user.store)
    else:
        query = query.filter_by(store=current_user.store)

    if priority_filter and priority_filter in PRIORITY_CHOICES:
        query = query.filter_by(priority=priority_filter)
    elif status_filter and status_filter in STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    else:
        if not range_param:
            range_param = 'today'
        query = _date_filter(query, range_param)

    notes = query.order_by(Note.updated_at.desc()).all()

    return jsonify([{
        "id": n.id, "title": n.title, "content": n.content,
        "store": n.store, "status": n.status or "pending",
        "priority": n.priority or "medium",
        "author": n.author.username if n.author else "",
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "updated_at": n.updated_at.isoformat() if n.updated_at else "",
    } for n in notes])
```

- [ ] **Step 3: Update frontend filter tabs to be mutually exclusive + add priority tabs**

In `templates/notes/index.html`, replace the status-tabs and range-tabs sections (lines 98-117) with:

```html
{% set priority_labels = {'':'全部優先權','high':'高','medium':'中','low':'低'} %}
<div class="range-tabs">
  <span style="font-size:.85rem;color:#666;align-self:center;margin-right:.25rem;">優先權：</span>
  {% for val, label in priority_labels.items() %}
  <a href="{{ url_for('notes.index', store=current_store, priority=val) }}"
     class="store-tab {% if active_filter == 'priority' and current_priority == val %}active{% endif %}"
     style="{% if active_filter == 'priority' and current_priority == val %}background:#e74c3c;color:#fff;{% endif %}">{{ label }}</a>
  {% endfor %}
</div>
<div class="range-tabs">
  <span style="font-size:.85rem;color:#666;align-self:center;margin-right:.25rem;">日期範圍：</span>
  {% set range_labels = [('today','今天'),('3d','近3天'),('7d','近7天'),('30d','近月')] %}
  {% for val, label in range_labels %}
  <a href="{{ url_for('notes.index', store=current_store, range=val) }}"
     class="store-tab {% if active_filter == 'range' and current_range == val %}active{% endif %}"
     style="{% if active_filter == 'range' and current_range == val %}background:#2c3e50;color:#fff;{% endif %}">{{ label }}</a>
  {% endfor %}
</div>
{% set status_labels = {'':'全部狀態','pending':'待處理','in_progress':'處理中','resolved':'已解決'} %}
<div class="status-tabs">
  {% for val, label in status_labels.items() %}
  <a href="{{ url_for('notes.index', store=current_store, status=val) }}"
     class="store-tab {% if active_filter == 'status' and current_status == val %}active{% endif %}"
     style="{% if val == 'pending' and active_filter == 'status' and current_status == val %}background:#95a5a6;color:#fff;
            {% elif val == 'in_progress' and active_filter == 'status' and current_status == val %}background:#3498db;color:#fff;
            {% elif val == 'resolved' and active_filter == 'status' and current_status == val %}background:#27ae60;color:#fff;
            {% endif %}">{{ label }}</a>
  {% endfor %}
</div>
```

- [ ] **Step 4: Commit**

```bash
git add app_unified/notes/routes.py app_unified/templates/notes/index.html
git commit -m "feat: 筆記篩選改為互斥模式（優先權/日期/狀態），新增優先權 filter"
```

---

### Task 4: WASM Timeout 15s → 6s

**Files:**
- Modify: `app_unified/wasm/src/lib.rs:12`
- Rebuild: `app_unified/static/wasm/stealth_bg.wasm`

- [ ] **Step 1: Change TIMEOUT_MS in lib.rs**

In `wasm/src/lib.rs`, change line 12:

```rust
const TIMEOUT_MS: f64 = 15000.0;
```

to:

```rust
const TIMEOUT_MS: f64 = 6000.0;
```

- [ ] **Step 2: Rebuild WASM**

```bash
cd /home/hirain0126/projects/webapp/app_unified/wasm && wasm-pack build --target web --out-dir ../static/wasm --out-name stealth
```

- [ ] **Step 3: Commit**

```bash
git add app_unified/wasm/src/lib.rs app_unified/static/wasm/stealth_bg.wasm
git commit -m "feat: stealth vault 超時從 15 秒縮短為 6 秒"
```

---

### Task 5: Remove Tap Animation on Weather Page

**Files:**
- Modify: `app_unified/templates/weather/index.html:57`

- [ ] **Step 1: Add CSS to suppress tap visual feedback**

In `templates/weather/index.html`, change line 57:

```css
    #tap-target { cursor: default; }
```

to:

```css
    #tap-target { cursor: default; -webkit-tap-highlight-color: transparent; user-select: none; outline: none; pointer-events: auto; }
    #tap-target:active, #tap-target:focus { outline: none; background: none; opacity: 1; }
```

- [ ] **Step 2: Commit**

```bash
git add app_unified/templates/weather/index.html
git commit -m "feat: 移除天氣頁面「天」字點擊動畫，確保隱密性"
```

---

### Task 6: Admin Restricted to Own Store

**Files:**
- Modify: `app_unified/notes/routes.py` (index, list_notes, get_note, update_note, delete_note, edit_note, create_note, notes_ai_summary)
- Modify: `app_unified/notes/ws.py` (_list_notes, _create_note, _update_note, _delete_note, _get_note)
- Modify: `app_unified/templates/notes/index.html` (store tabs, AI summary store selector)
- Modify: `app_unified/templates/notes/editor.html` (store selector for admin)
- Modify: `app_unified/admin/routes.py:180-225` (store_summary for admin)

Note: Task 3 already updated `index()` and `list_notes()` with the correct store scoping logic (super_admin sees all, admin sees own store). This task handles the remaining endpoints and frontend.

- [ ] **Step 1: Update `get_note`, `update_note`, `delete_note` in notes/routes.py**

For `get_note` (line 125-145), change:
```python
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
```
to:
```python
    if current_user.is_super_admin():
        note = Note.query.get_or_404(note_id)
    elif current_user.is_admin():
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
```

Apply the same pattern to `update_note` (line 148-193), `delete_note` (line 196-212), and `edit_note` (line 375-384).

- [ ] **Step 2: Update `create_note` store assignment for admin**

In `create_note` (line 98-122), change:
```python
    if current_user.is_admin():
        store = data.get("store") if data.get("store") in stores else None
```
to:
```python
    if current_user.is_super_admin():
        store = data.get("store") if data.get("store") in stores else None
    elif current_user.is_admin():
        store = current_user.store
```

- [ ] **Step 3: Update `notes_ai_summary` for admin store restriction**

In `notes_ai_summary` (line 329-372), after the admin check, add:
```python
    # Admin can only summarize their own store
    if current_user.is_admin() and not current_user.is_super_admin():
        store = current_user.store
```

- [ ] **Step 4: Update WebSocket handlers for admin store scoping**

In `notes/ws.py`, update `_list_notes`, `_create_note`, `_update_note`, `_delete_note`, `_get_note` to use the same pattern:
- `current_user.is_super_admin()` → see all
- `current_user.is_admin()` → filter by `current_user.store`
- else → filter by `current_user.store`

For `_list_notes`:
```python
        if current_user.is_super_admin():
            if store_filter in stores:
                query = query.filter_by(store=store_filter)
        elif current_user.is_admin():
            query = query.filter_by(store=current_user.store)
        else:
            query = query.filter_by(store=current_user.store)
```

For `_create_note`:
```python
        if current_user.is_super_admin():
            store = data.get('store') if data.get('store') in stores else None
        elif current_user.is_admin():
            store = current_user.store
        else:
            store = current_user.store if current_user.store in stores else None
```

For `_update_note`:
```python
        if current_user.is_super_admin():
            note = Note.query.get(note_id)
        elif current_user.is_admin():
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
        else:
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
```

Same pattern for `_delete_note` and `_get_note`.

In `_update_note` store change, replace:
```python
        if 'store' in data and current_user.is_admin():
```
with:
```python
        if 'store' in data and current_user.is_super_admin():
```

- [ ] **Step 5: Update frontend — store tabs only for super_admin**

In `templates/notes/index.html`, change:
```html
{% if current_user.is_admin() %}
<div class="store-tabs">
```
to:
```html
{% if current_user.is_super_admin() %}
<div class="store-tabs">
```

And update the `elif` below it to also show admin's store badge:
```html
{% elif current_user.store %}
<div class="store-tabs">
  <a href="{{ url_for('notes.index') }}" class="store-tab active" data-store="{{ current_user.store }}">{{ current_user.store }} 店</a>
</div>
{% endif %}
```

- [ ] **Step 6: Update AI summary store selector for admin**

In `templates/notes/index.html`, change:
```html
{% if current_user.is_admin() %}
<div class="card" style="margin-bottom:1rem;">
```

The AI summary card should remain visible for both admin and super_admin, but the store selector differs:

```html
{% if current_user.is_admin() %}
<div class="card" style="margin-bottom:1rem;">
  <div style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;">
    <strong style="font-size:.95rem;">🤖 AI 摘要</strong>
    {% if current_user.is_super_admin() %}
    <select id="ai-store-select" style="font-size:.85rem;padding:.3rem .5rem;border-radius:6px;border:1px solid #ddd;min-height:36px;">
      <option value="all">全店</option>
      {% for s in stores %}
      <option value="{{ s }}">{{ s }} 店</option>
      {% endfor %}
    </select>
    {% else %}
    <input type="hidden" id="ai-store-select" value="{{ current_user.store }}">
    <span style="font-size:.85rem;color:#666;">{{ current_user.store }} 店</span>
    {% endif %}
    <select id="ai-days-select" style="font-size:.85rem;padding:.3rem .5rem;border-radius:6px;border:1px solid #ddd;min-height:36px;">
      <option value="1" selected>近 1 天</option>
      <option value="3">近 3 天</option>
      <option value="7">近 1 週</option>
    </select>
    <button class="btn btn-primary" id="btn-ai-summary" onclick="generateSummary()" style="font-size:.85rem;padding:.4rem .8rem;">產生摘要</button>
    <span id="ai-status" style="font-size:.8rem;color:#666;"></span>
  </div>
  <div id="ai-summary-output" style="display:none;background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;padding:1rem;margin-top:.75rem;white-space:pre-wrap;font-size:.88rem;line-height:1.6;"></div>
  <button id="btn-save-summary" class="btn btn-success" style="display:none;margin-top:.5rem;font-size:.85rem;padding:.4rem .8rem;" onclick="saveSummaryAsNote()">💾 儲存為筆記</button>
</div>
{% endif %}
```

- [ ] **Step 7: Update editor store selector for admin**

In `templates/notes/editor.html`, change:
```html
  {% if current_user.is_admin() %}
  <div class="store-selector">
```
to:
```html
  {% if current_user.is_super_admin() %}
  <div class="store-selector">
    <label>店別：</label>
    {% for s in ['B','C','D','E','F','G','J','JJ','K','Q','S'] %}
    <button class="store-btn {% if (note and note.store == s) or (not note and current_user.store == s) %}selected{% endif %}" data-store="{{ s }}" type="button" onclick="selectStore(this)">{{ s }}</button>
    {% endfor %}
  </div>
  {% elif current_user.is_admin() %}
  <div class="store-display">
    店別：
    {% if current_user.store %}
    <span class="store-badge-inline" style="background:var(--store-color-{{ current_user.store }}, #999);">{{ current_user.store }} 店</span>
    {% endif %}
  </div>
```

- [ ] **Step 8: Update admin dashboard AI summary store selector**

In `templates/admin/dashboard.html`, the AI store summary section — for admin, force their store:

Change the AI store select (lines 36-41):
```html
    <select id="ai-store-select" style="font-size:.9rem;padding:.4rem .6rem;border-radius:6px;border:1px solid #ddd;min-height:36px;">
      {% if current_user.is_super_admin() %}
      <option value="all">全店</option>
      {% for s in stores %}
      <option value="{{ s }}">{{ s }} 店</option>
      {% endfor %}
      {% else %}
      <option value="{{ current_user.store }}">{{ current_user.store }} 店</option>
      {% endif %}
    </select>
```

- [ ] **Step 9: Commit**

```bash
git add app_unified/notes/routes.py app_unified/notes/ws.py app_unified/templates/notes/index.html app_unified/templates/notes/editor.html app_unified/templates/admin/dashboard.html
git commit -m "feat: admin 權限限縮為只看本店，super_admin 維持全域"
```

---

### Task 7: Admin/Super_admin Edit Any In-Scope Note + Log

This is already handled by the existing `update_note` + NoteLog logic combined with Task 6's store scoping. No additional backend changes needed.

**Verification only:**

- [ ] **Step 1: Verify edit permission logic**

After Task 6, the permission model is:
- super_admin: `Note.query.get_or_404(note_id)` — can edit any note
- admin: `Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()` — can edit any note in their store
- user: `Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()` — same store filter

The existing `update_note` already sets `note.updated_by = current_user.id` and creates a `NoteLog` with diff. No changes needed.

- [ ] **Step 2: Verify WebSocket `_update_note` also logs**

The existing `_update_note` in `ws.py` already creates `NoteLog` entries with diff. After Task 6's store scoping update, this is correct. No changes needed.

---

### Task 8: Add User Panel in Admin Dashboard

**Files:**
- Modify: `app_unified/templates/admin/dashboard.html` (add new user card)
- Modify: `app_unified/admin/routes.py:77-121` (`create_user` — add role support + store validation)

- [ ] **Step 1: Update `create_user` backend to support role and validate store**

In `admin/routes.py`, update `create_user`:

```python
@admin_bp.route("/users/create", methods=["POST"])
@login_required
def create_user():
    require_admin()
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()
    face_image = data.get("face_image")
    store = (data.get("store") or "").strip()
    role = data.get("role", "user")

    if not username or not pin:
        return jsonify({"status": "error", "message": "請填寫帳號和 PIN"}), 400

    if role not in ("super_admin", "admin", "user"):
        role = "user"

    # admin/user must have a store
    valid_stores = [s.name for s in Store.query.all()]
    if role in ("admin", "user") and store not in valid_stores:
        return jsonify({"status": "error", "message": "admin 和 user 必須選擇店別"}), 400

    if role == "super_admin" and not current_user.is_super_admin():
        return jsonify({"status": "error", "message": "僅 super_admin 可建立此角色"}), 403

    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "帳號已存在"}), 409

    user = User(
        username=username,
        role=role,
        store=store if store in valid_stores else None,
    )
    user.set_password(pin)

    if face_image and FACE_RECOGNITION_AVAILABLE:
        try:
            img_data = base64.b64decode(face_image.split(",")[-1])
            img = face_recognition.load_image_file(io.BytesIO(img_data))
            encodings = face_recognition.face_encodings(img)
            if encodings:
                user.set_face_encoding(encodings[0])
        except Exception:
            pass

    db.session.add(user)
    db.session.flush()

    if face_image:
        try:
            from storage import upload_face_photo
            img_bytes = base64.b64decode(face_image.split(",")[-1])
            key = upload_face_photo(img_bytes, user.id)
            if key:
                user.face_photo_url = key
        except Exception:
            pass

    db.session.commit()
    return jsonify({"status": "ok", "user_id": user.id, "username": user.username})
```

- [ ] **Step 2: Also update `approve_device` to validate store for admin/user roles**

In `admin/routes.py`, in the `approve_device` function, add validation after `role = data.get("role", "user")`:

```python
    if role in ("admin", "user"):
        valid_stores = [s.name for s in Store.query.all()]
        if store not in valid_stores:
            return jsonify({"status": "error", "message": "admin 和 user 必須選擇店別"}), 400
```

- [ ] **Step 3: Add "新增人員" card HTML in dashboard**

In `templates/admin/dashboard.html`, add this card after the "使用者列表" card (after line 102, before the "最近筆記" card):

```html
<div class="card" style="margin-top:1rem;">
  <h3>新增人員</h3>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-top:.75rem;">
    <div>
      <label style="font-size:.85rem;font-weight:600;">帳號名稱</label>
      <input type="text" id="new-user-username" class="form-control">
    </div>
    <div>
      <label style="font-size:.85rem;font-weight:600;">PIN 碼（4位數）</label>
      <input type="password" id="new-user-pin" maxlength="4" inputmode="numeric" class="form-control">
    </div>
    <div>
      <label style="font-size:.85rem;font-weight:600;">店別</label>
      <select id="new-user-store" class="form-control">
        <option value="">— 請選擇 —</option>
        {% for s in stores %}
        <option value="{{ s }}">{{ s }} 店</option>
        {% endfor %}
      </select>
    </div>
    <div>
      <label style="font-size:.85rem;font-weight:600;">權限</label>
      <select id="new-user-role" class="form-control" onchange="toggleNewUserStore(this.value)">
        <option value="user">一般使用者</option>
        <option value="admin">管理員（綁店）</option>
        {% if current_user.is_super_admin() %}
        <option value="super_admin">超級管理員（不綁店）</option>
        {% endif %}
      </select>
    </div>
  </div>
  <div style="margin-top:.75rem;">
    <label style="font-size:.85rem;font-weight:600;">人臉登錄</label>
    <button class="btn btn-secondary" id="new-user-cam-btn" onclick="startNewUserCamera()" style="font-size:.85rem;margin-left:.5rem;">開啟鏡頭</button>
  </div>
  <video id="new-user-video" autoplay playsinline muted style="width:100%;max-width:320px;border-radius:8px;background:#000;display:none;margin-top:.5rem;"></video>
  <canvas id="new-user-canvas" style="display:none;"></canvas>
  <button class="btn btn-secondary" id="new-user-capture-btn" style="display:none;font-size:.85rem;margin-top:.5rem;" onclick="captureNewUserFace()">拍照</button>
  <img id="new-user-preview" style="display:none;width:80px;border-radius:6px;border:2px solid #27ae60;margin-top:.5rem;">
  <div style="margin-top:.75rem;">
    <button class="btn btn-primary" onclick="submitNewUser()" style="min-width:120px;">建立帳號</button>
    <span id="new-user-msg" style="font-size:.9rem;margin-left:.5rem;"></span>
  </div>
</div>
```

- [ ] **Step 4: Add JavaScript for the new user panel**

In the `<script>` section of `dashboard.html`, add:

```javascript
var newUserStream = null;
var newUserFaceImage = null;

function toggleNewUserStore(role) {
  var storeSelect = document.getElementById('new-user-store');
  if (role === 'super_admin') {
    storeSelect.value = '';
    storeSelect.disabled = true;
  } else {
    storeSelect.disabled = false;
  }
}

function startNewUserCamera() {
  var video = document.getElementById('new-user-video');
  video.style.display = 'block';
  document.getElementById('new-user-capture-btn').style.display = 'inline-block';
  document.getElementById('new-user-cam-btn').disabled = true;
  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
    .catch(function() { return navigator.mediaDevices.getUserMedia({ video: true, audio: false }); })
    .then(function(s) { newUserStream = s; video.srcObject = s; })
    .catch(function() { document.getElementById('new-user-msg').textContent = '無法開啟鏡頭'; });
}

function captureNewUserFace() {
  var video = document.getElementById('new-user-video');
  var canvas = document.getElementById('new-user-canvas');
  if (!newUserStream || video.readyState < 2) return;
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);
  newUserFaceImage = canvas.toDataURL('image/jpeg', 0.85);
  var preview = document.getElementById('new-user-preview');
  preview.src = newUserFaceImage;
  preview.style.display = 'block';
}

function submitNewUser() {
  var username = document.getElementById('new-user-username').value.trim();
  var pin = document.getElementById('new-user-pin').value.trim();
  var store = document.getElementById('new-user-store').value;
  var role = document.getElementById('new-user-role').value;
  var msgEl = document.getElementById('new-user-msg');

  if (!username || !pin) { msgEl.textContent = '請填寫帳號和 PIN'; msgEl.style.color = '#dc3545'; return; }
  if (role !== 'super_admin' && !store) { msgEl.textContent = 'admin 和 user 必須選擇店別'; msgEl.style.color = '#dc3545'; return; }

  msgEl.textContent = '建立中…';
  msgEl.style.color = '#666';

  fetch('/admin/users/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username, pin: pin, store: store, role: role, face_image: newUserFaceImage })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.status === 'ok') {
      msgEl.textContent = '帳號建立成功！';
      msgEl.style.color = '#28a745';
      if (newUserStream) { newUserStream.getTracks().forEach(function(t) { t.stop(); }); newUserStream = null; }
      setTimeout(function() { location.reload(); }, 1200);
    } else {
      msgEl.textContent = data.message || '建立失敗';
      msgEl.style.color = '#dc3545';
    }
  }).catch(function() { msgEl.textContent = '連線錯誤'; msgEl.style.color = '#dc3545'; });
}
```

- [ ] **Step 5: Also add store validation to approve modal JS**

In `submitApprove()`, add validation before the fetch:

```javascript
  var role = document.getElementById('approve-role').value;
  if (role !== 'super_admin' && !store) { msgEl.textContent = 'admin 和 user 必須選擇店別'; msgEl.style.color = '#dc3545'; return; }
```

- [ ] **Step 6: Commit**

```bash
git add app_unified/admin/routes.py app_unified/templates/admin/dashboard.html
git commit -m "feat: 管理頁面新增「新增人員」區塊，含帳號/PIN/店別/權限/人臉"
```

---

### Task 9: Multi-User Login on Same Device

**Files:**
- Modify: `app_unified/device/routes.py:10-30` (`is_device_authorized`)

- [ ] **Step 1: Simplify `is_device_authorized` to check device only**

Replace the function:

```python
def is_device_authorized(fp):
    """檢查設備是否已授權且未掛失（不限定綁定使用者）"""
    if not fp:
        return False
    device = TrustedDevice.query.filter_by(fingerprint=fp).first()
    if not device or not device.is_approved or device.is_revoked:
        return False
    return True
```

The store OFF check and user active check are already handled in `/auth/verify` at login time — the device itself just needs to be approved and not revoked.

- [ ] **Step 2: Verify `/auth/verify` already supports any user**

The existing `verify()` in `auth/routes.py` already:
1. Gets all active users: `User.query.filter_by(is_active=True).all()`
2. Filters by PIN match
3. Compares face against all PIN-matched users
4. Checks store login_enabled for the matched user

This already works for multi-user login — any active user whose PIN and face match will be logged in regardless of which device they're on. No changes needed.

- [ ] **Step 3: Commit**

```bash
git add app_unified/device/routes.py
git commit -m "feat: 設備授權改為只檢查設備本身，支援同設備多人登入"
```

---

## Summary of All Files Modified

| File | Tasks |
|------|-------|
| `notes/routes.py` | 1, 3, 6 |
| `notes/ws.py` | 1, 6 |
| `templates/notes/index.html` | 1, 2, 3, 6 |
| `templates/notes/editor.html` | 2, 6 |
| `templates/weather/index.html` | 5 |
| `templates/admin/dashboard.html` | 6, 8 |
| `admin/routes.py` | 8 |
| `device/routes.py` | 9 |
| `wasm/src/lib.rs` | 4 |
