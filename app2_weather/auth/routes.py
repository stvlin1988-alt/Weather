import io
import base64
import hashlib
import numpy as np
import sqlite3
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_db():
    db_path = current_app.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _verify_face(face_encoding_blob, image_b64: str):
    try:
        import face_recognition
        img_data = base64.b64decode(image_b64.split(",")[-1])
        img = face_recognition.load_image_file(io.BytesIO(img_data))
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return False, 0.0
        known = np.frombuffer(face_encoding_blob, dtype=np.float64)
        distances = face_recognition.face_distance([known], encodings[0])
        match = bool(face_recognition.compare_faces([known], encodings[0], tolerance=0.45)[0])
        return match, float(1 - distances[0])
    except Exception:
        return False, 0.0


@auth_bp.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    face_image = data.get("face_image")

    if not face_image:
        return jsonify({"status": "face_mismatch"})

    # Identify user by face first
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, password_hash, face_encoding FROM users WHERE is_active=1 AND face_encoding IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    matched_row = None
    for row in rows:
        match, _ = _verify_face(row["face_encoding"], face_image)
        if match:
            matched_row = row
            break

    if not matched_row:
        return jsonify({"status": "face_mismatch"})

    if matched_row["password_hash"] != _sha256(pin):
        return jsonify({"status": "wrong_password"})

    # Generate one-time token
    token = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(seconds=30)).isoformat()
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO login_tokens (token, user_id, expires_at, used) VALUES (?, ?, ?, 0)",
            (token, matched_row["id"], expires_at)
        )
        conn.commit()
    finally:
        conn.close()

    app1_url = current_app.config.get("APP1_URL", "http://localhost:5000")
    redirect_url = f"{app1_url}/auth/token-login?token={token}"
    return jsonify({"status": "ok", "redirect_url": redirect_url})
