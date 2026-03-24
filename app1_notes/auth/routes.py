import io
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, flash
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User, LoginToken

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()

    if not username or not pin:
        return jsonify({"status": "error", "message": "請填寫帳號和 PIN"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "帳號已存在"}), 409

    user = User(username=username)
    user.set_password(pin)
    db.session.add(user)
    db.session.commit()
    return jsonify({"status": "ok", "user_id": user.id})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()
    image_b64 = data.get("face_image")

    user = User.query.filter_by(username=username, is_active=1).first()
    if not user or not user.check_password(pin):
        return jsonify({"status": "wrong_password"}), 401

    # Face check if user has encoding and image provided
    if user.face_encoding and image_b64 and FACE_RECOGNITION_AVAILABLE:
        match, _ = _verify_face(user, image_b64)
        if not match:
            return jsonify({"status": "face_mismatch"}), 401

    login_user(user)
    return jsonify({"status": "ok", "redirect": url_for("notes.index")})


@auth_bp.route("/token-login")
def token_login():
    token_str = request.args.get("token", "")
    record = LoginToken.query.filter_by(token=token_str, used=0).first()
    if not record:
        flash("連結無效或已過期", "error")
        return redirect(url_for("auth.login"))

    now = datetime.utcnow().isoformat()
    if record.expires_at < now:
        flash("連結已過期，請重新登入", "error")
        return redirect(url_for("auth.login"))

    record.used = 1
    db.session.commit()

    user = User.query.get(record.user_id)
    if not user or not user.is_active:
        flash("帳號不存在或已停用", "error")
        return redirect(url_for("auth.login"))

    login_user(user)
    return redirect(url_for("notes.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def _verify_face(user: User, image_b64: str):
    """Returns (match: bool, confidence: float)"""
    try:
        img_data = base64.b64decode(image_b64.split(",")[-1])
        img = face_recognition.load_image_file(io.BytesIO(img_data))
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return False, 0.0
        known = user.get_face_encoding()
        distances = face_recognition.face_distance([known], encodings[0])
        match = bool(face_recognition.compare_faces([known], encodings[0], tolerance=0.45)[0])
        confidence = float(1 - distances[0])
        return match, confidence
    except Exception:
        return False, 0.0
