"""add rag index profile and outbox

Revision ID: 20260714_0002
Revises: 20260713_0001
Create Date: 2026-07-14
"""

from alembic import op

revision = '20260714_0002'
down_revision = '20260713_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE rag_index_profile (
        id BIGSERIAL PRIMARY KEY, profile_hash VARCHAR(64) NOT NULL,
        parser_name VARCHAR(128) NOT NULL, parser_version VARCHAR(64) NOT NULL,
        chunker_name VARCHAR(128) NOT NULL, chunker_version VARCHAR(64) NOT NULL,
        chunk_size INTEGER NOT NULL, chunk_overlap INTEGER NOT NULL,
        tokenizer_name VARCHAR(128) NOT NULL, tokenizer_version VARCHAR(64) NOT NULL,
        embedding_model VARCHAR(256) NOT NULL, embedding_dimensions INTEGER NOT NULL,
        embedding_instruction VARCHAR(512), lexical_config VARCHAR(64) NOT NULL,
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ,
        CONSTRAINT uq_rag_index_profile_hash UNIQUE(profile_hash)
    )""")
    op.execute('CREATE INDEX ix_rag_index_profile_profile_hash ON rag_index_profile(profile_hash)')
    op.execute('ALTER TABLE rag_document ADD COLUMN index_profile_id BIGINT REFERENCES rag_index_profile(id)')
    op.execute('CREATE INDEX ix_rag_document_index_profile_id ON rag_document(index_profile_id)')
    op.execute("""
    CREATE TABLE rag_outbox_event (
        id BIGSERIAL PRIMARY KEY, event_type VARCHAR(64) NOT NULL,
        aggregate_id BIGINT NOT NULL, payload TEXT NOT NULL, dedupe_key VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'PENDING', dispatch_attempts INTEGER NOT NULL DEFAULT 0,
        last_error VARCHAR(512), dispatched_time TIMESTAMPTZ,
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ,
        CONSTRAINT uq_rag_outbox_dedupe UNIQUE(event_type, aggregate_id, dedupe_key)
    )""")
    op.execute('CREATE INDEX ix_rag_outbox_status_created ON rag_outbox_event(status, created_time)')
    op.execute('CREATE INDEX ix_rag_outbox_aggregate_id ON rag_outbox_event(aggregate_id)')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS rag_outbox_event')
    op.execute('ALTER TABLE rag_document DROP COLUMN IF EXISTS index_profile_id')
    op.execute('DROP TABLE IF EXISTS rag_index_profile')
