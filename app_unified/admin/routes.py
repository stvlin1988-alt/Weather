import io
import base64
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, abort, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User, Note, STORES, STATUS_CHOICES

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def require_admin():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    require_admin()
    users = User.query.order_by(User.created_at.desc()).all()
    notes = Note.query.order_by(Note.updated_at.desc()).limit(20).all()
    return render_template("admin/dashboard.html", users=users, notes=notes,
                           stores=STORES, status_choices=STATUS_CHOICES)


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

    user = User(username=username, store=store if store in STORES else None)
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
    user.store = store if store in STORES else None
    db.session.commit()
    return jsonify({"status": "ok", "store": user.store})


@admin_bp.route("/ai/store-summary", methods=["POST"])
@login_required
def store_summary():
    require_admin()
    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"status": "error", "message": "未設定 Anthropic API Key"}), 503

    data = request.get_json(silent=True) or {}
    store = data.get("store", "all")
    days = int(data.get("days", 7))
    since = datetime.utcnow() - timedelta(days=days)

    query = Note.query.filter(Note.updated_at >= since)
    if store != "all" and store in STORES:
        query = query.filter_by(store=store)
    notes = query.order_by(Note.store, Note.updated_at.desc()).all()

    if not notes:
        return jsonify({"status": "ok", "summary": "（近期無筆記）"})

    STATUS_LABELS = {
        "pending": "待處理", "in_progress": "處理中",
        "tracking": "持續追蹤", "resolved": "已解決",
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
        "2. 標示哪些狀態為「待處理」或「持續追蹤」需要關注\n"
        "3. 給主管的建議行動\n"
        "請用 Markdown 格式回覆。"
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"status": "ok", "summary": msg.content[0].text})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
