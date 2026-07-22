"""add exact lexical tokens

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from alembic import op

revision = '20260721_0004'
down_revision = '20260721_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE rag_chunk ADD COLUMN exact_tokens TEXT[] NOT NULL DEFAULT '{}'")
    op.execute('CREATE INDEX ix_rag_chunk_exact_tokens ON rag_chunk USING gin (exact_tokens)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_rag_chunk_exact_tokens')
    op.execute('ALTER TABLE rag_chunk DROP COLUMN exact_tokens')
