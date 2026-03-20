"""001 initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-20

Changes from SQLite schema:
- BLOB → BYTEA (face_encoding stored as numpy.tobytes(), raw float64)
- TEXT datetime → TIMESTAMP WITH TIME ZONE
- INTEGER 0/1 → BOOLEAN (is_active, used)
- face_photo_path → face_photo_url (Cloudflare R2 key)
- notes: add 'store' column (was missing in init_db.py)
- new table: weather_cache
"""
from alembic import op
import sqlalchemy as sa


revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('username', sa.Text(), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='user'),
        sa.Column('face_encoding', sa.LargeBinary(), nullable=True),
        sa.Column('face_photo_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )

    op.create_table(
        'notes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False, server_default=''),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('ai_outline', sa.Text(), nullable=True),
        sa.Column('store', sa.Text(), nullable=True),          # Fix: was missing in init_db.py
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_notes_user_id', 'notes', ['user_id'])
    op.create_index('ix_notes_updated_at', 'notes', ['updated_at'])

    op.create_table(
        'login_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token', sa.Text(), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_index('ix_login_tokens_token', 'login_tokens', ['token'])

    op.create_table(
        'weather_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('city_key', sa.Text(), nullable=False, unique=True),
        sa.Column('data_json', sa.Text(), nullable=False),
        sa.Column('cached_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )


def downgrade() -> None:
    op.drop_table('weather_cache')
    op.drop_table('login_tokens')
    op.drop_table('notes')
    op.drop_table('users')
