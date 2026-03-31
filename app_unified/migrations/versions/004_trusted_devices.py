"""Add trusted_devices table for device binding

Revision ID: 004
Revises: 003
Create Date: 2026-03-31
"""
revision = '004'
down_revision = '003'

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def upgrade():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trusted_devices (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            fingerprint TEXT UNIQUE NOT NULL,
            device_name TEXT NOT NULL DEFAULT 'Unknown',
            is_approved BOOLEAN NOT NULL DEFAULT false,
            is_revoked BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_trusted_devices_fingerprint ON trusted_devices(fingerprint)")

    cur.close()
    conn.close()
    print("Migration 004 done.")

if __name__ == "__main__":
    upgrade()
