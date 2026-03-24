"""
Unified auth blueprint.

Two login flows:
  1. /auth/login  — username + PIN + optional face (App1 style, for web)
  2. /auth/verify — face + PIN only, no username (App2 hidden modal style)
     After verify: server writes session directly → returns {status: ok}
     Frontend navigates to /s/r (opaque endpoint) → redirects to notes
     This hides the token and target URL from DevTools.
"""
import io
import base64
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, flash, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models import User

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if not current_user.is_admin():
        abort(403)
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
@limiter.limit("10 per minute", exempt_when=lambda: current_app.config.get("TESTING"))
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    pin = str(data.get("pin") or "").strip()
    image_b64 = data.get("face_image")

    user = User.query.filter_by(username=username, is_active=True).first()
    if not user or not user.check_password(pin):
        return jsonify({"status": "wrong_password"}), 401

    # First-time login: no face enrolled yet → log in and send to face setup
    if not user.face_encoding:
        login_user(user)
        return jsonify({"status": "need_face_enroll",
                        "redirect": url_for("face.settings", first="1")})

    # Face enrolled → face image is required
    if not image_b64:
        return jsonify({"status": "face_required"})

    if FACE_RECOGNITION_AVAILABLE:
        match, _ = _verify_face(user, image_b64)
        if not match:
            return jsonify({"status": "face_mismatch"}), 401

    login_user(user)
    return jsonify({"status": "ok", "redirect": url_for("notes.index")})


@auth_bp.route("/verify", methods=["POST"])
@limiter.limit("5 per minute", exempt_when=lambda: current_app.config.get("TESTING"))
def verify():
    """
    Face + PIN verification (hidden modal flow).
    On success: logs in user server-side, returns {status: ok}.
    Frontend navigates to /s/r which redirects to notes — no token in any response.
    """
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    face_image = data.get("face_image")

    if not face_image:
        return jsonify({"status": "face_mismatch"})

    rows = User.query.filter_by(is_active=True).filter(
        User.face_encoding.isnot(None)
    ).all()

    matched_user = None
    for user in rows:
        match, _ = _verify_face(user, face_image)
        if match:
            matched_user = user
            break

    if not matched_user:
        # 區分「影像沒有人臉」vs「人臉找到但不符」
        try:
            img_data = base64.b64decode(face_image.split(",")[-1])
            img = face_recognition.load_image_file(io.BytesIO(img_data))
            any_face_found = len(face_recognition.face_locations(img, number_of_times_to_upsample=2)) > 0
        except Exception:
            any_face_found = False
        if not any_face_found:
            logger.warning("verify: no face detected in submitted image")
            return jsonify({"status": "face_not_found"})
        return jsonify({"status": "face_mismatch"})

    if not matched_user.check_password(pin):
        return jsonify({"status": "wrong_password"})

    # Server-side login — write session directly, no token in URL
    login_user(matched_user)
    return jsonify({"status": "ok"})


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# Opaque redirect endpoint — hides destination from JS/DevTools
@auth_bp.route("/s/r")
@login_required
def silent_redirect():
    return redirect(url_for("notes.index"))


def _verify_face(user: User, image_b64: str):
    """Returns (match: bool, confidence: float)"""
    try:
        img_data = base64.b64decode(image_b64.split(",")[-1])
        img = face_recognition.load_image_file(io.BytesIO(img_data))
        locations = face_recognition.face_locations(img, number_of_times_to_upsample=2)
        encodings = face_recognition.face_encodings(img, locations)
        logger.warning("_verify_face: img_size=%d bytes, locations=%d", len(img_data), len(locations))
        if not encodings:
            logger.warning("_verify_face: no face detected (img size=%d bytes)", len(img_data))
            return False, 0.0
        known = user.get_face_encoding()
        if known is None:
            return False, 0.0
        distances = face_recognition.face_distance([known], encodings[0])
        logger.warning("_verify_face: user=%s distance=%.3f", user.username, float(distances[0]))
        match = bool(face_recognition.compare_faces([known], encodings[0], tolerance=0.62)[0])
        confidence = float(1 - distances[0])
        return match, confidence
    except Exception as e:
        logger.warning("_verify_face exception: user=%s error=%s", user.username, e)
        return False, 0.0
