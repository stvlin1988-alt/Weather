from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from extensions import db
from models import TrustedDevice, User, Store

device_bp = Blueprint("device", __name__, url_prefix="/api/v1")


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
    """以下任一情況進入種子模式：
    1. DB 沒有 admin
    2. 有 admin 但沒有任何已核准設備
    3. 所有 admin 都沒有 face_encoding（人臉資料損壞）
    """
    admins = User.query.filter_by(role="admin").all()
    if not admins:
        return True
    if TrustedDevice.query.filter_by(is_approved=True).count() == 0:
        return True
    # 所有 admin 都沒有有效的人臉資料
    if all(a.face_encoding is None for a in admins):
        return True
    return False


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
        existing.last_seen_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"status": "ok", "registered": False})
    device = TrustedDevice(
        fingerprint=fp,
        device_name=device_name or "Unknown",
        is_approved=False,
        is_revoked=False,
    )
    db.session.add(device)
    db.session.commit()
    return jsonify({"status": "ok", "registered": True}), 201


@device_bp.route("/secure-loader")
def secure_loader():
    """回傳動態載入的 JS（連點 + PIN modal + 人臉驗證）"""
    fp = request.args.get("fp", "") or request.headers.get("X-Device-FP", "")
    fp = fp.strip()
    if not is_device_authorized(fp):
        return "", 404
    return Response(_build_secure_loader_js(), mimetype="application/javascript")


@device_bp.route("/seed-setup", methods=["GET"])
def seed_setup_loader():
    """種子模式：回傳初始化設定的 JS"""
    if not is_seed_mode():
        return "", 404
    return Response(_build_seed_setup_js(), mimetype="application/javascript")


@device_bp.route("/seed-setup", methods=["POST"])
def seed_setup_submit():
    """種子模式：建立第一位 admin 或綁定現有 admin 的設備"""
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

    # 如果帳號已存在（現有 admin），驗證 PIN 後綁定設備 + 更新人臉
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        if not existing_user.check_password(pin):
            return jsonify({"status": "error", "message": "PIN 碼錯誤"}), 401
        # 更新人臉（如果之前的人臉資料損壞或不存在）
        if face_image:
            try:
                import face_recognition
                import io
                import base64
                img_data = base64.b64decode(face_image.split(",")[-1])
                img = face_recognition.load_image_file(io.BytesIO(img_data))
                encodings = face_recognition.face_encodings(img)
                if encodings:
                    existing_user.set_face_encoding(encodings[0])
            except BaseException:
                pass
        # 綁定設備
        device = TrustedDevice.query.filter_by(fingerprint=fp).first()
        if not device and fp:
            device = TrustedDevice(fingerprint=fp, device_name=device_name)
            db.session.add(device)
            db.session.flush()
        if device:
            device.user_id = existing_user.id
            device.is_approved = True
        db.session.commit()
        return jsonify({"status": "ok", "user_id": existing_user.id})

    user = User(username=username, role="admin")
    user.set_password(pin)

    if face_image:
        try:
            import face_recognition
            import io
            import base64
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
    if not device and fp:
        device = TrustedDevice(fingerprint=fp, device_name=device_name)
        db.session.add(device)
        db.session.flush()
    if device:
        device.user_id = user.id
        device.is_approved = True

    db.session.commit()
    return jsonify({"status": "ok", "user_id": user.id})


def _build_secure_loader_js():
    return r"""
(function() {
  // ── Auth Modal HTML ──
  var modalHTML = ''
    + '<div id="auth-modal">'
    + '  <div class="modal-box">'
    + '    <button class="modal-close" id="modal-close">&times;</button>'
    + '    <h2>\ud83d\udd10 進入系統</h2>'
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
        video.play().catch(function() {});
        cameraState = 'ready';
        if (indicator) indicator.style.backgroundColor = '#2ecc71';
        var msgEl = document.getElementById('modal-msg');
        if (msgEl && msgEl.textContent.indexOf('\u93e1\u982d') >= 0) { msgEl.textContent = ''; }
      })
      .catch(function() {
        cameraState = 'failed';
        if (indicator) { indicator.style.display = 'inline-block'; indicator.style.backgroundColor = '#999'; }
        var msgEl = document.getElementById('modal-msg');
        if (msgEl) { msgEl.textContent = '\u76f8\u6a5f\u7121\u6cd5\u555f\u52d5\uff0c\u8acb\u78ba\u8a8d\u700f\u89bd\u5668\u76f8\u6a5f\u6b0a\u9650\u5f8c\u91cd\u65b0\u6574\u7406'; msgEl.className = 'err'; }
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
        if (msg) { msg.textContent = '\u93e1\u982d\u555f\u52d5\u4e2d\u2026'; msg.className = ''; }
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
        showMsg('\u76f8\u6a5f\u7121\u6cd5\u555f\u52d5\uff0c\u8acb\u78ba\u8a8d\u700f\u89bd\u5668\u76f8\u6a5f\u6b0a\u9650\u5f8c\u91cd\u65b0\u6574\u7406', 'err');
      } else {
        showMsg('\u93e1\u982d\u555f\u52d5\u4e2d\uff0c\u8acb\u7a0d\u5019\u518d\u8a66', 'err');
      }
      return;
    }
    submitBtn.disabled = true;
    showMsg('\u8fa8\u8b58\u4e2d\u2026');
    fetch('/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pin, face_image: faceImage })
    }).then(function(res) { return res.json(); }).then(function(data) {
      switch (data.status) {
        case 'ok':
          showMsg('\u9a57\u8b49\u6210\u529f\uff01\u6b63\u5728\u8df3\u8f49\u2026', 'ok');
          setTimeout(function() { location.href = '/auth/s/r'; }, 800);
          break;
        case 'wrong_password':
          showMsg('PIN \u78bc\u932f\u8aa4\uff0c\u8acb\u91cd\u65b0\u8f38\u5165', 'err');
          break;
        case 'face_not_found':
          showMsg('\u932f\u8aa41', 'err');
          break;
        case 'need_face_enroll':
          showMsg('\u8acb\u806f\u7e6b\u7ba1\u7406\u54e11', 'err');
          break;
        case 'face_mismatch':
          showMsg('1\u5931\u6557\uff0c\u8acb\u91cd\u8a66', 'err');
          break;
        case 'store_disabled':
          if (modal) modal.classList.remove('open');
          showMsg('');
          var pinInput = document.getElementById('m-pin');
          if (pinInput) pinInput.value = '';
          stopCamera();
          break;
        default:
          showMsg('\u9a57\u8b49\u5931\u6557\uff0c\u8acb\u91cd\u8a66', 'err');
      }
    }).catch(function() {
      showMsg('\u9023\u7dda\u932f\u8aa4\uff0c\u8acb\u91cd\u8a66', 'err');
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
    return r"""
(function() {
  var setupHTML = ''
    + '<div id="seed-modal" style="display:flex;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center;">'
    + '  <div style="background:#fff;color:#333;border-radius:16px;padding:2rem;width:400px;max-width:95vw;">'
    + '    <h2 style="margin-bottom:1rem;color:#2c3e50;">\ud83d\udd27 \u7cfb\u7d71\u521d\u59cb\u5316</h2>'
    + '    <p style="font-size:.85rem;color:#666;margin-bottom:1rem;">\u9996\u6b21\u4f7f\u7528\uff0c\u8acb\u8a2d\u5b9a\u7ba1\u7406\u54e1\u5e33\u865f\u3002</p>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">\u5e33\u865f\u540d\u7a31</label><input type="text" id="seed-username" style="width:100%;padding:.5rem;border:1px solid #ddd;border-radius:6px;font-size:16px;"></div>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">PIN \u78bc\uff084\u4f4d\u6578\uff09</label><input type="password" id="seed-pin" maxlength="4" inputmode="numeric" style="width:100%;padding:.5rem;border:1px solid #ddd;border-radius:6px;font-size:16px;"></div>'
    + '    <div style="margin-bottom:.75rem;"><label style="display:block;font-size:.85rem;font-weight:600;margin-bottom:.25rem;">\u4eba\u81c9\u767b\u9304</label><button id="seed-cam-btn" style="padding:.5rem 1rem;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:.9rem;">\u958b\u555f\u93e1\u982d</button></div>'
    + '    <video id="seed-video" autoplay playsinline muted style="width:100%;border-radius:6px;background:#000;display:none;margin-bottom:.5rem;"></video>'
    + '    <canvas id="seed-canvas" style="display:none;"></canvas>'
    + '    <button id="seed-capture" style="display:none;padding:.5rem 1rem;border:1px solid #ddd;border-radius:6px;cursor:pointer;margin-bottom:.5rem;">\u62cd\u7167</button>'
    + '    <img id="seed-preview" style="display:none;width:100px;border-radius:6px;border:2px solid #27ae60;margin-bottom:.5rem;">'
    + '    <button id="seed-submit" style="display:block;width:100%;padding:.75rem;border-radius:8px;border:none;cursor:pointer;font-size:.95rem;font-weight:600;background:#3498db;color:#fff;margin-top:.5rem;">\u5efa\u7acb\u7ba1\u7406\u54e1</button>'
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
      .then(function(s) { seedStream = s; seedVideo.srcObject = s; seedVideo.play().catch(function() {}); })
      .catch(function() { document.getElementById('seed-msg').textContent = '\u7121\u6cd5\u958b\u555f\u93e1\u982d'; });
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
    if (!username || !pin) { msgEl.textContent = '\u8acb\u586b\u5beb\u5e33\u865f\u548c PIN'; msgEl.style.color = '#e74c3c'; return; }
    if (!seedFaceImage) { msgEl.textContent = '\u8acb\u5148\u62cd\u651d\u4eba\u81c9'; msgEl.style.color = '#e74c3c'; return; }
    msgEl.textContent = '\u5efa\u7acb\u4e2d\u2026';
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
        msgEl.textContent = '\u7ba1\u7406\u54e1\u5efa\u7acb\u6210\u529f\uff01\u91cd\u65b0\u8f09\u5165\u4e2d\u2026';
        msgEl.style.color = '#27ae60';
        if (seedStream) { seedStream.getTracks().forEach(function(t) { t.stop(); }); }
        setTimeout(function() { location.reload(); }, 1500);
      } else {
        msgEl.textContent = data.message || '\u5efa\u7acb\u5931\u6557';
        msgEl.style.color = '#e74c3c';
      }
    }).catch(function() {
      msgEl.textContent = '\u9023\u7dda\u932f\u8aa4';
      msgEl.style.color = '#e74c3c';
    });
  });
})();
"""
