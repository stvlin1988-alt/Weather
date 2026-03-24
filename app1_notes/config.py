import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, os.getenv("DB_PATH", "../shared/database/app.db")))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # Database — supports DATABASE_URL for PostgreSQL (e.g. Zeabur), fallback to SQLite
    _db_url = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True}
        if _db_url.startswith("postgresql")
        else {"connect_args": {"check_same_thread": False}}
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    APP2_URL = os.getenv("APP2_URL", "http://localhost:5001")
    FACE_PHOTOS_DIR = os.path.join(BASE_DIR, "static", "face_photos")
