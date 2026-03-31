# Stealth Vault Phase 1: 設備綁定 + 動態載入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓未授權設備在原始碼層面完全看不到 Notes 功能，只有已綁定且核准的設備才能動態載入連點 + PIN + 人臉驗證模組。

**Architecture:** 新增 TrustedDevice model 做設備綁定。天氣 API 根據設備指紋決定是否回傳 ext_ptr。前端收到 ext_ptr 才動態載入 secure-loader（包含連點、PIN modal、人臉驗證的完整 JS+HTML）。天氣頁面的靜態 HTML 不再包含任何 Notes 相關程式碼。種子模式在 DB 無 admin 時自動啟用。

**Tech Stack:** Flask, SQLAlchemy, PostgreSQL, vanilla JavaScript, SHA-256 (for device fingerprint)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app_unified/models.py` | Modify | 新增 TrustedDevice model |
| `app_unified/migrations/versions/004_trusted_devices.py` | Create | DB migration |
| `app_unified/device/routes.py` | Create | 設備指紋驗證 + secure-loader + seed-setup API |
| `app_unified/device/__init__.py` | Create | Blueprint package init |
| `app_unified/static/js/fingerprint.js` | Create | 前端設備指紋收集 |
| `app_unified/weather/routes.py` | Modify | 天氣 API 加入 ext_ptr 邏輯 |
| `app_unified/templates/weather/index.html` | Modify | 移除所有 Notes 相關 HTML/JS，改為動態載入 |
| `app_unified/admin/routes.py` | Modify | 新增設備管理 API |
| `app_unified/templates/admin/dashboard.html` | Modify | 新增設備管理 UI |
| `app_unified/app.py` | Modify | 註冊 device blueprint，移除預設 admin 建立 |

---

### Task 1: TrustedDevice Model + Migration

**Files:**
- Modify: `app_unified/models.py:106-113`（在 WeatherCache 之後新增）
- Create: `app_unified/migrations/versions/004_trusted_devices.py`

- [ ] **Step 1: 新增 TrustedDevice model**

在 `app_unified/models.py` 的 `WeatherCache` class 之後（第 113 行後）新增：

```python
class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fingerprint = db.Column(db.Text, unique=True, nullable=False)
    device_name = db.Column(db.Text, nullable=False, default="Unknown")
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    is_revoked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
```

- [ ] **Step 2: 建立 migration 004**

建立 `app_unified/migrations/versions/004_trusted_devices.py`：

```python
"""Add trusted_devices table for device binding

Revision ID: 004
Revises: 003
Create Date: 2026-03-31
"""
revision = '004'
down_revision = '003'

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def upgrade():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trusted_devices (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            fingerprint TEXT UNIQUE NOT NULL,
            device_name TEXT NOT NULL DEFAULT 'Unknown',
            is_approved BOOLEAN NOT NULL DEFAULT false,
            is_revoked BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_trusted_devices_fingerprint ON trusted_devices(fingerprint)")

    cur.close()
    conn.close()
    print("Migration 004 done.")

if __name__ == "__main__":
    upgrade()
```

- [ ] **Step 3: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/models.py app_unified/migrations/versions/004_trusted_devices.py
git commit -m "feat: add TrustedDevice model and migration 004"
```

---

### Task 2: 設備指紋前端收集

**Files:**
- Create: `app_unified/static/js/fingerprint.js`

- [ ] **Step 1: 建立 fingerprint.js**

建立 `app_unified/static/js/fingerprint.js`：

```javascript
/**
 * Device Fingerprint — 收集設備特徵產生唯一 hash
 * 自動將 hash 存入 localStorage 並在每次天氣請求時帶入
 */
(function() {
  function collectFeatures() {
    var features = [];
    features.push(navigator.userAgent || '');
    features.push(screen.width + 'x' + screen.height);
    features.push(window.devicePixelRatio || 1);
    features.push(Intl.DateTimeFormat().resolvedOptions().timeZone || '');
    features.push(navigator.language || '');
    features.push(navigator.hardwareConcurrency || 0);
    features.push(navigator.maxTouchPoints || 0);
    if (navigator.deviceMemory) features.push(navigator.deviceMemory);

    // Canvas fingerprint
    try {
      var canvas = document.createElement('canvas');
      canvas.width = 200;
      canvas.height = 50;
      var ctx = canvas.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('DeviceFP', 2, 15);
      features.push(canvas.toDataURL());
    } catch (e) {
      features.push('no-canvas');
    }

    return features.join('|||');
  }

  function sha256(str) {
    var encoder = new TextEncoder();
    var data = encoder.encode(str);
    return crypto.subtle.digest('SHA-256', data).then(function(buffer) {
      var arr = Array.from(new Uint8Array(buffer));
      return arr.map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    });
  }

  function getDeviceName() {
    var ua = navigator.userAgent;
    var name = 'Unknown';
    if (/iPhone/.test(ua)) name = 'iPhone';
    else if (/iPad/.test(ua)) name = 'iPad';
    else if (/Android/.test(ua)) name = 'Android';
    else if (/Windows/.test(ua)) name = 'Windows PC';
    else if (/Mac OS/.test(ua)) name = 'Mac';
    else if (/Linux/.test(ua)) name = 'Linux PC';

    if (/Chrome/.test(ua) && !/Edg/.test(ua)) name += ' / Chrome';
    else if (/Safari/.test(ua) && !/Chrome/.test(ua)) name += ' / Safari';
    else if (/Firefox/.test(ua)) name += ' / Firefox';
    else if (/Edg/.test(ua)) name += ' / Edge';

    return name;
  }

  var raw = collectFeatures();
  sha256(raw).then(function(hash) {
    window.__deviceFP = hash;
    window.__deviceName = getDeviceName();
  });
})();
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/static/js/fingerprint.js
git commit -m "feat: add client-side device fingerprint collector"
```

---

### Task 3: Device Blueprint（secure-loader + seed-setup API）

**Files:**
- Create: `app_unified/device/__init__.py`
- Create: `app_unified/device/routes.py`

- [ ] **Step 1: 建立 device package**

建立 `app_unified/device/__init__.py`（空檔案）：

```python
```

- [ ] **Step 2: 建立 device/routes.py**

建立 `app_unified/device/routes.py`：

```python
from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user
from extensions import db
from models import TrustedDevice, User, Store

device_bp = Blueprint("device", __name__, url_prefix="/api/v1")


def _get_device_from_request():
    """從 request header 取得設備，自動建立不存在的設備記錄"""
    fp = request.headers.get("X-Device-FP", "").strip()
    if not fp:
        return None, None
    device = TrustedDevice.query.filter_by(fingerprint=fp).first()
    return fp, device


def _register_device(fp, device_name):
    """註冊新設備（未核准）"""
    device = TrustedDevice(
        fingerprint=fp,
        device_name=device_name or "Unknown",
        is_approved=False,
        is_revoked=False,
    )
    db.session.add(device)
    db.session.commit()
    return device


def is_device_authorized(fp):
    """檢查設備是否已授權且未掛失，同時考慮店別 OFF"""
    if not fp:
        return False
    device = TrustedDevice.query.filter_by(fingerprint=fp).first()
    if not device or not device.is_approved or device.is_revoked:
        return False
    if not device.user_id:
        return False
    user = User.query.get(device.user_id)
    if not user or not user.is_active:
        return False
    # Admin 不受店別 OFF 影響
    if user.is_admin():
        return True
    # 檢查店別是否 OFF
    if user.store:
        store = Store.query.filter_by(name=user.store).first()
        if store and not store.login_enabled:
            return False
    return True


def is_seed_mode():
    """DB 沒有任何 admin 時進入種子模式"""
    return User.query.filter_by(role="admin").count() == 0


@device_bp.route("/register-device", methods=["POST"])
def register_device():
    """前端自動呼叫，註冊設備指紋"""
    data = request.get_json(silent=True) or {}
    fp = data.get("fingerprint", "").strip()
    device_name = data.get("device_name", "Unknown")
    if not fp:
        return jsonify({"status": "error", "message": "missing fingerprint"}), 400
    existing = TrustedDevice.query.filter_by(fingerprint=fp).first()
    if existing:
        existing.last_seen_at = __import__("datetime").datetime.utcnow()
        db.session.commit()
        return jsonify({"status": "ok", "registered": False})
    _register_device(fp, device_name)
    return jsonify({"status": "ok", "registered": True}), 201


@device_bp.route("/secure-loader")
def secure_loader():
    """回傳動態載入的 JS（連點 + PIN modal + 人臉驗證）"""
    fp = request.headers.get("X-Device-FP", "").strip()
    if not is_device_authorized(fp):
        return "", 404

    js_code = _build_secure_loader_js()
    return Response(js_code, mimetype="application/javascript")


@device_bp.route("/seed-setup", methods=["GET"])
def seed_setup_loader():
    """種子模式：回傳初始化設定的 JS"""
    if not is_seed_mode():
        return "", 404
    js_code = _build_seed_setup_js()
    return Response(js_code, mimetype="application/javascript")


@device_bp.route("/seed-setup", methods=["POST"])
def seed_setup_submit():
    """種子模式：建立第一位 admin"""
    if not is_seed_mode():
        return jsonify({"status": "error", "message": "已有管理員"}), 403

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    pin = (data.get("pin") or "").strip()
    face_image = data.get("face_image")
    fp = data.get("fingerprint", "").strip()
    device_name = data.get("device_name", "Unknown")

    if not username or not pin:
        return jsonify({"status": "error", "message": "請填寫帳號和 PIN"}), 400

    user = User(username=username, role="admin")
    user.set_password(pin)

    # 人臉註冊
    if face_image:
        try:
            import face_recognition
            import io, base64
            img_data = base64.b64decode(face_image.split(",")[-1])
            img = face_recognition.load_image_file(io.BytesIO(img_data))
            encodings = face_recognition.face_encodings(img)
            if encodings:
                user.set_face_encoding(encodings[0])
        except BaseException:
            pass

    db.session.add(user)
    db.session.flush()

    # 自動綁定並核准此設備
    device = TrustedDevice.query.filter_by(fingerprint=fp).first()
    if not device:
        device = TrustedDevice(fingerprint=fp, device_name=device_name)
        db.session.add(device)
        db.session.flush()
    device.user_id = user.id
    device.is_approved = True

    db.session.commit()
    return jsonify({"status": "ok", "user_id": user.id})


def _build_secure_loader_js():
    """產生連點 + PIN modal + 人臉驗證的完整 JS"""
    return """
(function() {
  // ── Auth Modal HTML ──
  var modalHTML = ''
    + '<div id="auth-modal">'
    + '  <div class="modal-box">'
    + '    <button class="modal-close" id="modal-close">&times;</button>'
    + '    <h2>\\ud83d\\udd10 進入系統</h2>'
    + '    <div class="modal-form-group">'
    + '      <label style="display:flex;align-items:center;gap:.5rem;">'
    + '        PIN 碼'
    + '        <span id="m-cam-indicator" style="display:none;width:10px;height:10px;border-radius:50%;background:#e74c3c;animation:blink 1s infinite;"></span>'
    + '      </label>'
    + '      <input type="password" id="m-pin" maxlength="4" placeholder="4 位數" inputmode="numeric" autocomplete="current-password">'
    + '    </div>'
    + '    <button class="btn-modal btn-modal-primary" id="m-submit">驗證登入</button>'
    + '    <div id="modal-msg"></div>'
    + '  </div>'
    + '</div>';

  var modalStyle = document.createElement('style');
  modalStyle.textContent = ''
    + '#auth-modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:1000; align-items:center; justify-content:center; }'
    + '#auth-modal.open { display:flex; }'
    + '.modal-box { background:#fff; color:#333; border-radius:16px; padding:2rem; width:360px; max-width:95vw; position:relative; }'
    + '.modal-box h2 { margin-bottom:1.25rem; color:#2c3e50; }'
    + '.modal-close { position:absolute; top:.75rem; right:1rem; font-size:1.5rem; background:none; border:none; cursor:pointer; color:#888; min-width:44px; min-height:44px; }'
    + '.modal-form-group { margin-bottom:.9rem; }'
    + '.modal-form-group label { display:block; margin-bottom:.3rem; font-size:.85rem; font-weight:600; color:#555; }'
    + '.modal-form-group input { width:100%; padding:.55rem .75rem; border:1px solid #ddd; border-radius:6px; font-size:16px; }'
    + '.modal-form-group input:focus { outline:none; border-color:#3498db; }'
    + '.btn-modal { display:block; width:100%; padding:.75rem; border-radius:8px; border:none; cursor:pointer; font-size:.95rem; margin-top:.5rem; font-weight:600; min-height:44px; }'
    + '.btn-modal-primary { background:#3498db; color:#fff; }'
    + '.btn-modal-primary:hover { background:#2980b9; }'
    + '#modal-msg { text-align:center; font-size:.9rem; min-height:1.3em; margin-top:.5rem; }'
    + '#modal-msg.ok { color:#27ae60; }'
    + '#modal-msg.err { color:#e74c3c; }'
    + '@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }';
  document.head.appendChild(modalStyle);

  var wrapper = document.createElement('div');
  wrapper.innerHTML = modalHTML;
  document.body.appendChild(wrapper.firstChild);

  // ── Video/Canvas for face capture ──
  var video = document.createElement('video');
  video.autoplay = true;
  video.playsInline = true;
  video.muted = true;
  video.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:320px;height:240px;pointer-events:none;';
  document.body.appendChild(video);

  var canvas = document.createElement('canvas');
  canvas.width = 320;
  canvas.height = 240;
  canvas.style.display = 'none';
  document.body.appendChild(canvas);

  var stream = null;
  var cameraState = 'idle';

  function startCamera() {
    cameraState = 'starting';
    var indicator = document.getElementById('m-cam-indicator');
    if (indicator) indicator.style.display = 'inline-block';
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      .catch(function() { return navigator.mediaDevices.getUserMedia({ video: true, audio: false }); })
      .then(function(s) {
        stream = s;
        video.srcObject = s;
        cameraState = 'ready';
        if (indicator) indicator.style.backgroundColor = '#2ecc71';
        var msgEl = document.getElementById('modal-msg');
        if (msgEl && msgEl.textContent.indexOf('鏡頭') >= 0) { msgEl.textContent = ''; }
      })
      .catch(function() {
        cameraState = 'failed';
        if (indicator) { indicator.style.display = 'inline-block'; indicator.style.backgroundColor = '#999'; }
        var msgEl = document.getElementById('modal-msg');
        if (msgEl) { msgEl.textContent = '相機無法啟動，請確認瀏覽器相機權限後重新整理'; msgEl.className = 'err'; }
      });
  }

  function stopCamera() {
    if (stream) { stream.getTracks().forEach(function(t) { t.stop(); }); stream = null; }
    cameraState = 'idle';
    var indicator = document.getElementById('m-cam-indicator');
    if (indicator) indicator.style.display = 'none';
  }

  function captureFace() {
    if (!stream || video.readyState < 2 || video.videoWidth === 0) return null;
    var ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  }

  // ── Tap detector ──
  var target = document.getElementById('tap-target');
  var tapCount = 0;
  var tapTimer;
  if (target) {
    target.addEventListener('click', function() {
      tapCount++;
      clearTimeout(tapTimer);
      tapTimer = setTimeout(function() { tapCount = 0; }, 5000);
      if (tapCount >= 6) {
        tapCount = 0;
        var modal = document.getElementById('auth-modal');
        if (modal) modal.classList.add('open');
        var msg = document.getElementById('modal-msg');
        if (msg) { msg.textContent = '鏡頭啟動中…'; msg.className = ''; }
        startCamera();
      }
    });
  }

  // ── Modal auth logic ──
  var modal = document.getElementById('auth-modal');
  var closeBtn = document.getElementById('modal-close');
  var submitBtn = document.getElementById('m-submit');
  var msgEl = document.getElementById('modal-msg');

  function showMsg(text, cls) { if (msgEl) { msgEl.textContent = text; msgEl.className = cls || ''; } }

  if (closeBtn) closeBtn.addEventListener('click', function() {
    if (modal) modal.classList.remove('open');
    showMsg('');
    stopCamera();
  });

  if (modal) modal.addEventListener('click', function(e) {
    if (e.target === modal) { modal.classList.remove('open'); showMsg(''); stopCamera(); }
  });

  if (submitBtn) submitBtn.addEventListener('click', function() {
    var pin = (document.getElementById('m-pin') || {}).value || '';
    pin = pin.trim();
    var faceImage = captureFace();
    if (!faceImage) {
      if (cameraState === 'failed') {
        showMsg('相機無法啟動，請確認瀏覽器相機權限後重新整理', 'err');
      } else {
        showMsg('鏡頭啟動中，請稍候再試', 'err');
      }
      return;
    }
    submitBtn.disabled = true;
    showMsg('辨識中…');
    fetch('/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pin, face_image: faceImage })
    }).then(function(res) { return res.json(); }).then(function(data) {
      switch (data.status) {
        case 'ok':
          showMsg('驗證成功！正在跳轉…', 'ok');
          setTimeout(function() { location.href = '/auth/s/r'; }, 800);
          break;
        case 'wrong_password':
          showMsg('PIN 碼錯誤，請重新輸入', 'err');
          break;
        case 'face_not_found':
          showMsg('錯誤1', 'err');
          break;
        case 'need_face_enroll':
          showMsg('請聯繫管理員1', 'err');
          break;
        case 'face_mismatch':
          showMsg('1失敗，請重試', 'err');
          break;
        case 'store_disabled':
          if (modal) modal.classList.remove('open');
          showMsg('');
          var pinInput = document.getElementById('m-pin');
          if (pinInput) pinInput.value = '';
          stopCamera();
          break;
        default:
          showMsg('驗證失敗，請重試', 'err');
      }
    }).catch(function() {
      showMsg('連線錯誤，請重試', 'err');
    }).then(function() {
      submitBtn.disabled = false;
    });
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && modal && modal.classList.contains('open') && submitBtn) submitBtn.click();
  });
})();
"""


def _build_seed_setup_js():
    """產生種子模式初始化設定的 JS"""
    return """
(function() {
  var setupHTML = ''
    + '<div id="seed-modal" style="display:flex;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center;">'
    + '  <div style="background:#fff;color:#333;border-radius:16px;padding:2rem;width:400px;max-width:95vw;">'
    + '    <h2 style="margin-bottom:1rem;color:#2c3e50;">\\ud83d\\udd27 系統初始化</h2>'
    + '    <p style="font-size:.85rem;color:#666;margin-bottom:1rem;">首次使用，請設定管理員帳號。</p>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">帳號名稱</label><input type="text" id="seed-username" style="width:100%;padding:.5rem;border:1px solid #ddd;border-radius:6px;font-size:16px;"></div>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">PIN 碼（4位數）</label><input type="password" id="seed-pin" maxlength="4" inputmode="numeric" style="width:100%;padding:.5rem;border:1px solid #ddd;border-radius:6px;font-size:16px;"></div>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">人臉登錄</label><button id="seed-cam-btn" style="padding:.5rem 1rem;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:.9rem;">開啟鏡頭</button></div>'
    + '    <video id="seed-video" autoplay playsinline muted style="width:100%;border-radius:6px;background:#000;display:none;margin-bottom:.5rem;"></video>'
    + '    <canvas id="seed-canvas" style="display:none;"></canvas>'
    + '    <button id="seed-capture" style="display:none;padding:.5rem 1rem;border:1px solid #ddd;border-radius:6px;cursor:pointer;margin-bottom:.5rem;">拍照</button>'
    + '    <img id="seed-preview" style="display:none;width:100px;border-radius:6px;border:2px solid #27ae60;margin-bottom:.5rem;">'
    + '    <button id="seed-submit" style="display:block;width:100%;padding:.75rem;border-radius:8px;border:none;cursor:pointer;font-size:.95rem;font-weight:600;background:#3498db;color:#fff;margin-top:.5rem;">建立管理員</button>'
    + '    <div id="seed-msg" style="text-align:center;font-size:.9rem;min-height:1.3em;margin-top:.5rem;"></div>'
    + '  </div>'
    + '</div>';

  var wrapper = document.createElement('div');
  wrapper.innerHTML = setupHTML;
  document.body.appendChild(wrapper.firstChild);

  var seedStream = null;
  var seedFaceImage = null;
  var seedVideo = document.getElementById('seed-video');
  var seedCanvas = document.getElementById('seed-canvas');

  document.getElementById('seed-cam-btn').addEventListener('click', function() {
    seedVideo.style.display = 'block';
    document.getElementById('seed-capture').style.display = 'inline-block';
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      .catch(function() { return navigator.mediaDevices.getUserMedia({ video: true, audio: false }); })
      .then(function(s) { seedStream = s; seedVideo.srcObject = s; })
      .catch(function() { document.getElementById('seed-msg').textContent = '無法開啟鏡頭'; });
  });

  document.getElementById('seed-capture').addEventListener('click', function() {
    if (!seedStream || seedVideo.readyState < 2) return;
    seedCanvas.width = seedVideo.videoWidth || 640;
    seedCanvas.height = seedVideo.videoHeight || 480;
    seedCanvas.getContext('2d').drawImage(seedVideo, 0, 0);
    seedFaceImage = seedCanvas.toDataURL('image/jpeg', 0.85);
    var preview = document.getElementById('seed-preview');
    preview.src = seedFaceImage;
    preview.style.display = 'block';
  });

  document.getElementById('seed-submit').addEventListener('click', function() {
    var username = document.getElementById('seed-username').value.trim();
    var pin = document.getElementById('seed-pin').value.trim();
    var msgEl = document.getElementById('seed-msg');
    if (!username || !pin) { msgEl.textContent = '請填寫帳號和 PIN'; msgEl.style.color = '#e74c3c'; return; }
    if (!seedFaceImage) { msgEl.textContent = '請先拍攝人臉'; msgEl.style.color = '#e74c3c'; return; }
    msgEl.textContent = '建立中…';
    msgEl.style.color = '#666';
    fetch('/api/v1/seed-setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        pin: pin,
        face_image: seedFaceImage,
        fingerprint: window.__deviceFP || '',
        device_name: window.__deviceName || 'Unknown'
      })
    }).then(function(res) { return res.json(); }).then(function(data) {
      if (data.status === 'ok') {
        msgEl.textContent = '管理員建立成功！重新載入中…';
        msgEl.style.color = '#27ae60';
        if (seedStream) { seedStream.getTracks().forEach(function(t) { t.stop(); }); }
        setTimeout(function() { location.reload(); }, 1500);
      } else {
        msgEl.textContent = data.message || '建立失敗';
        msgEl.style.color = '#e74c3c';
      }
    }).catch(function() {
      msgEl.textContent = '連線錯誤';
      msgEl.style.color = '#e74c3c';
    });
  });
})();
"""
```

- [ ] **Step 3: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/device/__init__.py app_unified/device/routes.py
git commit -m "feat: add device blueprint with secure-loader and seed-setup"
```

---

### Task 4: 天氣 API 加入 ext_ptr + 設備自動註冊

**Files:**
- Modify: `app_unified/weather/routes.py:19-66`

- [ ] **Step 1: 修改天氣 API**

在 `app_unified/weather/routes.py` 頂部 import 區加入：

```python
from models import WeatherCache, User
```

然後修改 `api_weather` 函式，在 `return jsonify(data), resp.status_code`（第 64 行）之前，加入 ext_ptr 邏輯。將整個 `api_weather` 函式替換為：

```python
@weather_bp.route("/api/weather")
def api_weather():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    api_key = current_app.config.get("OPENWEATHERMAP_API_KEY", "")

    if lat and lon:
        city_key = f"geo_{round(float(lat), 2)}_{round(float(lon), 2)}"
        ow_params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric", "lang": "zh_tw"}
    else:
        city = request.args.get("city", "Taipei")
        city_key = city.lower()
        ow_params = {"q": city, "appid": api_key, "units": "metric", "lang": "zh_tw"}

    # Check DB cache (shared across multiple workers)
    cached = WeatherCache.query.filter_by(city_key=city_key).first()
    if cached:
        age = (datetime.utcnow() - cached.cached_at).total_seconds()
        if age < _CACHE_TTL_SECONDS:
            data = json.loads(cached.data_json)
            _inject_ext_ptr(data)
            return jsonify(data)

    if not api_key:
        return jsonify({"error": "未設定 OpenWeatherMap API Key"}), 503

    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=ow_params,
            timeout=5,
        )
        data = resp.json()
        if resp.status_code == 200:
            # Upsert cache
            data_json = json.dumps(data)
            if cached:
                cached.data_json = data_json
                cached.cached_at = datetime.utcnow()
            else:
                cached = WeatherCache(
                    city_key=city_key,
                    data_json=data_json,
                    cached_at=datetime.utcnow(),
                )
                db.session.add(cached)
            db.session.commit()
        _inject_ext_ptr(data)
        return jsonify(data), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _inject_ext_ptr(data):
    """根據設備狀態注入 ext_ptr 或 seed_ptr"""
    from device.routes import is_device_authorized, is_seed_mode
    fp = request.headers.get("X-Device-FP", "").strip()
    if is_seed_mode():
        data["ext_ptr"] = "/api/v1/seed-setup"
    elif fp and is_device_authorized(fp):
        data["ext_ptr"] = "/api/v1/secure-loader"
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/weather/routes.py
git commit -m "feat: weather API injects ext_ptr for authorized devices"
```

---

### Task 5: 天氣頁面改造（移除 Notes 痕跡 + 動態載入）

**Files:**
- Modify: `app_unified/templates/weather/index.html`

- [ ] **Step 1: 移除所有 Notes 相關 HTML/JS，加入動態載入**

將 `app_unified/templates/weather/index.html` 的第 82 行之後（從 `<!-- Hidden Auth Modal -->` 到檔案結尾）全部替換為：

```html

<script src="/static/js/fingerprint.js"></script>
<script>
// Weather loading
(function() {
  var card = document.getElementById('weather-card');
  var locText = document.getElementById('location-text');

  var weatherIcons = {
    Thunderstorm: '⛈️', Drizzle: '🌦️', Rain: '🌧️', Snow: '❄️',
    Clear: '☀️', Clouds: '☁️', Mist: '🌫️', Fog: '🌫️',
    Haze: '🌁', Dust: '💨', Sand: '💨', Ash: '🌋', Tornado: '🌪️'
  };

  function renderWeatherCard(data) {
    if (data.error) {
      card.innerHTML = '<div class="weather-error">' + data.error + '</div>';
      return;
    }
    locText.textContent = data.name || locText.textContent;
    var icon = weatherIcons[data.weather && data.weather[0] && data.weather[0].main] || '🌐';
    var humidity = data.main && data.main.humidity != null ? data.main.humidity : '--';
    var wind = data.wind && data.wind.speed != null ? data.wind.speed : '--';
    var feels = data.main && data.main.feels_like != null ? Math.round(data.main.feels_like) : '--';
    var visibility = data.visibility != null ? (data.visibility / 1000).toFixed(1) : '--';
    card.innerHTML = ''
      + '<div class="city-name">📍 ' + data.name + '</div>'
      + '<div class="weather-icon">' + icon + '</div>'
      + '<div class="temp">' + Math.round(data.main && data.main.temp || 0) + '°C</div>'
      + '<div class="desc">' + (data.weather && data.weather[0] && data.weather[0].description || '') + '</div>'
      + '<div class="details">'
      + '  <span>💧 濕度 ' + humidity + '%</span>'
      + '  <span>💨 風速 ' + wind + ' m/s</span>'
      + '  <span>🌡️ 體感 ' + feels + '°C</span>'
      + '  <span>👁️ 能見度 ' + visibility + ' km</span>'
      + '</div>';

    // 動態載入：只在收到 ext_ptr 時執行
    if (data.ext_ptr) {
      var s = document.createElement('script');
      s.src = data.ext_ptr;
      if (window.__deviceFP) {
        // 帶 fingerprint 作為 query param（secure-loader 也會從 header 驗證）
        s.src = data.ext_ptr + '?_t=' + Date.now();
      }
      document.body.appendChild(s);
    }
  }

  function renderAQI(item) {
    var aqi = item.main.aqi;
    var pm25 = item.components && item.components.pm2_5 != null ? item.components.pm2_5.toFixed(1) : '--';
    var levels = ['', '好', '中等', '不良', '差', '非常差'];
    var colors = ['', '#2ecc71', '#f1c40f', '#e74c3c', '#e74c3c', '#e74c3c'];
    var label = levels[aqi] || '--';
    var color = colors[aqi] || '#fff';
    var block = document.createElement('div');
    block.className = 'aqi-block';
    block.innerHTML = ''
      + '<div class="aqi-label">🌫️ 空氣品質</div>'
      + '<div class="aqi-level" style="color:' + color + '">' + label + '</div>'
      + '<div class="aqi-detail">PM2.5 ' + pm25 + ' μg/m³</div>';
    card.appendChild(block);
  }

  // 等待 fingerprint 計算完成後再發天氣請求
  function waitForFP(callback) {
    if (window.__deviceFP) {
      callback();
    } else {
      setTimeout(function() { waitForFP(callback); }, 50);
    }
  }

  function fetchWeather(url) {
    var controller = new AbortController();
    var timeout = setTimeout(function() { controller.abort(); }, 10000);
    fetch(url, {
      signal: controller.signal,
      headers: { 'X-Device-FP': window.__deviceFP || '' }
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        clearTimeout(timeout);
        renderWeatherCard(data);
        // 註冊設備（靜默）
        if (window.__deviceFP) {
          fetch('/api/v1/register-device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fingerprint: window.__deviceFP, device_name: window.__deviceName || 'Unknown' })
          }).catch(function() {});
        }
      })
      .catch(function(err) {
        clearTimeout(timeout);
        var msg = err.name === 'AbortError' ? '載入逾時，請重新整理' : '無法載入天氣資料';
        card.innerHTML = '<div class="weather-error">' + msg + '</div>';
      });
  }

  function loadWeatherByCoords(lat, lon) {
    var weatherUrl = '/weather/api/weather?lat=' + lat + '&lon=' + lon;
    var namePromise = fetch(
      'https://nominatim.openstreetmap.org/reverse?lat=' + lat + '&lon=' + lon + '&format=json&accept-language=zh-TW'
    ).then(function(r) { return r.json(); })
     .then(function(geo) { return (geo.address && (geo.address.city || geo.address.county || geo.address.state)) || null; })
     .catch(function() { return null; });

    var weatherPromise = fetch(weatherUrl, { headers: { 'X-Device-FP': window.__deviceFP || '' } })
      .then(function(r) { return r.json(); });

    var aqiPromise = fetch('/weather/api/air_quality?lat=' + lat + '&lon=' + lon)
      .then(function(r) { return r.json(); })
      .catch(function() { return null; });

    Promise.all([weatherPromise, namePromise, aqiPromise]).then(function(results) {
      var data = results[0];
      var chineseName = results[1];
      var aqiData = results[2];
      if (chineseName) data.name = chineseName;
      renderWeatherCard(data);
      if (aqiData && aqiData.list && aqiData.list[0]) renderAQI(aqiData.list[0]);
      // 註冊設備
      if (window.__deviceFP) {
        fetch('/api/v1/register-device', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fingerprint: window.__deviceFP, device_name: window.__deviceName || 'Unknown' })
        }).catch(function() {});
      }
    }).catch(function() {
      card.innerHTML = '<div class="weather-error">無法載入天氣資料</div>';
    });
  }

  function fallbackToIP() {
    fetch('https://ip-api.com/json?fields=city,status', { cache: 'no-store' })
      .then(function(r) { return r.json(); })
      .then(function(geo) {
        if (geo.status === 'success' && geo.city) {
          fetchWeather('/weather/api/weather?city=' + encodeURIComponent(geo.city));
        } else {
          fetchWeather('/weather/api/weather?city=Taipei');
        }
      })
      .catch(function() { fetchWeather('/weather/api/weather?city=Taipei'); });
  }

  waitForFP(function() {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        function(pos) { loadWeatherByCoords(pos.coords.latitude, pos.coords.longitude); },
        function() { fallbackToIP(); },
        { timeout: 8000, maximumAge: 300000 }
      );
    } else {
      fallbackToIP();
    }
  });
})();
</script>
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }
</script>
</body>
</html>
```

注意：整個 `<!-- Hidden Auth Modal -->` 區塊、face_capture.js 引用、連點邏輯、PIN modal HTML、modal auth JS 全部移除。這些現在由 secure-loader 動態注入。

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/templates/weather/index.html
git commit -m "feat: weather page stripped of all Notes traces, dynamic loading via ext_ptr"
```

---

### Task 6: 註冊 device blueprint + 移除預設 admin

**Files:**
- Modify: `app_unified/app.py:88-98`（blueprint 註冊區）
- Modify: `app_unified/app.py:59-64`（移除預設 admin 建立）

- [ ] **Step 1: 修改 app.py**

在 blueprint import 區（第 88-92 行）加入 device：

```python
    from auth.routes import auth_bp
    from face.routes import face_bp
    from notes.routes import notes_bp
    from weather.routes import weather_bp
    from admin.routes import admin_bp
    from device.routes import device_bp
```

在 blueprint 註冊區（第 94-98 行）加入：

```python
    app.register_blueprint(auth_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(device_bp)
```

移除預設 admin 建立（第 59-64 行），替換為：

```python
        # 種子模式由 device blueprint 處理，不再自動建立預設 admin
```

- [ ] **Step 2: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/app.py
git commit -m "feat: register device blueprint, remove default admin creation (seed mode replaces it)"
```

---

### Task 7: Admin Dashboard 設備管理

**Files:**
- Modify: `app_unified/admin/routes.py`（新增設備管理 API）
- Modify: `app_unified/templates/admin/dashboard.html`（新增設備管理 UI）

- [ ] **Step 1: 新增設備管理 API**

在 `app_unified/admin/routes.py` 的 `# ── 店家管理 ──` 之前（約第 256 行），新增：

```python
# ── 設備管理 ──────────────────────────────────────────────

@admin_bp.route("/devices", methods=["GET"])
@login_required
def list_devices():
    require_admin()
    from models import TrustedDevice
    devices = TrustedDevice.query.order_by(TrustedDevice.created_at.desc()).all()
    return jsonify([{
        "id": d.id,
        "fingerprint": d.fingerprint[:12] + "...",
        "device_name": d.device_name,
        "is_approved": d.is_approved,
        "is_revoked": d.is_revoked,
        "user_id": d.user_id,
        "username": d.user.username if d.user else None,
        "store": d.user.store if d.user else None,
        "role": d.user.role if d.user else None,
        "created_at": d.created_at.strftime("%Y/%m/%d %H:%M") if d.created_at else "",
        "last_seen_at": d.last_seen_at.strftime("%Y/%m/%d %H:%M") if d.last_seen_at else "",
    } for d in devices])


@admin_bp.route("/devices/<int:device_id>/approve", methods=["POST"])
@login_required
def approve_device(device_id):
    require_admin()
    from models import TrustedDevice
    import io, base64
    device = TrustedDevice.query.get_or_404(device_id)
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()
    store = (data.get("store") or "").strip()
    role = data.get("role", "user")
    face_image = data.get("face_image")

    if not username or not pin:
        return jsonify({"status": "error", "message": "請填寫帳號和 PIN"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "帳號已存在"}), 409

    valid_stores = [s.name for s in Store.query.all()]
    user = User(
        username=username,
        role=role if role in ("admin", "user") else "user",
        store=store if store in valid_stores else None,
    )
    user.set_password(pin)

    if face_image:
        try:
            import face_recognition
            img_data = base64.b64decode(face_image.split(",")[-1])
            img = face_recognition.load_image_file(io.BytesIO(img_data))
            encodings = face_recognition.face_encodings(img)
            if encodings:
                user.set_face_encoding(encodings[0])
        except BaseException:
            pass

    db.session.add(user)
    db.session.flush()

    device.user_id = user.id
    device.is_approved = True
    device.is_revoked = False
    db.session.commit()

    return jsonify({"status": "ok", "user_id": user.id})


@admin_bp.route("/devices/<int:device_id>/revoke", methods=["POST"])
@login_required
def revoke_device(device_id):
    require_admin()
    from models import TrustedDevice
    device = TrustedDevice.query.get_or_404(device_id)
    device.is_revoked = True
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/devices/<int:device_id>/unrervoke", methods=["POST"])
@login_required
def unrevoke_device(device_id):
    require_admin()
    from models import TrustedDevice
    device = TrustedDevice.query.get_or_404(device_id)
    device.is_revoked = False
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/devices/<int:device_id>", methods=["DELETE"])
@login_required
def delete_device(device_id):
    require_admin()
    from models import TrustedDevice
    device = TrustedDevice.query.get_or_404(device_id)
    db.session.delete(device)
    db.session.commit()
    return jsonify({"status": "ok"})
```

- [ ] **Step 2: 在 dashboard 傳入 stores 到設備核准表單**

確認 `dashboard` route 已傳入 `stores`（已經有了，在第 82 行）。

- [ ] **Step 3: 新增設備管理 UI 到 dashboard.html**

在 `app_unified/templates/admin/dashboard.html` 的「店家管理」`<div class="card">` 之前，新增：

```html
<div class="card" style="margin-top:1rem;">
  <h3>設備管理</h3>
  <button class="btn btn-secondary" onclick="loadDevices()" style="margin-top:.5rem;">載入設備列表</button>
  <table id="devices-table" style="margin-top:.75rem;display:none;">
    <thead><tr><th>設備</th><th>狀態</th><th>綁定帳號</th><th>店別</th><th>首次出現</th><th>最後上線</th><th>操作</th></tr></thead>
    <tbody id="devices-tbody"></tbody>
  </table>
</div>

<!-- 設備核准 Modal -->
<div id="approve-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center;">
  <div class="card" style="max-width:420px;width:90%;position:relative;">
    <button onclick="document.getElementById('approve-modal').style.display='none'" style="position:absolute;top:.5rem;right:.75rem;background:none;border:none;font-size:1.4rem;cursor:pointer;min-width:44px;min-height:44px;">&times;</button>
    <h3 style="margin-bottom:1rem;">核准設備並建立帳號</h3>
    <input type="hidden" id="approve-device-id">
    <div style="margin-bottom:.5rem;"><label style="font-size:.85rem;font-weight:600;">帳號名稱</label><input type="text" id="approve-username" class="form-control"></div>
    <div style="margin-bottom:.5rem;"><label style="font-size:.85rem;font-weight:600;">PIN 碼（4位數）</label><input type="password" id="approve-pin" maxlength="4" inputmode="numeric" class="form-control"></div>
    <div style="margin-bottom:.5rem;">
      <label style="font-size:.85rem;font-weight:600;">店別</label>
      <select id="approve-store" class="form-control">
        <option value="">— 請選擇 —</option>
        {% for s in stores %}
        <option value="{{ s }}">{{ s }} 店</option>
        {% endfor %}
      </select>
    </div>
    <div style="margin-bottom:.5rem;">
      <label style="font-size:.85rem;font-weight:600;">權限</label>
      <select id="approve-role" class="form-control">
        <option value="user">一般使用者</option>
        <option value="admin">管理員</option>
      </select>
    </div>
    <div style="margin-bottom:.5rem;">
      <label style="font-size:.85rem;font-weight:600;">人臉登錄</label>
      <button class="btn btn-secondary" onclick="startApproveCamera()" id="approve-cam-btn" style="font-size:.85rem;">開啟鏡頭</button>
    </div>
    <video id="approve-video" autoplay playsinline muted style="width:100%;border-radius:6px;background:#000;display:none;margin-bottom:.5rem;"></video>
    <canvas id="approve-canvas" style="display:none;"></canvas>
    <button class="btn btn-secondary" id="approve-capture-btn" style="display:none;font-size:.85rem;margin-bottom:.5rem;" onclick="captureApproveFace()">拍照</button>
    <img id="approve-preview" style="display:none;width:80px;border-radius:6px;border:2px solid #27ae60;margin-bottom:.5rem;">
    <button class="btn btn-primary" onclick="submitApprove()" style="width:100%;">核准並建立帳號</button>
    <div id="approve-msg" style="font-size:.9rem;margin-top:.5rem;min-height:1.2em;"></div>
  </div>
</div>
```

- [ ] **Step 4: 新增設備管理 JS**

在 dashboard.html 的 `<script>` 區塊內（`loadStores();` 之前）新增：

```javascript
// 設備管理
var approveStream = null;
var approveFaceImage = null;

function loadDevices() {
  fetch('/admin/devices').then(function(r) { return r.json(); }).then(function(devices) {
    document.getElementById('devices-table').style.display = 'table';
    var tbody = document.getElementById('devices-tbody');
    tbody.innerHTML = devices.map(function(d) {
      var statusBadge = d.is_revoked
        ? '<span class="badge badge-inactive">已掛失</span>'
        : (d.is_approved ? '<span class="badge badge-active">已核准</span>' : '<span class="badge badge-user">待核准</span>');
      var actions = '';
      if (!d.is_approved && !d.is_revoked) {
        actions += '<button class="btn btn-primary" style="font-size:.8rem;padding:.3rem .7rem;" onclick="openApproveModal(' + d.id + ')">設定並核准</button>';
      }
      if (d.is_approved && !d.is_revoked) {
        actions += '<button class="btn btn-secondary" style="font-size:.8rem;padding:.3rem .7rem;color:#dc3545;" onclick="revokeDevice(' + d.id + ')">掛失</button>';
      }
      if (d.is_revoked) {
        actions += '<button class="btn btn-secondary" style="font-size:.8rem;padding:.3rem .7rem;" onclick="unrevokeDevice(' + d.id + ')">恢復</button>';
      }
      actions += ' <button class="btn btn-secondary" style="font-size:.8rem;padding:.3rem .7rem;color:#dc3545;" onclick="deleteDevice(' + d.id + ')">刪除</button>';
      return '<tr>'
        + '<td>' + d.device_name + '</td>'
        + '<td>' + statusBadge + '</td>'
        + '<td>' + (d.username || '—') + '</td>'
        + '<td>' + (d.store || '—') + '</td>'
        + '<td style="font-size:.8rem;">' + d.created_at + '</td>'
        + '<td style="font-size:.8rem;">' + d.last_seen_at + '</td>'
        + '<td>' + actions + '</td>'
        + '</tr>';
    }).join('');
  });
}

function openApproveModal(deviceId) {
  document.getElementById('approve-device-id').value = deviceId;
  document.getElementById('approve-username').value = '';
  document.getElementById('approve-pin').value = '';
  document.getElementById('approve-store').value = '';
  document.getElementById('approve-role').value = 'user';
  document.getElementById('approve-msg').textContent = '';
  document.getElementById('approve-preview').style.display = 'none';
  document.getElementById('approve-modal').style.display = 'flex';
  approveFaceImage = null;
}

function startApproveCamera() {
  var video = document.getElementById('approve-video');
  video.style.display = 'block';
  document.getElementById('approve-capture-btn').style.display = 'inline-block';
  document.getElementById('approve-cam-btn').disabled = true;
  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
    .catch(function() { return navigator.mediaDevices.getUserMedia({ video: true, audio: false }); })
    .then(function(s) { approveStream = s; video.srcObject = s; })
    .catch(function() { document.getElementById('approve-msg').textContent = '無法開啟鏡頭'; });
}

function captureApproveFace() {
  var video = document.getElementById('approve-video');
  var canvas = document.getElementById('approve-canvas');
  if (!approveStream || video.readyState < 2) return;
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);
  approveFaceImage = canvas.toDataURL('image/jpeg', 0.85);
  var preview = document.getElementById('approve-preview');
  preview.src = approveFaceImage;
  preview.style.display = 'block';
}

function submitApprove() {
  var deviceId = document.getElementById('approve-device-id').value;
  var username = document.getElementById('approve-username').value.trim();
  var pin = document.getElementById('approve-pin').value.trim();
  var store = document.getElementById('approve-store').value;
  var role = document.getElementById('approve-role').value;
  var msgEl = document.getElementById('approve-msg');
  if (!username || !pin) { msgEl.textContent = '請填寫帳號和 PIN'; msgEl.style.color = '#dc3545'; return; }
  if (!approveFaceImage) { msgEl.textContent = '請先拍攝人臉'; msgEl.style.color = '#dc3545'; return; }
  msgEl.textContent = '處理中…';
  msgEl.style.color = '#666';
  fetch('/admin/devices/' + deviceId + '/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username, pin: pin, store: store, role: role, face_image: approveFaceImage })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.status === 'ok') {
      msgEl.textContent = '帳號建立並核准成功！';
      msgEl.style.color = '#28a745';
      if (approveStream) { approveStream.getTracks().forEach(function(t) { t.stop(); }); approveStream = null; }
      setTimeout(function() {
        document.getElementById('approve-modal').style.display = 'none';
        loadDevices();
        location.reload();
      }, 1200);
    } else {
      msgEl.textContent = data.message || '操作失敗';
      msgEl.style.color = '#dc3545';
    }
  }).catch(function() { msgEl.textContent = '連線錯誤'; msgEl.style.color = '#dc3545'; });
}

function revokeDevice(id) {
  if (!confirm('確定要掛失此設備？')) return;
  fetch('/admin/devices/' + id + '/revoke', { method: 'POST' }).then(function() { loadDevices(); });
}

function unrevokeDevice(id) {
  fetch('/admin/devices/' + id + '/unrervoke', { method: 'POST' }).then(function() { loadDevices(); });
}

function deleteDevice(id) {
  if (!confirm('確定要刪除此設備？')) return;
  fetch('/admin/devices/' + id, { method: 'DELETE' }).then(function() { loadDevices(); });
}
```

- [ ] **Step 5: Commit**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/admin/routes.py app_unified/templates/admin/dashboard.html
git commit -m "feat: admin dashboard device management (approve, revoke, delete)"
```

---

### Task 8: 執行 Migration + 更新 SW Cache + 整合測試

**Files:**
- Modify: `app_unified/static/sw.js`（cache 版本更新）

- [ ] **Step 1: 更新 SW cache 版本**

修改 `app_unified/static/sw.js` 第 8 行：

```javascript
const CACHE_NAME = 'note-weather-v7';
```

- [ ] **Step 2: 最終 Commit + Push**

```bash
cd /home/hirain0126/projects/webapp
git add app_unified/static/sw.js
git commit -m "feat: SW cache v7 for stealth vault phase 1"
git push origin main
```

- [ ] **Step 3: 執行 Migration（Zeabur）**

在 Zeabur 的 app-unified terminal 或透過 Zeabur AI 執行：

```bash
python migrations/versions/004_trusted_devices.py
```

- [ ] **Step 4: 手動測試流程**

1. **種子模式測試：**
   - 清除瀏覽器資料
   - 打開天氣頁面
   - 確認出現「系統初始化」設定介面
   - 建立第一位 admin
   - 確認建立後重新載入，初始化介面不再出現

2. **設備綁定測試：**
   - 用另一台設備/瀏覽器打開天氣頁面
   - 確認只看到天氣（無任何 Notes 痕跡）
   - 確認 DevTools Network 裡沒有 secure-loader 請求
   - Admin 登入後台 → 設備管理 → 看到新設備 → 設定並核准
   - 新設備重新載入天氣頁面 → 可以連點 6 下進入

3. **掛失測試：**
   - Admin 對某設備按「掛失」
   - 該設備重新載入 → 只有天氣，連點無效

4. **店別 OFF 測試：**
   - Admin 將某店設為 OFF
   - 該店員工設備重新載入 → 連點無效
