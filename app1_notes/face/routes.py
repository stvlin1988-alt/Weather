import io
import os
import base64
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

face_bp = Blueprint("face", __name__, url_prefix="/face")


@face_bp.route("/settings")
@login_required
def settings():
    from flask import render_template
    return render_template("face_enroll.html")


def _decode_image(image_b64: str):
    img_data = base64.b64decode(image_b64.split(",")[-1])
    return face_recognition.load_image_file(io.BytesIO(img_data))


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
        img = _decode_image(image_b64)
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return jsonify({"status": "error", "message": "未偵測到人臉，請重試"}), 422

        user = current_user
        user.set_face_encoding(encodings[0])

        # Save photo
        photos_dir = current_app.config["FACE_PHOTOS_DIR"]
        os.makedirs(photos_dir, exist_ok=True)
        photo_name = f"{user.id}_{uuid.uuid4().hex[:8]}.jpg"
        photo_path = os.path.join(photos_dir, photo_name)
        from PIL import Image
        Image.fromarray(img).save(photo_path, "JPEG")
        user.face_photo_url = f"/static/face_photos/{photo_name}"

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
        img = _decode_image(image_b64)
        encodings = face_recognition.face_encodings(img)
        if not encodings:
            return jsonify({"match": False, "confidence": 0.0})

        known = user.get_face_encoding()
        import face_recognition as fr
        distances = fr.face_distance([known], encodings[0])
        match = bool(fr.compare_faces([known], encodings[0], tolerance=0.45)[0])
        confidence = float(1 - distances[0])
        return jsonify({"match": match, "confidence": round(confidence, 3)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
