"""add parent chunk marker

Revision ID: 20260721_0003
Revises: 20260714_0002
Create Date: 2026-07-21
"""

from alembic import op

revision = '20260721_0003'
down_revision = '20260714_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE rag_chunk ALTER COLUMN embedding DROP NOT NULL')
    op.execute('ALTER TABLE rag_chunk ADD COLUMN is_parent BOOLEAN NOT NULL DEFAULT FALSE')
    op.execute('CREATE INDEX ix_rag_chunk_parent_child ON rag_chunk(parent_chunk_id, is_parent)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_rag_chunk_parent_child')
    op.execute('ALTER TABLE rag_chunk DROP COLUMN is_parent')
    op.execute('ALTER TABLE rag_chunk ALTER COLUMN embedding SET NOT NULL')
