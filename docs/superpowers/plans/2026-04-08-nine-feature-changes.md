# 九項功能修改實作計劃

> **自動化執行指引：** 建議使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 逐步執行此計劃。步驟使用核取方塊 (`- [ ]`) 追蹤進度。

**目標：** 實作 9 項功能修改，涵蓋 AI 摘要時間邏輯、UI 調整、篩選器改版、隱身金庫計時、管理員權限、使用者管理、多人登入。

**架構：** 所有修改皆在現有 Flask 應用 `/home/hirain0126/projects/webapp/app_unified/`。後端修改 `notes/routes.py`、`notes/ws.py`、`device/routes.py`、`admin/routes.py`、`wasm/src/lib.rs`。前端修改 `templates/notes/` 與 `templates/admin/` 下的模板。各項修改大致獨立，可依序實作。

**技術棧：** Python/Flask、Jinja2 模板、原生 JS、Rust/WASM、PostgreSQL + SQLAlchemy

---

### 任務 1：AI 摘要「今天」改為營業日 08:00-08:00

**檔案：**
- 修改：`app_unified/notes/routes.py:21-27`（`_date_filter` 函式）
- 修改：`app_unified/notes/routes.py:329-372`（`notes_ai_summary` 函式）
- 修改：`app_unified/notes/ws.py:51-57`（WebSocket `_list_notes` 日期邏輯）
- 修改：`app_unified/templates/notes/index.html:230-237`（`saveSummaryAsNote` 日期標題）

- [ ] **步驟 1：在 notes/routes.py 新增營業日輔助函式**

在 `RANGE_DAYS` 字典（第 11 行）之後、`_ai_tasks` 之前加入：

```python
from datetime import datetime, timedelta, timezone

_TW = timezone(timedelta(hours=8))


def _get_business_day_range():
    """回傳目前營業日的 (start, end)，以 UTC 表示。
    營業日定義：台灣時間 08:00 ~ 隔天 08:00
    若現在（台灣時間）>= 08:00：當天 08:00 ~ 隔天 08:00
    若現在（台灣時間）< 08:00：前一天 08:00 ~ 當天 08:00
    """
    now_tw = datetime.now(_TW)
    if now_tw.hour >= 8:
        start_tw = now_tw.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        start_tw = (now_tw - timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    end_tw = start_tw + timedelta(days=1)
    # 轉換為 UTC 以利 DB 查詢
    start_utc = start_tw.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_tw.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _get_business_day_label():
    """回傳營業日的日期字串（YYYY-MM-DD），供顯示用。"""
    now_tw = datetime.now(_TW)
    if now_tw.hour >= 8:
        return now_tw.strftime("%Y-%m-%d")
    else:
        return (now_tw - timedelta(days=1)).strftime("%Y-%m-%d")
```

- [ ] **步驟 2：更新 `_date_filter` 使用營業日邏輯**

取代現有 `_date_filter` 函式：

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

- [ ] **步驟 3：更新 `notes_ai_summary` 的 days=1 邏輯**

在 `notes_ai_summary()` 中，將：
```python
    since = datetime.utcnow() - timedelta(days=days)
```
改為：
```python
    if days == 1:
        start_utc, end_utc = _get_business_day_range()
    else:
        start_utc = datetime.utcnow() - timedelta(days=days)
        end_utc = None
```

並將查詢從：
```python
    query = Note.query.filter(Note.updated_at >= since)
```
改為：
```python
    query = Note.query.filter(Note.updated_at >= start_utc)
    if end_utc:
        query = query.filter(Note.updated_at < end_utc)
```

- [ ] **步驟 4：更新 WebSocket `_list_notes` 日期邏輯**

在 `notes/ws.py` 中，將第 51-57 行：

```python
        range_days = {'today': 0, '3d': 3, '5d': 5, '7d': 7}
        days = range_days.get(range_param, 3)
        if days == 0:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Note.updated_at >= since)
```

改為：

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

- [ ] **步驟 5：更新前端 `saveSummaryAsNote` 日期標題**

在 `templates/notes/index.html` 中，將 `saveSummaryAsNote` 的日期邏輯（第 234-237 行）：

```javascript
  var today = new Date();
  var dateStr = today.getFullYear() + '-' +
    String(today.getMonth() + 1).padStart(2, '0') + '-' +
    String(today.getDate()).padStart(2, '0');
```

改為：

```javascript
  var now = new Date();
  var twHour = (now.getUTCHours() + 8) % 24;
  var bizDate = new Date(now.getTime() + 8 * 3600000);
  if (twHour < 8) bizDate.setDate(bizDate.getDate() - 1);
  var dateStr = bizDate.getFullYear() + '-' +
    String(bizDate.getMonth() + 1).padStart(2, '0') + '-' +
    String(bizDate.getDate()).padStart(2, '0');
```

- [ ] **步驟 6：提交**

```bash
git add app_unified/notes/routes.py app_unified/notes/ws.py app_unified/templates/notes/index.html
git commit -m "feat: AI摘要與筆記列表「今天」改為營業日 08:00-08:00"
```

---

### 任務 2：放大筆記中的作者與時間字體

**檔案：**
- 修改：`app_unified/templates/notes/index.html:134`
- 修改：`app_unified/templates/notes/editor.html:41`

- [ ] **步驟 1：放大筆記卡片的作者/時間文字**

在 `templates/notes/index.html` 中，將第 134 行：

```html
      <span style="font-size:.72rem;color:#bbb;">{{ note.author.username if note.author else '—' }} · {{ note.created_at | fmt_date }}</span>
```

改為：

```html
      <span style="font-size:.85rem;color:#888;font-weight:600;">{{ note.author.username if note.author else '—' }} · {{ note.created_at | fmt_date }}</span>
```

- [ ] **步驟 2：放大編輯器的修改者資訊**

在 `templates/notes/editor.html` 中，將第 41 行：

```css
.updated-by-info { font-size: .78rem; color: #aaa; margin-bottom: .5rem; }
```

改為：

```css
.updated-by-info { font-size: .85rem; color: #888; margin-bottom: .5rem; }
```

- [ ] **步驟 3：提交**

```bash
git add app_unified/templates/notes/index.html app_unified/templates/notes/editor.html
git commit -m "feat: 放大筆記卡片作者/時間字體至 0.85rem"
```

---

### 任務 3：篩選器改為互斥模式（優先權 / 日期範圍 / 狀態）

**檔案：**
- 修改：`app_unified/notes/routes.py:30-54`（`index` 函式）
- 修改：`app_unified/notes/routes.py:68-95`（`list_notes` 函式）
- 修改：`app_unified/templates/notes/index.html:98-117`（篩選器 tabs）

- [ ] **步驟 1：更新後端 `index()` 支援互斥篩選**

取代 `index` 函式：

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

    # 店別範圍（始終套用）
    if current_user.is_super_admin():
        if store_filter in stores:
            query = query.filter_by(store=store_filter)
    elif current_user.is_admin():
        query = query.filter_by(store=current_user.store)
    else:
        query = query.filter_by(store=current_user.store)

    # 互斥篩選：優先權、狀態、日期範圍，一次只套用一組
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

- [ ] **步驟 2：同樣更新 `list_notes` API**

取代 `list_notes` 函式：

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

- [ ] **步驟 3：更新前端篩選器 tabs 為互斥模式 + 新增優先權 tabs**

在 `templates/notes/index.html` 中，取代狀態 tabs 與日期範圍 tabs 區段（第 98-117 行）：

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

- [ ] **步驟 4：提交**

```bash
git add app_unified/notes/routes.py app_unified/templates/notes/index.html
git commit -m "feat: 筆記篩選改為互斥模式（優先權/日期/狀態），新增優先權 filter"
```

---

### 任務 4：WASM 超時從 15 秒改為 6 秒

**檔案：**
- 修改：`app_unified/wasm/src/lib.rs:12`
- 重建：`app_unified/static/wasm/stealth_bg.wasm`

- [ ] **步驟 1：修改 lib.rs 的 TIMEOUT_MS**

在 `wasm/src/lib.rs` 中，將第 12 行：

```rust
const TIMEOUT_MS: f64 = 15000.0;
```

改為：

```rust
const TIMEOUT_MS: f64 = 6000.0;
```

- [ ] **步驟 2：重新編譯 WASM**

```bash
cd /home/hirain0126/projects/webapp/app_unified/wasm && wasm-pack build --target web --out-dir ../static/wasm --out-name stealth
```

- [ ] **步驟 3：提交**

```bash
git add app_unified/wasm/src/lib.rs app_unified/static/wasm/stealth_bg.wasm
git commit -m "feat: 隱身金庫超時從 15 秒縮短為 6 秒"
```

---

### 任務 5：移除天氣頁面「天」字點擊動畫

**檔案：**
- 修改：`app_unified/templates/weather/index.html:57`

- [ ] **步驟 1：加入 CSS 隱藏所有點擊視覺回饋**

在 `templates/weather/index.html` 中，將第 57 行：

```css
    #tap-target { cursor: default; }
```

改為：

```css
    #tap-target { cursor: default; -webkit-tap-highlight-color: transparent; user-select: none; outline: none; pointer-events: auto; }
    #tap-target:active, #tap-target:focus { outline: none; background: none; opacity: 1; }
```

- [ ] **步驟 2：提交**

```bash
git add app_unified/templates/weather/index.html
git commit -m "feat: 移除天氣頁面「天」字點擊動畫，確保隱密性"
```

---

### 任務 6：Admin 權限限縮為只看本店

**檔案：**
- 修改：`app_unified/notes/routes.py`（get_note、update_note、delete_note、edit_note、create_note、notes_ai_summary）
- 修改：`app_unified/notes/ws.py`（_list_notes、_create_note、_update_note、_delete_note、_get_note）
- 修改：`app_unified/templates/notes/index.html`（店別 tabs、AI 摘要店別選擇器）
- 修改：`app_unified/templates/notes/editor.html`（admin 店別選擇器）
- 修改：`app_unified/templates/admin/dashboard.html`（AI 摘要店別選擇器）

備註：任務 3 已將 `index()` 和 `list_notes()` 更新為正確的店別範圍邏輯（super_admin 看全部、admin 看本店）。此任務處理其餘端點和前端。

- [ ] **步驟 1：更新 notes/routes.py 中的 `get_note`、`update_note`、`delete_note`**

對 `get_note`（第 125-145 行），將：
```python
    if current_user.is_admin():
        note = Note.query.get_or_404(note_id)
```
改為：
```python
    if current_user.is_super_admin():
        note = Note.query.get_or_404(note_id)
    elif current_user.is_admin():
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
```

對 `update_note`（第 148-193 行）、`delete_note`（第 196-212 行）、`edit_note`（第 375-384 行）套用相同模式。

- [ ] **步驟 2：更新 `create_note` 的 admin 店別指定**

在 `create_note`（第 98-122 行）中，將：
```python
    if current_user.is_admin():
        store = data.get("store") if data.get("store") in stores else None
```
改為：
```python
    if current_user.is_super_admin():
        store = data.get("store") if data.get("store") in stores else None
    elif current_user.is_admin():
        store = current_user.store
```

- [ ] **步驟 3：更新 `notes_ai_summary` 的 admin 店別限制**

在 `notes_ai_summary`（第 329-372 行）中，admin 檢查之後加入：
```python
    # Admin 只能摘要自己的店
    if current_user.is_admin() and not current_user.is_super_admin():
        store = current_user.store
```

- [ ] **步驟 4：更新 WebSocket 處理器的 admin 店別範圍**

在 `notes/ws.py` 中，更新 `_list_notes`、`_create_note`、`_update_note`、`_delete_note`、`_get_note` 使用相同模式：
- `current_user.is_super_admin()` → 看全部
- `current_user.is_admin()` → 過濾 `current_user.store`
- 否則 → 過濾 `current_user.store`

`_list_notes`：
```python
        if current_user.is_super_admin():
            if store_filter in stores:
                query = query.filter_by(store=store_filter)
        elif current_user.is_admin():
            query = query.filter_by(store=current_user.store)
        else:
            query = query.filter_by(store=current_user.store)
```

`_create_note`：
```python
        if current_user.is_super_admin():
            store = data.get('store') if data.get('store') in stores else None
        elif current_user.is_admin():
            store = current_user.store
        else:
            store = current_user.store if current_user.store in stores else None
```

`_update_note`：
```python
        if current_user.is_super_admin():
            note = Note.query.get(note_id)
        elif current_user.is_admin():
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
        else:
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
```

`_delete_note` 和 `_get_note` 套用同樣模式。

`_update_note` 中的店別修改，將：
```python
        if 'store' in data and current_user.is_admin():
```
改為：
```python
        if 'store' in data and current_user.is_super_admin():
```

- [ ] **步驟 5：更新前端 — 店別 tabs 僅限 super_admin**

在 `templates/notes/index.html` 中，將：
```html
{% if current_user.is_admin() %}
<div class="store-tabs">
```
改為：
```html
{% if current_user.is_super_admin() %}
<div class="store-tabs">
```

其下的 `elif` 改為也顯示 admin 的店別標章：
```html
{% elif current_user.store %}
<div class="store-tabs">
  <a href="{{ url_for('notes.index') }}" class="store-tab active" data-store="{{ current_user.store }}">{{ current_user.store }} 店</a>
</div>
{% endif %}
```

- [ ] **步驟 6：更新 AI 摘要店別選擇器**

在 `templates/notes/index.html` 中，AI 摘要卡片應區分 super_admin 和 admin：

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

- [ ] **步驟 7：更新編輯器店別選擇器**

在 `templates/notes/editor.html` 中，將：
```html
  {% if current_user.is_admin() %}
  <div class="store-selector">
```
改為：
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

- [ ] **步驟 8：更新管理後台 AI 摘要店別選擇器**

在 `templates/admin/dashboard.html` 中，AI 店別選擇器（第 36-41 行）改為：

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

- [ ] **步驟 9：提交**

```bash
git add app_unified/notes/routes.py app_unified/notes/ws.py app_unified/templates/notes/index.html app_unified/templates/notes/editor.html app_unified/templates/admin/dashboard.html
git commit -m "feat: admin 權限限縮為只看本店，super_admin 維持全域"
```

---

### 任務 7：Super_admin/Admin 可修改任何（本店內）筆記 + Log

此功能已由現有的 `update_note` + NoteLog 邏輯搭配任務 6 的店別範圍處理完成。無需額外後端修改。

**僅需驗證：**

- [ ] **步驟 1：確認編輯權限邏輯**

任務 6 完成後，權限模型為：
- super_admin：`Note.query.get_or_404(note_id)` — 可編輯任何筆記
- admin：`Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()` — 可編輯本店任何筆記
- user：`Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()` — 同店篩選

現有 `update_note` 已設定 `note.updated_by = current_user.id` 並建立 `NoteLog` 記錄 diff。無需修改。

- [ ] **步驟 2：確認 WebSocket `_update_note` 也有記錄**

現有 `notes/ws.py` 的 `_update_note` 已建立 `NoteLog` 記錄 diff。任務 6 的店別範圍更新後即正確。無需修改。

---

### 任務 8：管理頁面新增人員區塊

**檔案：**
- 修改：`app_unified/templates/admin/dashboard.html`（新增「新增人員」卡片）
- 修改：`app_unified/admin/routes.py:77-121`（`create_user` — 新增角色支援 + 店別驗證）

- [ ] **步驟 1：更新 `create_user` 後端以支援角色與驗證店別**

在 `admin/routes.py` 中，取代 `create_user` 函式：

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

    # admin/user 必須選擇店別
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

- [ ] **步驟 2：同時更新 `approve_device` 的店別驗證**

在 `admin/routes.py` 的 `approve_device` 函式中，在 `role = data.get("role", "user")` 之後加入：

```python
    if role in ("admin", "user"):
        valid_stores = [s.name for s in Store.query.all()]
        if store not in valid_stores:
            return jsonify({"status": "error", "message": "admin 和 user 必須選擇店別"}), 400
```

- [ ] **步驟 3：在 dashboard 新增「新增人員」卡片 HTML**

在 `templates/admin/dashboard.html` 中，在「使用者列表」卡片之後（第 102 行之後）、「最近筆記」卡片之前加入：

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

- [ ] **步驟 4：新增「新增人員」面板的 JavaScript**

在 `dashboard.html` 的 `<script>` 區段中加入：

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

- [ ] **步驟 5：在設備核准 modal 的 JS 中也加入店別驗證**

在 `submitApprove()` 中，fetch 之前加入：

```javascript
  var role = document.getElementById('approve-role').value;
  if (role !== 'super_admin' && !store) { msgEl.textContent = 'admin 和 user 必須選擇店別'; msgEl.style.color = '#dc3545'; return; }
```

- [ ] **步驟 6：提交**

```bash
git add app_unified/admin/routes.py app_unified/templates/admin/dashboard.html
git commit -m "feat: 管理頁面新增「新增人員」區塊，含帳號/PIN/店別/權限/人臉"
```

---

### 任務 9：同一設備支援多人登入

**檔案：**
- 修改：`app_unified/device/routes.py:10-30`（`is_device_authorized`）

- [ ] **步驟 1：簡化 `is_device_authorized` 為僅檢查設備狀態**

取代該函式：

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

店別 OFF 檢查和使用者啟用狀態檢查已在 `/auth/verify` 登入時處理 — 設備本身只需是已核准且未掛失即可。

- [ ] **步驟 2：確認 `/auth/verify` 已支援任意使用者**

現有 `auth/routes.py` 的 `verify()` 已經：
1. 取得所有啟用使用者：`User.query.filter_by(is_active=True).all()`
2. 依 PIN 篩選
3. 將人臉與所有 PIN 符合的使用者比對
4. 檢查符合使用者的店別 login_enabled

這已支援多人登入 — 只要 PIN 和人臉符合的啟用使用者即可登入，不限綁定的設備。無需修改。

- [ ] **步驟 3：提交**

```bash
git add app_unified/device/routes.py
git commit -m "feat: 設備授權改為只檢查設備本身，支援同設備多人登入"
```

---

## 所有修改檔案彙整

| 檔案 | 涉及任務 |
|------|----------|
| `notes/routes.py` | 1、3、6 |
| `notes/ws.py` | 1、6 |
| `templates/notes/index.html` | 1、2、3、6 |
| `templates/notes/editor.html` | 2、6 |
| `templates/weather/index.html` | 5 |
| `templates/admin/dashboard.html` | 6、8 |
| `admin/routes.py` | 8 |
| `device/routes.py` | 9 |
| `wasm/src/lib.rs` | 4 |
