import io
import base64
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, abort, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User, Note, Store, NoteLog, STATUS_CHOICES

try:
    import face_recognition_models
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except BaseException as _e:
    import logging as _log
    _log.getLogger(__name__).warning("face_recognition import failed: %s", _e)
    FACE_RECOGNITION_AVAILABLE = False

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _call_gemini(prompt: str, max_tokens: int) -> str:
    """Gemini 1.5 Flash（免費方案）"""
    api_key = current_app.config.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    import requests as _req
    model = current_app.config.get("GEMINI_MODEL", "gemini-1.5-flash")
    resp = _req.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_ollama(prompt: str, max_tokens: int) -> str:
    """Ollama（自架 LLM）"""
    ollama_url = current_app.config.get("OLLAMA_HOST", "").strip()
    if not ollama_url:
        raise ValueError("OLLAMA_HOST not set")
    if not ollama_url.startswith(("http://", "https://")):
        ollama_url = f"http://{ollama_url}"
    import requests as _req
    model = current_app.config.get("OLLAMA_MODEL", "llama3.2:1b")
    # 先嘗試 OpenAI 相容 API，失敗則用 Ollama 原生 API
    try:
        resp = _req.post(
            f"{ollama_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except (_req.exceptions.HTTPError, KeyError):
        pass
    resp = _req.post(
        f"{ollama_url}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    """Anthropic Claude"""
    api_key = current_app.config.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def call_llm(prompt: str, max_tokens: int = 2048) -> str:
    """依序嘗試：Gemini → Ollama → Anthropic"""
    import time
    import logging
    logger = logging.getLogger("call_llm")
    errors = []
    for name, fn in [("Gemini", _call_gemini), ("Ollama", _call_ollama), ("Anthropic", _call_anthropic)]:
        try:
            logger.warning("=== LLM: trying %s ===", name)
            t0 = time.time()
            result = fn(prompt, max_tokens)
            elapsed = time.time() - t0
            logger.warning("=== LLM: %s OK, %.1f sec, %d chars ===", name, elapsed, len(result))
            return result
        except Exception as e:
            logger.warning("=== LLM: %s FAILED: %s ===", name, e)
            errors.append(f"{name}: {e}")
    raise ValueError("所有 AI 服務都無法使用：" + "; ".join(errors))


def require_admin():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    require_admin()
    users = User.query.order_by(User.created_at.desc()).all()
    notes = Note.query.order_by(Note.updated_at.desc()).limit(20).all()
    stores = [s.name for s in Store.query.order_by(Store.name).all()]
    return render_template("admin/dashboard.html", users=users, notes=notes,
                           stores=stores, status_choices=STATUS_CHOICES)


@admin_bp.route("/users/create", methods=["POST"])
@login_required
def create_user():
    require_admin()
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()
    face_image = data.get("face_image")
    store = (data.get("store") or "").strip()

    if not username or not pin:
        return jsonify({"status": "error", "message": "請填寫帳號和 PIN"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "帳號已存在"}), 409

    valid_stores = [s.name for s in Store.query.all()]
    user = User(username=username, store=store if store in valid_stores else None)
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
    db.session.flush()  # get user.id before upload

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


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({"status": "error", "message": "不可停用自己"}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({"status": "ok", "is_active": user.is_active})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({"status": "error", "message": "不可刪除自己"}), 400
    # Log 保留（note_id/user_id 已設 ON DELETE SET NULL，30 天後自動清理）
    Note.query.filter_by(user_id=user.id).delete()
    Note.query.filter_by(updated_by=user.id).update({"updated_by": None})
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/users/<int:user_id>/set-role", methods=["POST"])
@login_required
def set_role(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    role = data.get("role", "user")
    if role not in ("super_admin", "admin", "user"):
        return jsonify({"status": "error", "message": "角色無效"}), 400
    user.role = role
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/users/<int:user_id>/set-store", methods=["POST"])
@login_required
def set_store(user_id):
    require_admin()
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    store = data.get("store", "")
    valid_stores = [s.name for s in Store.query.all()]
    user.store = store if store in valid_stores else None
    db.session.commit()
    return jsonify({"status": "ok", "store": user.store})


@admin_bp.route("/ai/store-summary", methods=["POST"])
@login_required
def store_summary():
    require_admin()
    data = request.get_json(silent=True) or {}
    store = data.get("store", "all")
    days = int(data.get("days", 7))
    since = datetime.utcnow() - timedelta(days=days)

    valid_stores = [s.name for s in Store.query.all()]
    query = Note.query.filter(Note.updated_at >= since)
    if store != "all" and store in valid_stores:
        query = query.filter_by(store=store)
    notes = query.order_by(Note.store, Note.updated_at.desc()).all()

    if not notes:
        return jsonify({"status": "ok", "summary": "（近期無筆記）"})

    STATUS_LABELS = {
        "pending": "待處理", "in_progress": "處理中",
        "resolved": "已解決",
    }
    PRIORITY_LABELS = {
        "high": "高", "medium": "中", "low": "低",
    }
    lines = []
    for n in notes:
        s_label = STATUS_LABELS.get(n.status or "pending", n.status)
        p_label = PRIORITY_LABELS.get(n.priority or "medium", n.priority)
        store_tag = f"[{n.store}店]" if n.store else "[未分店]"
        author = n.author.username if n.author else "?"
        date_str = n.updated_at.strftime("%m/%d") if n.updated_at else ""
        lines.append(f"{store_tag}[{date_str}][{author}][{s_label}][優先:{p_label}] {n.title}\n{n.content}")

    store_label = f"「{store}店」" if store != "all" else "全店"
    if store == "all":
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
        return jsonify({"status": "ok", "summary": summary})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
        role=role if role in ("super_admin", "admin", "user") else "user",
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


@admin_bp.route("/devices/<int:device_id>/unrevoke", methods=["POST"])
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


# ── 店家管理 ──────────────────────────────────────────────

@admin_bp.route("/stores", methods=["GET"])
@login_required
def list_stores():
    require_admin()
    stores = Store.query.order_by(Store.name).all()
    return jsonify([{"name": s.name, "login_enabled": s.login_enabled} for s in stores])


@admin_bp.route("/stores", methods=["POST"])
@login_required
def create_store():
    require_admin()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip().upper()
    if not name:
        return jsonify({"status": "error", "message": "請填寫店名"}), 400
    if Store.query.filter_by(name=name).first():
        return jsonify({"status": "error", "message": "店家已存在"}), 409
    db.session.add(Store(name=name))
    db.session.commit()
    return jsonify({"status": "ok", "name": name}), 201


@admin_bp.route("/stores/<name>", methods=["DELETE"])
@login_required
def delete_store(name):
    require_admin()
    store = Store.query.filter_by(name=name).first_or_404()
    db.session.delete(store)
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/stores/<name>/toggle-login", methods=["POST"])
@login_required
def toggle_store_login(name):
    require_admin()
    store = Store.query.filter_by(name=name).first_or_404()
    store.login_enabled = not store.login_enabled
    db.session.commit()
    return jsonify({"status": "ok", "login_enabled": store.login_enabled})


# ── 操作 Log ──────────────────────────────────────────────

@admin_bp.route("/logs", methods=["GET"])
@login_required
def get_logs():
    require_admin()
    # 自動清理 30 天前的記錄
    cutoff = datetime.utcnow() - timedelta(days=30)
    NoteLog.query.filter(NoteLog.created_at < cutoff).delete()
    db.session.commit()

    logs = NoteLog.query.order_by(NoteLog.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": l.id,
        "note_id": l.note_id,
        "note_title": l.note_title,
        "operator": l.operator.username if l.operator else "?",
        "action": l.action,
        "diff": l.diff,
        "created_at": l.created_at.strftime("%Y/%m/%d %H:%M") if l.created_at else "",
    } for l in logs])
