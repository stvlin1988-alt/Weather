"""002 add user.store and note.status

Revision ID: 002
Revises: 001
Create Date: 2026-03-26

Changes:
- users: add 'store' column (employee's branch, nullable; admin is NULL)
- notes: add 'status' column (pending/in_progress/tracking/resolved)
"""
from alembic import op
import sqlalchemy as sa


revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('store', sa.Text(), nullable=True))
    op.add_column('notes', sa.Column('status', sa.Text(), nullable=False,
                                     server_default='pending'))


def downgrade() -> None:
    op.drop_column('notes', 'status')
    op.drop_column('users', 'store')
