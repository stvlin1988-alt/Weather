import hashlib
from datetime import datetime
import numpy as np
from flask_login import UserMixin
from extensions import db

STATUS_CHOICES = ["pending", "in_progress", "resolved"]
PRIORITY_CHOICES = ["high", "medium", "low"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Store(db.Model):
    __tablename__ = "stores"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    login_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="user")
    face_encoding = db.Column(db.LargeBinary)
    face_photo_url = db.Column(db.Text)
    store = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    notes = db.relationship("Note", backref="author", lazy=True, foreign_keys="Note.user_id")

    def set_password(self, pin: str):
        self.password_hash = sha256(pin)

    def check_password(self, pin: str) -> bool:
        return self.password_hash == sha256(pin)

    def set_face_encoding(self, encoding: np.ndarray):
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
    status = db.Column(db.Text, nullable=False, default="pending")
    priority = db.Column(db.Text, nullable=False, default="medium")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    logs = db.relationship("NoteLog", backref="note", lazy=True,
                           foreign_keys="NoteLog.note_id",
                           primaryjoin="Note.id == NoteLog.note_id")


class NoteLog(db.Model):
    __tablename__ = "note_logs"

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)
    note_title = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.Text, nullable=False)   # 'edit' | 'delete'
    diff = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    operator = db.relationship("User", foreign_keys=[user_id])


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
    data_json = db.Column(db.Text, nullable=False)
    cached_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
