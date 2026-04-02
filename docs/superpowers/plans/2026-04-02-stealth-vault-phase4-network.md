# Stealth Vault Phase 4: 網路層隱身 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notes 通訊改走 WebSocket 加密隧道 + 1KB/s 恆定流量填充，讓 Wireshark 無法區分天氣瀏覽和筆記操作。

**Architecture:** 加入 flask-socketio + gevent，Notes CRUD 和 AI 摘要全部走 WebSocket 事件（通用名稱 `d`/`r`/`p`），HTTP endpoints 保留作為 fallback。gunicorn worker 從 sync 改為 geventwebsocket。base.html 載入 socket.io client 並啟動流量填充。

**Tech Stack:** flask-socketio, gevent, gevent-websocket, socket.io client JS

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app_unified/requirements.txt` | Modify | 加 flask-socketio, gevent, gevent-websocket |
| `app_unified/extensions.py` | Modify | 加 SocketIO 實例 |
| `app_unified/app.py` | Modify | 初始化 SocketIO |
| `app_unified/wsgi.py` | Modify | 用 SocketIO run |
| `app_unified/gunicorn.conf.py` | Modify | worker_class 改 geventwebsocket.gunicorn.workers.GeventWebSocketWorker |
| `app_unified/notes/ws.py` | Create | WebSocket 事件處理（Notes CRUD + AI 摘要）|
| `app_unified/templates/base.html` | Modify | 載入 socket.io client + 流量填充 + WS 連接 |
| `app_unified/templates/notes/index.html` | Modify | AI 摘要改用 WS |
| `app_unified/templates/notes/editor.html` | Modify | save/delete 改用 WS |
| `app_unified/static/sw.js` | Modify | cache v9 |

---

### Task 1: 後端依賴 + SocketIO 初始化

**Files:**
- Modify: `app_unified/requirements.txt`
- Modify: `app_unified/extensions.py`
- Modify: `app_unified/app.py`
- Modify: `app_unified/wsgi.py`
- Modify: `app_unified/gunicorn.conf.py`

- [ ] **Step 1: 加入依賴**

在 `app_unified/requirements.txt` 末尾加入：

```
flask-socketio>=5.3
gevent>=23.0
gevent-websocket>=0.10
```

- [ ] **Step 2: extensions.py 加 SocketIO**

在 `app_unified/extensions.py` 末尾加入：

```python
from flask_socketio import SocketIO

socketio = SocketIO()
```

- [ ] **Step 3: app.py 初始化 SocketIO**

在 `app_unified/app.py` 的 import 區加入：

```python
from extensions import db, login_manager, limiter, socketio
```

在 `limiter.init_app(app)` 之後加入：

```python
    socketio.init_app(app, cors_allowed_origins="*", async_mode="gevent")
```

在 blueprint 註冊之後、`return app` 之前加入：

```python
    from notes.ws import register_ws_events
    register_ws_events(socketio)
```

- [ ] **Step 4: wsgi.py 加入 socketio import**

在 `app_unified/wsgi.py` 的 `app = create_app()` 之後加入：

```python
from extensions import socketio
```

- [ ] **Step 5: gunicorn.conf.py 改 worker class**

將 `app_unified/gunicorn.conf.py` 的 `worker_class = "sync"` 改為：

```python
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
```

同時移除 `preload_app = True`（gevent worker 不需要 preload）。

- [ ] **Step 6: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/requirements.txt app_unified/extensions.py app_unified/app.py app_unified/wsgi.py app_unified/gunicorn.conf.py
git commit -m "feat: add flask-socketio + gevent, initialize SocketIO"
```

---

### Task 2: WebSocket 事件處理（Notes CRUD + AI 摘要）

**Files:**
- Create: `app_unified/notes/ws.py`

- [ ] **Step 1: 建立 ws.py**

建立 `app_unified/notes/ws.py`：

```python
from datetime import datetime, timedelta
from flask import request
from flask_login import current_user
from flask_socketio import emit
from extensions import db
from models import Note, Store, NoteLog, User, STATUS_CHOICES, PRIORITY_CHOICES


def register_ws_events(socketio):
    """註冊所有 WebSocket 事件"""

    @socketio.on('connect')
    def handle_connect():
        if not current_user.is_authenticated:
            return False  # 拒絕未認證連接

    @socketio.on('d')
    def handle_data(data):
        """通用數據請求處理"""
        if not current_user.is_authenticated:
            emit('r', {'op': 'er', 'message': 'unauthorized'})
            return

        op = data.get('op', '')
        try:
            if op == 'ln':
                _list_notes(data)
            elif op == 'cn':
                _create_note(data)
            elif op == 'un':
                _update_note(data)
            elif op == 'dn':
                _delete_note(data)
            elif op == 'gn':
                _get_note(data)
            elif op == 'as':
                _ai_summary(data)
            else:
                emit('r', {'op': 'er', 'message': 'unknown op'})
        except Exception as e:
            emit('r', {'op': 'er', 'message': str(e)})

    @socketio.on('p')
    def handle_padding(data):
        """流量填充 — 收到 padding 不做任何事"""
        pass

    def _get_stores():
        return [s.name for s in Store.query.order_by(Store.name).all()]

    def _list_notes(data):
        store_filter = data.get('store', '')
        status_filter = data.get('status', '')
        range_param = data.get('range', '3d')
        stores = _get_stores()

        query = Note.query
        if store_filter in stores:
            query = query.filter_by(store=store_filter)

        range_days = {'today': 0, '3d': 3, '5d': 5, '7d': 7}
        days = range_days.get(range_param, 3)
        if days == 0:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Note.updated_at >= since)

        if status_filter in STATUS_CHOICES:
            query = query.filter_by(status=status_filter)

        notes = query.order_by(Note.updated_at.desc()).all()
        emit('r', {'op': 'ln', 'notes': [{
            'id': n.id, 'title': n.title, 'content': n.content,
            'store': n.store, 'status': n.status or 'pending',
            'priority': n.priority or 'medium',
            'author': n.author.username if n.author else '',
            'created_at': n.created_at.isoformat() if n.created_at else '',
            'updated_at': n.updated_at.isoformat() if n.updated_at else '',
        } for n in notes]})

    def _create_note(data):
        stores = _get_stores()
        now = datetime.utcnow()
        if current_user.is_admin():
            store = data.get('store') if data.get('store') in stores else None
        else:
            store = current_user.store if current_user.store in stores else None
        status = data.get('status') if data.get('status') in STATUS_CHOICES else 'pending'
        priority = data.get('priority') if data.get('priority') in PRIORITY_CHOICES else 'medium'
        note = Note(
            user_id=current_user.id,
            title=data.get('title', '未命名筆記'),
            content=data.get('content', ''),
            store=store, status=status, priority=priority,
            created_at=now, updated_at=now,
        )
        db.session.add(note)
        db.session.commit()
        emit('r', {'op': 'cn', 'status': 'ok', 'id': note.id})

    def _update_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return

        stores = _get_stores()
        diff_parts = []
        if 'title' in data and data['title'] != note.title:
            diff_parts.append(f"標題: {note.title} → {data['title']}")
            note.title = data['title']
        if 'content' in data and data['content'] != note.content:
            diff_parts.append(f"內容長度: {len(note.content)} → {len(data['content'])} 字")
            note.content = data['content']
        if 'store' in data and current_user.is_admin():
            note.store = data['store'] if data['store'] in stores else None
        if 'status' in data and data['status'] in STATUS_CHOICES:
            if data['status'] != note.status:
                diff_parts.append(f"狀態: {note.status} → {data['status']}")
            note.status = data['status']
        if 'priority' in data and data['priority'] in PRIORITY_CHOICES:
            if data['priority'] != note.priority:
                diff_parts.append(f"優先度: {note.priority} → {data['priority']}")
            note.priority = data['priority']

        note.updated_by = current_user.id
        note.updated_at = datetime.utcnow()
        db.session.flush()

        if diff_parts:
            log = NoteLog(
                note_id=note.id, note_title=note.title,
                user_id=current_user.id, action='edit',
                diff='; '.join(diff_parts),
            )
            db.session.add(log)

        db.session.commit()
        emit('r', {'op': 'un', 'status': 'ok'})

    def _delete_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return
        log = NoteLog(
            note_id=note.id, note_title=note.title,
            user_id=current_user.id, action='delete',
        )
        db.session.add(log)
        db.session.delete(note)
        db.session.commit()
        emit('r', {'op': 'dn', 'status': 'ok'})

    def _get_note(data):
        note_id = data.get('id')
        if current_user.is_admin():
            note = Note.query.get(note_id)
        else:
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return
        updater = None
        if note.updated_by:
            u = User.query.get(note.updated_by)
            updater = u.username if u else None
        emit('r', {'op': 'gn', 'note': {
            'id': note.id, 'title': note.title, 'content': note.content,
            'store': note.store, 'status': note.status or 'pending',
            'priority': note.priority or 'medium',
            'updated_by': updater,
            'created_at': note.created_at.isoformat() if note.created_at else '',
            'updated_at': note.updated_at.isoformat() if note.updated_at else '',
        }})

    def _ai_summary(data):
        if not current_user.is_admin():
            emit('r', {'op': 'er', 'message': '僅限管理員'})
            return

        from admin.routes import call_llm
        store = data.get('store', 'all')
        days = int(data.get('days', 7))
        since = datetime.utcnow() - timedelta(days=days)

        valid_stores = [s.name for s in Store.query.all()]
        query = Note.query.filter(Note.updated_at >= since)
        if store != 'all' and store in valid_stores:
            query = query.filter_by(store=store)
        notes = query.order_by(Note.store, Note.updated_at.desc()).all()

        if not notes:
            emit('r', {'op': 'as', 'status': 'ok', 'summary': '（近期無筆記）'})
            return

        STATUS_LABELS = {'pending': '待處理', 'in_progress': '處理中', 'resolved': '已解決'}
        PRIORITY_LABELS = {'high': '高', 'medium': '中', 'low': '低'}
        lines = []
        for n in notes:
            s_label = STATUS_LABELS.get(n.status or 'pending', n.status)
            p_label = PRIORITY_LABELS.get(n.priority or 'medium', n.priority)
            store_tag = f"[{n.store}店]" if n.store else "[未分店]"
            author = n.author.username if n.author else "?"
            date_str = n.updated_at.strftime("%m/%d") if n.updated_at else ""
            lines.append(f"{store_tag}[{date_str}][{author}][{s_label}][優先:{p_label}] {n.title}\n{n.content}")

        store_label = f"「{store}店」" if store != 'all' else "全店"
        if store == 'all':
            prompt = (
                f"以下是{store_label}近 {days} 天的員工筆記：\n\n"
                + "\n---\n".join(lines)
                + "\n\n請用繁體中文，依以下結構整理：\n"
                "1. 第一層：依「店別」分類\n"
                "2. 第二層：每間店內依「優先權」排列（高→中→低）\n"
                "3. 相關的事項請合併成一條摘要，不要逐條列出\n"
                "4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n"
                "請用 Markdown 格式回覆。"
            )
        else:
            prompt = (
                f"以下是{store_label}近 {days} 天的員工筆記：\n\n"
                + "\n---\n".join(lines)
                + f"\n\n請用繁體中文，依以下結構整理：\n"
                f"1. 先標明這是「{store}店」的摘要\n"
                "2. 依「優先權」排列（高→中→低）\n"
                "3. 相關的事項請合併成一條摘要，不要逐條列出\n"
                "4. 最後給主管一個「建議優先處理順序」，說明應該先處理哪件事、為什麼\n"
                "請用 Markdown 格式回覆。"
            )

        try:
            summary = call_llm(prompt, max_tokens=2048)
            emit('r', {'op': 'as', 'status': 'ok', 'summary': summary})
        except Exception as e:
            emit('r', {'op': 'er', 'message': str(e)})
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/notes/ws.py
git commit -m "feat: WebSocket event handlers for Notes CRUD and AI summary"
```

---

### Task 3: 前端 WebSocket 連接 + 流量填充

**Files:**
- Modify: `app_unified/templates/base.html`

- [ ] **Step 1: 在 base.html 加入 socket.io client + WS 連接 + 流量填充**

在 `base.html` 的 `{% block scripts %}{% endblock %}` 之前加入 socket.io CDN：

```html
  <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
```

在 5 分鐘無操作自動登出的 `})();` 之後、`</script>` 之前加入：

```javascript
    // ── WebSocket 連接 + 流量填充 ──
    (function() {
      if (typeof io === 'undefined') return;
      var _ws = io({ transports: ['websocket'] });
      window._ws = _ws;

      // 流量填充：每秒發送 1KB 隨機數據
      var _pd = '';
      for (var i = 0; i < 1024; i++) _pd += String.fromCharCode(Math.floor(Math.random() * 26) + 97);
      setInterval(function() {
        if (_ws.connected) _ws.emit('p', _pd);
      }, 1000);
    })();
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/templates/base.html
git commit -m "feat: socket.io client + 1KB/s traffic padding in base.html"
```

---

### Task 4: 筆記編輯頁改用 WebSocket

**Files:**
- Modify: `app_unified/templates/notes/editor.html`

- [ ] **Step 1: 修改 doSave 和 doDelete 改用 WebSocket**

將 `doSave()` 函式替換為：

```javascript
function doSave() {
  var title = document.getElementById('title-input').value.trim() || '未命名筆記';
  var content = document.getElementById('content-area').value;
  var store = currentStore || null;
  var statusEl = document.getElementById('save-status');
  var saveBtn = document.getElementById('btn-save');
  statusEl.textContent = '儲存中…';
  saveBtn.disabled = true;

  if (window._ws && window._ws.connected) {
    var op = NOTE_ID ? 'un' : 'cn';
    var payload = { op: op, title: title, content: content, store: store, status: currentStatus, priority: currentPriority };
    if (NOTE_ID) payload.id = NOTE_ID;
    window._ws.emit('d', payload);
    window._ws.once('r', function(data) {
      if (data.op === op && (data.status === 'ok' || data.id)) {
        window.location.href = '/notes/';
      } else {
        statusEl.textContent = '儲存失敗：' + (data.message || '未知錯誤');
        saveBtn.disabled = false;
      }
    });
  } else {
    // HTTP fallback
    var url = NOTE_ID ? ('/notes/api/' + NOTE_ID) : '/notes/api';
    var method = NOTE_ID ? 'PUT' : 'POST';
    fetch(url, {
      method: method,
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ title: title, content: content, store: store, status: currentStatus, priority: currentPriority })
    }).then(function(res) { return res.json(); }).then(function(data) {
      if (data.status === 'ok' || data.id) { window.location.href = '/notes/'; }
      else { statusEl.textContent = '儲存失敗：' + (data.message || '未知錯誤'); saveBtn.disabled = false; }
    }).catch(function(err) { statusEl.textContent = '儲存失敗：' + err.message; saveBtn.disabled = false; });
  }
}
```

將 `doDelete()` 函式替換為：

```javascript
function doDelete() {
  if (!NOTE_ID || !confirm('確定要刪除這篇筆記？')) return;
  if (window._ws && window._ws.connected) {
    window._ws.emit('d', { op: 'dn', id: NOTE_ID });
    window._ws.once('r', function() { window.location.href = '/notes/'; });
  } else {
    fetch('/notes/api/' + NOTE_ID, { method: 'DELETE' }).then(function() { window.location.href = '/notes/'; });
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/templates/notes/editor.html
git commit -m "feat: notes editor save/delete via WebSocket with HTTP fallback"
```

---

### Task 5: AI 摘要改用 WebSocket

**Files:**
- Modify: `app_unified/templates/notes/index.html`

- [ ] **Step 1: 修改 generateSummary 改用 WebSocket**

將 `generateSummary()` 函式替換為：

```javascript
function generateSummary() {
  var store = document.getElementById('ai-store-select').value;
  var days = document.getElementById('ai-days-select').value;
  var btn = document.getElementById('btn-ai-summary');
  var statusEl = document.getElementById('ai-status');
  var outputEl = document.getElementById('ai-summary-output');
  btn.disabled = true;
  statusEl.textContent = 'AI 整理中…（首次可能需要數分鐘）';
  outputEl.style.display = 'none';

  if (window._ws && window._ws.connected) {
    window._ws.emit('d', { op: 'as', store: store, days: parseInt(days) });
    window._ws.once('r', function(data) {
      if (data.op === 'as' && data.status === 'ok') {
        outputEl.textContent = data.summary;
        outputEl.style.display = 'block';
        statusEl.textContent = '';
      } else {
        statusEl.textContent = data.message || '錯誤';
      }
      btn.disabled = false;
    });
  } else {
    // HTTP fallback
    fetch('/notes/ai/summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ store: store, days: parseInt(days) })
    }).then(function(res) { return res.json(); }).then(function(data) {
      if (data.status === 'ok') {
        outputEl.textContent = data.summary;
        outputEl.style.display = 'block';
        statusEl.textContent = '';
      } else { statusEl.textContent = data.message || '錯誤'; }
    }).catch(function(e) { statusEl.textContent = '連線錯誤：' + e.message; })
    .finally(function() { btn.disabled = false; });
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/templates/notes/index.html
git commit -m "feat: AI summary via WebSocket with HTTP fallback"
```

---

### Task 6: SW Cache 更新 + Final Push

**Files:**
- Modify: `app_unified/static/sw.js`

- [ ] **Step 1: 更新 SW cache**

```javascript
const CACHE_NAME = 'note-weather-v9';
```

- [ ] **Step 2: Final commit + push**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/static/sw.js
git commit -m "feat: Stealth Vault Phase 4 — WebSocket + traffic padding, SW cache v9"
git push origin main
```

- [ ] **Step 3: 手動測試**

1. **WebSocket 連接：** 開 F12 Network tab → 看到 WebSocket 連線（type: websocket）
2. **流量填充：** WS messages 裡每秒有 `p` 事件（1KB 數據）
3. **儲存筆記：** 新增/修改筆記 → WS messages 裡看到 `d` 和 `r` 事件
4. **AI 摘要：** 產生摘要 → WS messages 裡看到 `d`（op:as）和 `r` 事件
5. **Wireshark：** 只看到一條恆定速率的加密 WebSocket 流
