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
except BaseException:
    FACE_RECOGNITION_AVAILABLE = False

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def call_llm(prompt: str, max_tokens: int = 2048) -> str:
    """呼叫 Ollama（優先）或 Anthropic（fallback）。"""
    ollama_url = current_app.config.get("OLLAMA_HOST", "")
    if ollama_url:
        import requests as _req
        resp = _req.post(
            f"{ollama_url}/v1/chat/completions",
            json={
                "model": current_app.config.get("OLLAMA_MODEL", "llama3.2:1b"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("未設定 AI 服務（請設定 OLLAMA_BASE_URL 或 ANTHROPIC_API_KEY）")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


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
    if role not in ("admin", "user"):
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
    lines = []
    for n in notes:
        s_label = STATUS_LABELS.get(n.status or "pending", n.status)
        store_tag = f"[{n.store}店]" if n.store else "[未分店]"
        author = n.author.username if n.author else "?"
        date_str = n.updated_at.strftime("%m/%d") if n.updated_at else ""
        lines.append(f"{store_tag}[{date_str}][{author}][{s_label}] {n.title}\n{n.content}")

    store_label = f"「{store}店」" if store != "all" else "全店"
    prompt = (
        f"以下是{store_label}近 {days} 天的員工筆記（依店別排列）：\n\n"
        + "\n---\n".join(lines)
        + f"\n\n請用繁體中文：\n1. 依店別條列整理主要問題與事件\n"
        "2. 標示哪些狀態為「待處理」或「處理中」需要關注\n"
        "3. 給主管的建議行動\n"
        "請用 Markdown 格式回覆。"
    )

    try:
        summary = call_llm(prompt, max_tokens=2048)
        return jsonify({"status": "ok", "summary": summary})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
