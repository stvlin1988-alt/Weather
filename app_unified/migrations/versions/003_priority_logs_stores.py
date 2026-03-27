"""Add stores table, note_logs table, priority and updated_by to notes

Revision ID: 003
Revises: 002
Create Date: 2026-03-27
"""
revision = '003'
down_revision = '002'

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
        CREATE TABLE IF NOT EXISTS stores (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            login_enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    cur.execute("""
        INSERT INTO stores (name)
        VALUES ('B'),('C'),('D'),('E'),('F'),('G'),('J'),('JJ'),('K'),('Q'),('S')
        ON CONFLICT (name) DO NOTHING
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS note_logs (
            id SERIAL PRIMARY KEY,
            note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,
            note_title TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            diff TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_note_logs_created_at ON note_logs(created_at)")

    cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'medium'")
    cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS updated_by INTEGER REFERENCES users(id)")
    cur.execute("UPDATE notes SET status='in_progress' WHERE status='tracking'")

    cur.close()
    conn.close()
    print("Migration 003 done.")

if __name__ == "__main__":
    upgrade()
