# Note Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to upload images and videos as attachments to notes, stored in Cloudflare R2.

**Architecture:** New `NoteAttachment` model links files to notes. Upload/list/delete via HTTP endpoints in `notes/routes.py`. Files stored in R2 via existing `storage.py`. Frontend adds upload button + attachment display in editor. Note deletion cascades to R2 cleanup.

**Tech Stack:** Flask, SQLAlchemy, Cloudflare R2 (boto3), existing `storage.py`

---

### Task 1: Add NoteAttachment Model

**Files:**
- Modify: `app_unified/models.py`

- [ ] **Step 1: Add NoteAttachment class after NoteLog**

Add after line 96 in `models.py` (after the `NoteLog` class):

```python
class NoteAttachment(db.Model):
    __tablename__ = "note_attachments"

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    object_key = db.Column(db.Text, nullable=False)
    filename = db.Column(db.Text, nullable=False)
    content_type = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    note = db.relationship("Note", backref=db.backref("attachments", lazy=True, cascade="all, delete-orphan"))
    uploader = db.relationship("User", foreign_keys=[user_id])
```

- [ ] **Step 2: Verify model imports work**

Run: `cd /home/hirain0126/projects/webapp/app_unified && source ../venv/bin/activate && python -c "from models import NoteAttachment; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app_unified/models.py
git commit -m "feat: add NoteAttachment model for note file uploads"
```

---

### Task 2: Add R2 storage functions for attachments

**Files:**
- Modify: `app_unified/storage.py`

- [ ] **Step 1: Add upload_attachment and delete_attachment functions**

Add at end of `storage.py`:

```python
ALLOWED_CONTENT_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/webm',
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def upload_attachment(file_bytes: bytes, note_id: int, filename: str, content_type: str) -> str | None:
    """Upload attachment to R2. Returns object_key or None if R2 not configured."""
    if not BOTO3_AVAILABLE:
        return None
    cfg = current_app.config
    if not cfg.get("R2_ENDPOINT_URL"):
        return None

    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    object_key = f"attachments/{note_id}/{uuid.uuid4().hex}.{ext}"

    client = _get_client()
    client.put_object(
        Bucket=cfg["R2_BUCKET_NAME"],
        Key=object_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return object_key


def delete_attachment(object_key: str) -> bool:
    """Delete an object from R2. Returns True on success."""
    if not BOTO3_AVAILABLE or not object_key:
        return False
    cfg = current_app.config
    if not cfg.get("R2_ENDPOINT_URL"):
        return False

    try:
        client = _get_client()
        client.delete_object(Bucket=cfg["R2_BUCKET_NAME"], Key=object_key)
        return True
    except Exception:
        return False
```

- [ ] **Step 2: Verify import**

Run: `cd /home/hirain0126/projects/webapp/app_unified && source ../venv/bin/activate && python -c "from storage import upload_attachment, delete_attachment, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app_unified/storage.py
git commit -m "feat: add R2 upload/delete functions for note attachments"
```

---

### Task 3: Add attachment API endpoints

**Files:**
- Modify: `app_unified/notes/routes.py`

- [ ] **Step 1: Add upload endpoint**

Add at end of `notes/routes.py`:

```python
@notes_bp.route("/api/attachments/upload", methods=["POST"])
@login_required
def upload_attachment_api():
    from models import NoteAttachment
    from storage import upload_attachment, get_signed_url, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE

    note_id = request.form.get("note_id", type=int)
    if not note_id:
        return jsonify({"status": "error", "message": "缺少 note_id"}), 400

    # 權限檢查：能存取該筆記才能上傳
    if current_user.is_super_admin():
        note = Note.query.get(note_id)
    elif current_user.is_admin():
        note = Note.query.filter_by(id=note_id, store=current_user.store).first()
    else:
        note = Note.query.filter_by(id=note_id, user_id=current_user.id, store=current_user.store).first()
    if not note:
        return jsonify({"status": "error", "message": "筆記不存在或無權限"}), 404

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"status": "error", "message": "未選擇檔案"}), 400

    content_type = file.content_type or ''
    if content_type not in ALLOWED_CONTENT_TYPES:
        return jsonify({"status": "error", "message": "不支援的檔案格式"}), 400

    file_bytes = file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return jsonify({"status": "error", "message": "檔案超過 50MB 上限"}), 400

    object_key = upload_attachment(file_bytes, note_id, file.filename, content_type)
    if not object_key:
        return jsonify({"status": "error", "message": "儲存服務未設定"}), 503

    attachment = NoteAttachment(
        note_id=note_id,
        user_id=current_user.id,
        object_key=object_key,
        filename=file.filename,
        content_type=content_type,
        file_size=len(file_bytes),
    )
    db.session.add(attachment)
    db.session.commit()

    url = get_signed_url(object_key)
    return jsonify({
        "status": "ok",
        "attachment": {
            "id": attachment.id,
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "file_size": attachment.file_size,
            "url": url,
        }
    }), 201


@notes_bp.route("/api/attachments", methods=["GET"])
@login_required
def list_attachments():
    from models import NoteAttachment
    from storage import get_signed_url

    note_id = request.args.get("note_id", type=int)
    if not note_id:
        return jsonify({"status": "error", "message": "缺少 note_id"}), 400

    # 權限檢查
    if current_user.is_super_admin():
        note = Note.query.get(note_id)
    elif current_user.is_admin():
        note = Note.query.filter_by(id=note_id, store=current_user.store).first()
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first()
    if not note:
        return jsonify({"status": "error", "message": "筆記不存在或無權限"}), 404

    attachments = NoteAttachment.query.filter_by(note_id=note_id).order_by(NoteAttachment.created_at).all()
    result = []
    for a in attachments:
        url = get_signed_url(a.object_key)
        result.append({
            "id": a.id,
            "filename": a.filename,
            "content_type": a.content_type,
            "file_size": a.file_size,
            "url": url,
            "uploader": a.uploader.username if a.uploader else "",
            "created_at": a.created_at.isoformat() if a.created_at else "",
        })
    return jsonify({"status": "ok", "attachments": result})


@notes_bp.route("/api/attachments/<int:attachment_id>", methods=["DELETE"])
@login_required
def delete_attachment_api(attachment_id):
    from models import NoteAttachment
    from storage import delete_attachment

    attachment = NoteAttachment.query.get(attachment_id)
    if not attachment:
        return jsonify({"status": "error", "message": "附件不存在"}), 404

    note = Note.query.get(attachment.note_id)
    if not note:
        return jsonify({"status": "error", "message": "筆記不存在"}), 404

    # 權限：筆記作者、附件上傳者、admin（同店）、super_admin
    can_delete = False
    if current_user.is_super_admin():
        can_delete = True
    elif current_user.is_admin() and note.store == current_user.store:
        can_delete = True
    elif attachment.user_id == current_user.id:
        can_delete = True
    elif note.user_id == current_user.id:
        can_delete = True

    if not can_delete:
        return jsonify({"status": "error", "message": "無權限刪除"}), 403

    delete_attachment(attachment.object_key)
    db.session.delete(attachment)
    db.session.commit()
    return jsonify({"status": "ok"})
```

- [ ] **Step 2: Verify import**

Run: `cd /home/hirain0126/projects/webapp/app_unified && source ../venv/bin/activate && python -c "from notes.routes import notes_bp; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app_unified/notes/routes.py
git commit -m "feat: add attachment upload/list/delete API endpoints"
```

---

### Task 4: Add R2 cleanup on note deletion

**Files:**
- Modify: `app_unified/notes/routes.py` (HTTP delete)
- Modify: `app_unified/notes/ws.py` (WebSocket delete)

- [ ] **Step 1: Update HTTP delete_note to clean up R2 files**

Replace the `delete_note` function in `notes/routes.py` (around line 256):

```python
@notes_bp.route("/api/<int:note_id>", methods=["DELETE"])
@login_required
def delete_note(note_id):
    from storage import delete_attachment as r2_delete
    if current_user.is_super_admin():
        note = Note.query.get_or_404(note_id)
    elif current_user.is_admin():
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()
    else:
        note = Note.query.filter_by(id=note_id, store=current_user.store).first_or_404()

    # Delete R2 files before DB cascade
    for att in note.attachments:
        r2_delete(att.object_key)

    log = NoteLog(
        note_id=note.id,
        note_title=note.title,
        user_id=current_user.id,
        action="delete",
    )
    db.session.add(log)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"status": "ok"})
```

- [ ] **Step 2: Update WebSocket _delete_note to clean up R2 files**

In `notes/ws.py`, update the `_delete_note` function:

```python
    def _delete_note(data):
        from storage import delete_attachment as r2_delete
        note_id = data.get('id')
        if current_user.is_super_admin():
            note = Note.query.get(note_id)
        elif current_user.is_admin():
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
        else:
            note = Note.query.filter_by(id=note_id, store=current_user.store).first()
        if not note:
            emit('r', {'op': 'er', 'message': 'not found'})
            return

        # Delete R2 files before DB cascade
        for att in note.attachments:
            r2_delete(att.object_key)

        log = NoteLog(note_id=note.id, note_title=note.title, user_id=current_user.id, action='delete')
        db.session.add(log)
        db.session.delete(note)
        db.session.commit()
        emit('r', {'op': 'dn', 'status': 'ok'})
```

- [ ] **Step 3: Commit**

```bash
git add app_unified/notes/routes.py app_unified/notes/ws.py
git commit -m "feat: delete R2 attachments when note is deleted (HTTP + WebSocket)"
```

---

### Task 5: Frontend — Upload UI in editor

**Files:**
- Modify: `app_unified/templates/notes/editor.html`

- [ ] **Step 1: Add attachment CSS**

Add before `</style>` in the `<style>` block:

```css
.attachment-section { margin-top: 1rem; }
.attachment-section h4 { font-size: .9rem; color: #666; margin-bottom: .5rem; }
.upload-bar { display: flex; gap: .5rem; align-items: center; margin-bottom: .75rem; flex-wrap: wrap; }
.upload-bar input[type="file"] { display: none; }
.upload-progress { width: 100%; height: 4px; background: #eee; border-radius: 2px; overflow: hidden; display: none; margin-bottom: .5rem; }
.upload-progress-bar { height: 100%; background: #3498db; width: 0%; transition: width .3s; }
.attachment-list { display: flex; flex-wrap: wrap; gap: .75rem; }
.att-item { position: relative; border-radius: 8px; overflow: hidden; border: 1px solid #eee; background: #fafafa; }
.att-item img { display: block; max-width: 200px; max-height: 150px; object-fit: cover; cursor: pointer; }
.att-item video { display: block; max-width: 280px; max-height: 200px; border-radius: 8px; }
.att-item .att-info { padding: .3rem .5rem; font-size: .75rem; color: #888; }
.att-item .att-delete { position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,.6); color: #fff; border: none; border-radius: 50%; width: 24px; height: 24px; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.fullscreen-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.9); z-index: 9999; align-items: center; justify-content: center; cursor: pointer; }
.fullscreen-overlay.open { display: flex; }
.fullscreen-overlay img { max-width: 95vw; max-height: 95vh; object-fit: contain; touch-action: pinch-zoom; }
```

- [ ] **Step 2: Add attachment HTML after textarea**

After line 99 (`<textarea id="content-area" ...>`) and before `</div>`, add:

```html
  <!-- 附件區 -->
  <div class="attachment-section" id="attachment-section" {% if not note %}style="display:none"{% endif %}>
    <h4>附件</h4>
    <div class="upload-bar">
      <button class="btn btn-secondary" type="button" onclick="document.getElementById('file-input').click()">📎 上傳圖片/影片</button>
      <input type="file" id="file-input" accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/webm" multiple onchange="handleFileUpload(this)">
      <span id="upload-status" style="font-size:.85rem;color:#888;"></span>
    </div>
    <div class="upload-progress" id="upload-progress"><div class="upload-progress-bar" id="upload-progress-bar"></div></div>
    <div class="attachment-list" id="attachment-list"></div>
  </div>

  <!-- 全螢幕預覽 -->
  <div class="fullscreen-overlay" id="fullscreen-overlay" onclick="closeFullscreen()">
    <img id="fullscreen-img" src="">
  </div>
```

- [ ] **Step 3: Add attachment JavaScript**

Add before `</script>` in the scripts block:

```javascript
// ── 附件功能 ──
function loadAttachments() {
  if (!NOTE_ID) return;
  fetch('/notes/api/attachments?note_id=' + NOTE_ID)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.status !== 'ok') return;
      var list = document.getElementById('attachment-list');
      list.innerHTML = '';
      data.attachments.forEach(function(att) {
        list.appendChild(createAttItem(att));
      });
    }).catch(function() {});
}

function createAttItem(att) {
  var div = document.createElement('div');
  div.className = 'att-item';
  div.id = 'att-' + att.id;

  if (att.content_type.startsWith('image/')) {
    var img = document.createElement('img');
    img.src = att.url;
    img.alt = att.filename;
    img.onclick = function() { openFullscreen(att.url); };
    div.appendChild(img);
  } else if (att.content_type.startsWith('video/')) {
    var video = document.createElement('video');
    video.src = att.url;
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;
    div.appendChild(video);
  }

  var info = document.createElement('div');
  info.className = 'att-info';
  var sizeStr = att.file_size > 1048576 ? (att.file_size / 1048576).toFixed(1) + ' MB' : (att.file_size / 1024).toFixed(0) + ' KB';
  info.textContent = att.filename + ' (' + sizeStr + ')';
  div.appendChild(info);

  var delBtn = document.createElement('button');
  delBtn.className = 'att-delete';
  delBtn.textContent = '×';
  delBtn.onclick = function(e) {
    e.stopPropagation();
    if (!confirm('刪除此附件？')) return;
    fetch('/notes/api/attachments/' + att.id, { method: 'DELETE' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'ok') {
          var el = document.getElementById('att-' + att.id);
          if (el) el.remove();
        }
      });
  };
  div.appendChild(delBtn);

  return div;
}

function handleFileUpload(input) {
  if (!NOTE_ID) {
    alert('請先儲存筆記後再上傳附件');
    input.value = '';
    return;
  }
  var files = input.files;
  if (!files.length) return;

  var statusEl = document.getElementById('upload-status');
  var progressWrap = document.getElementById('upload-progress');
  var progressBar = document.getElementById('upload-progress-bar');
  var total = files.length;
  var done = 0;

  progressWrap.style.display = 'block';

  for (var i = 0; i < files.length; i++) {
    (function(file) {
      var formData = new FormData();
      formData.append('file', file);
      formData.append('note_id', NOTE_ID);

      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/notes/api/attachments/upload');

      xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
          var pct = Math.round((e.loaded / e.total) * 100);
          progressBar.style.width = pct + '%';
        }
      };

      xhr.onload = function() {
        done++;
        statusEl.textContent = done + '/' + total + ' 完成';
        if (done >= total) {
          progressWrap.style.display = 'none';
          progressBar.style.width = '0%';
          statusEl.textContent = '';
          loadAttachments();
          input.value = '';
        }
      };

      xhr.onerror = function() {
        done++;
        statusEl.textContent = '上傳失敗：' + file.name;
      };

      xhr.send(formData);
    })(files[i]);
  }
}

function openFullscreen(url) {
  document.getElementById('fullscreen-img').src = url;
  document.getElementById('fullscreen-overlay').classList.add('open');
}

function closeFullscreen() {
  document.getElementById('fullscreen-overlay').classList.remove('open');
  document.getElementById('fullscreen-img').src = '';
}

// 頁面載入時讀取附件
if (NOTE_ID) loadAttachments();
```

- [ ] **Step 4: Commit**

```bash
git add app_unified/templates/notes/editor.html
git commit -m "feat: add attachment upload UI, display, fullscreen preview in note editor"
```

---

### Task 6: Update doSave to show attachment section after first save

**Files:**
- Modify: `app_unified/templates/notes/editor.html`

- [ ] **Step 1: Update doSave to reveal attachment section on new note creation**

In the `doSave` function, in the WebSocket success handler, change:

```javascript
// Replace the existing ws.once('r', ...) handler:
window._ws.once('r', function(data) {
  if ((data.op === op || data.op === 'cn') && (data.status === 'ok' || data.id)) {
    if (!NOTE_ID && data.id) {
      // New note created — set NOTE_ID and show attachment section
      NOTE_ID = data.id;
      document.getElementById('attachment-section').style.display = '';
      document.getElementById('save-status').textContent = '已儲存';
      document.getElementById('btn-save').disabled = false;
      // Update URL without reload
      history.replaceState(null, '', '/notes/' + NOTE_ID);
    } else {
      window.location.href = '/notes/';
    }
  } else {
    statusEl.textContent = '儲存失敗：' + (data.message || '未知錯誤');
    saveBtn.disabled = false;
  }
});
```

Also update the HTTP fallback success handler similarly:

```javascript
}).then(function(data) {
  if (data.status === 'ok' || data.id) {
    if (!NOTE_ID && data.id) {
      NOTE_ID = data.id;
      document.getElementById('attachment-section').style.display = '';
      document.getElementById('save-status').textContent = '已儲存';
      document.getElementById('btn-save').disabled = false;
      history.replaceState(null, '', '/notes/' + NOTE_ID);
    } else {
      window.location.href = '/notes/';
    }
  }
  else { statusEl.textContent = '儲存失敗：' + (data.message || '未知錯誤'); saveBtn.disabled = false; }
```

- [ ] **Step 2: Commit**

```bash
git add app_unified/templates/notes/editor.html
git commit -m "feat: show attachment section after first save of new note"
```

---

### Task 7: Run tests and verify

- [ ] **Step 1: Run all tests**

Run: `cd /home/hirain0126/projects/webapp/app_unified && source ../venv/bin/activate && python -m pytest tests/ -v`

Expected: All previously passing tests still pass. (New endpoints don't have dedicated tests yet since they require R2, which is mocked in conftest.)

- [ ] **Step 2: Verify app starts**

Run: `cd /home/hirain0126/projects/webapp/app_unified && source ../venv/bin/activate && python -c "from app import create_app; app = create_app(); print('App created OK')"`

Expected: `App created OK`

- [ ] **Step 3: Final commit with all files**

```bash
git add -A
git commit -m "feat: note attachments — upload/view/delete images and videos via R2"
```
