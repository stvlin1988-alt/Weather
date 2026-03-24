import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, os.getenv("DB_PATH", "../shared/database/app.db")))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")
    APP1_URL = os.getenv("APP1_URL", "http://localhost:5000")
    DB_PATH = DB_PATH
