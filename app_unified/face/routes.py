import io
import os
import base64
import logging
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User
import storage as r2_storage

logger = logging.getLogger(__name__)

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

face_bp = Blueprint("face", __name__, url_prefix="/face")


@face_bp.route("/settings")
@login_required
def settings():
    return render_template("face_enroll.html")


def _decode_image(image_b64: str):
    img_data = base64.b64decode(image_b64.split(",")[-1])
    return face_recognition.load_image_file(io.BytesIO(img_data)), img_data


@face_bp.route("/enroll", methods=["POST"])
@login_required
def enroll():
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"status": "error", "message": "人臉辨識功能未安裝"}), 503

    data = request.get_json(silent=True) or {}
    image_b64 = data.get("face_image")
    if not image_b64:
        return jsonify({"status": "error", "message": "缺少圖像資料"}), 400

    try:
        raw_bytes = base64.b64decode(image_b64.split(",")[-1])
        img = face_recognition.load_image_file(io.BytesIO(raw_bytes))
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return jsonify({"status": "error", "message": "未偵測到人臉，請重試"}), 422

        user = current_user
        user.set_face_encoding(encodings[0])

        # Upload photo to Cloudflare R2 (private bucket)
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG")
        jpeg_bytes = buf.getvalue()

        photo_url = r2_storage.upload_face_photo(jpeg_bytes, user.id)
        if photo_url:
            user.face_photo_url = photo_url

        db.session.commit()
        return jsonify({"status": "ok", "message": "人臉登錄成功"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@face_bp.route("/verify", methods=["POST"])
@login_required
def verify():
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"status": "error", "message": "人臉辨識功能未安裝"}), 503

    data = request.get_json(silent=True) or {}
    image_b64 = data.get("face_image")
    if not image_b64:
        return jsonify({"status": "error", "message": "缺少圖像資料"}), 400

    user = current_user
    if not user.face_encoding:
        return jsonify({"status": "error", "message": "尚未登錄人臉"}), 422

    try:
        raw_bytes = base64.b64decode(image_b64.split(",")[-1])
        img = face_recognition.load_image_file(io.BytesIO(raw_bytes))
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return jsonify({"match": False, "confidence": 0.0})

        known = user.get_face_encoding()
        distances = face_recognition.face_distance([known], encodings[0])
        match = bool(face_recognition.compare_faces([known], encodings[0], tolerance=0.62)[0])
        confidence = float(1 - distances[0])
        logger.warning("face/verify: user=%s distance=%.3f match=%s", current_user.username, float(distances[0]), match)
        return jsonify({"match": match, "confidence": round(confidence, 3)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
