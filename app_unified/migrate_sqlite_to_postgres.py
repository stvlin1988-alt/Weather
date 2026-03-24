#!/usr/bin/env python3
"""
One-time migration: SQLite → PostgreSQL + upload face photos to Cloudflare R2.

Usage:
  1. Set DATABASE_URL to PostgreSQL connection string in .env
  2. Run flask db upgrade to create PG schema first
  3. python migrate_sqlite_to_postgres.py --sqlite-path ../shared/database/app.db

The script:
  - Reads all users, notes, login_tokens from SQLite
  - Converts face_encoding from pickle → numpy.tobytes()
  - Uploads face photos from local disk to Cloudflare R2
  - Inserts data into PostgreSQL
"""
import sys
import os
import sqlite3
import argparse
import hashlib
import json
import io
from datetime import datetime

# Allow imports from app_unified directory
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()


def parse_dt(value):
    """Parse ISO string or return datetime as-is."""
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return datetime.utcnow()


def encoding_pickle_to_numpy(blob):
    """Convert pickle-serialized numpy array to raw bytes."""
    if not blob:
        return None
    try:
        import pickle
        import numpy as np
        arr = pickle.loads(blob)
        return arr.astype(np.float64).tobytes()
    except Exception as e:
        print(f"  [WARN] Could not convert face encoding: {e}")
        return None


def upload_photo_to_r2(photo_path_rel: str, user_id: int, app) -> str | None:
    """Upload face photo from local disk to R2, return object key."""
    if not photo_path_rel:
        return None

    # Build absolute path — photo_path is relative to app1_notes/static/
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'app1_notes', 'static')
    abs_path = os.path.normpath(os.path.join(base_dir, photo_path_rel))

    if not os.path.exists(abs_path):
        print(f"  [WARN] Photo not found: {abs_path}")
        return None

    with app.app_context():
        import storage as r2
        with open(abs_path, 'rb') as f:
            return r2.upload_face_photo(f.read(), user_id)


def migrate(sqlite_path: str, dry_run: bool = False):
    from app import create_app
    from extensions import db
    from models import User, Note, LoginToken

    app = create_app()

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    print(f"Connected to SQLite: {sqlite_path}")

    with app.app_context():
        # Clear target tables (in order due to FK)
        if not dry_run:
            db.session.execute(db.text("DELETE FROM login_tokens"))
            db.session.execute(db.text("DELETE FROM notes"))
            db.session.execute(db.text("DELETE FROM users"))
            db.session.commit()
            print("Cleared existing PG data")

        # Migrate users
        users = conn.execute("SELECT * FROM users").fetchall()
        id_map = {}
        print(f"\nMigrating {len(users)} users…")
        for row in users:
            face_enc_bytes = encoding_pickle_to_numpy(row['face_encoding'])
            face_url = upload_photo_to_r2(row['face_photo_path'], row['id'], app)
            if face_url:
                print(f"  Uploaded photo for user {row['username']} → {face_url}")

            u = User(
                id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                role=row['role'] or 'user',
                face_encoding=face_enc_bytes,
                face_photo_url=face_url,
                created_at=parse_dt(row['created_at']),
                is_active=bool(row['is_active']),
            )
            if not dry_run:
                db.session.merge(u)
            print(f"  User: {row['username']} (id={row['id']}, face={'yes' if face_enc_bytes else 'no'})")
        if not dry_run:
            db.session.commit()

        # Migrate notes
        notes = conn.execute("SELECT * FROM notes").fetchall()
        print(f"\nMigrating {len(notes)} notes…")
        for row in notes:
            n = Note(
                id=row['id'],
                user_id=row['user_id'],
                title=row['title'] or '',
                content=row['content'] or '',
                ai_summary=row['ai_summary'],
                ai_outline=row['ai_outline'],
                store=row['store'],
                created_at=parse_dt(row['created_at']),
                updated_at=parse_dt(row['updated_at']),
            )
            if not dry_run:
                db.session.merge(n)
        if not dry_run:
            db.session.commit()
        print(f"  Done.")

        # Migrate login_tokens (skip expired ones)
        tokens = conn.execute(
            "SELECT * FROM login_tokens WHERE used=0"
        ).fetchall()
        print(f"\nMigrating {len(tokens)} active tokens…")
        for row in tokens:
            t = LoginToken(
                id=row['id'],
                token=row['token'],
                user_id=row['user_id'],
                expires_at=parse_dt(row['expires_at']),
                used=bool(row['used']),
            )
            if not dry_run:
                db.session.merge(t)
        if not dry_run:
            db.session.commit()
        print(f"  Done.")

    conn.close()
    print("\n✅ Migration complete!" if not dry_run else "\n✅ Dry run complete (no data written).")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate SQLite → PostgreSQL')
    parser.add_argument('--sqlite-path', default='../shared/database/app.db',
                        help='Path to SQLite database file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview migration without writing to PostgreSQL')
    args = parser.parse_args()

    sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.sqlite_path))
    migrate(sqlite_path, dry_run=args.dry_run)
