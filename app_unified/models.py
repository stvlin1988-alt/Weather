import hashlib
from datetime import datetime
import numpy as np
from flask_login import UserMixin
from extensions import db

STORES = ["B", "C", "D", "E", "F", "G", "J", "JJ", "K", "Q", "S"]
STATUS_CHOICES = ["pending", "in_progress", "tracking", "resolved"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="user")
    face_encoding = db.Column(db.LargeBinary)   # numpy.tobytes() — raw float64 binary
    face_photo_url = db.Column(db.Text)          # Cloudflare R2 URL (replaces face_photo_path)
    store = db.Column(db.Text, nullable=True)                            # 員工所屬店別；管理者為 NULL
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    notes = db.relationship("Note", backref="author", lazy=True)

    def set_password(self, pin: str):
        self.password_hash = sha256(pin)

    def check_password(self, pin: str) -> bool:
        return self.password_hash == sha256(pin)

    def set_face_encoding(self, encoding: np.ndarray):
        """Store face encoding as raw bytes (safer than pickle)."""
        self.face_encoding = encoding.astype(np.float64).tobytes()

    def get_face_encoding(self) -> np.ndarray | None:
        if self.face_encoding:
            return np.frombuffer(self.face_encoding, dtype=np.float64)
        return None

    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def active(self):
        return bool(self.is_active)


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.Text, nullable=False, default="")
    content = db.Column(db.Text, nullable=False, default="")
    ai_summary = db.Column(db.Text)
    ai_outline = db.Column(db.Text)
    store = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=False, default="pending")  # 狀態標籤（待處理預設）
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class LoginToken(db.Model):
    __tablename__ = "login_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.Text, unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)


class WeatherCache(db.Model):
    __tablename__ = "weather_cache"

    id = db.Column(db.Integer, primary_key=True)
    city_key = db.Column(db.Text, unique=True, nullable=False)
    data_json = db.Column(db.Text, nullable=False)   # JSON string
    cached_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
