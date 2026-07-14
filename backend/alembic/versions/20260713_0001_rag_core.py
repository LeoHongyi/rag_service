"""create rag core tables

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13
"""

from alembic import op


revision = '20260713_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('''
    CREATE TABLE rag_knowledge_base (
        id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, name VARCHAR(128) NOT NULL,
        description VARCHAR(512), is_public BOOLEAN NOT NULL DEFAULT FALSE,
        document_count INTEGER NOT NULL DEFAULT 0, chunk_count INTEGER NOT NULL DEFAULT 0,
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ,
        CONSTRAINT uq_rag_kb_owner_name_deleted UNIQUE(owner_id, name, deleted)
    )''')
    op.execute('CREATE INDEX ix_rag_kb_owner_id ON rag_knowledge_base(owner_id)')
    op.execute('''
    CREATE TABLE rag_document (
        id BIGSERIAL PRIMARY KEY, knowledge_base_id BIGINT NOT NULL REFERENCES rag_knowledge_base(id),
        filename VARCHAR(256) NOT NULL, file_type VARCHAR(16) NOT NULL, mime_type VARCHAR(128),
        storage_key VARCHAR(512) NOT NULL UNIQUE, file_size BIGINT NOT NULL, content_hash VARCHAR(64) NOT NULL,
        parsed_content TEXT, status VARCHAR(32) NOT NULL DEFAULT 'PENDING', error_message VARCHAR(512),
        chunk_count INTEGER NOT NULL DEFAULT 0, index_version INTEGER NOT NULL DEFAULT 1,
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ
    )''')
    op.execute('CREATE INDEX ix_rag_document_kb_status ON rag_document(knowledge_base_id, status)')
    op.execute('CREATE INDEX ix_rag_document_content_hash ON rag_document(content_hash)')
    op.execute('''
    CREATE TABLE rag_chunk (
        id BIGSERIAL PRIMARY KEY, knowledge_base_id BIGINT NOT NULL REFERENCES rag_knowledge_base(id),
        document_id BIGINT NOT NULL REFERENCES rag_document(id), parent_chunk_id BIGINT,
        chunk_index INTEGER NOT NULL, content TEXT NOT NULL, contextual_content TEXT NOT NULL,
        search_text TEXT NOT NULL, heading_path JSONB NOT NULL DEFAULT '[]', location JSONB NOT NULL DEFAULT '{}',
        content_hash VARCHAR(64) NOT NULL, char_count INTEGER NOT NULL, token_count INTEGER NOT NULL,
        embedding vector(1024) NOT NULL, index_version INTEGER NOT NULL,
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ,
        CONSTRAINT uq_rag_chunk_version_index UNIQUE(document_id, index_version, chunk_index)
    )''')
    op.execute('CREATE INDEX ix_rag_chunk_kb_document ON rag_chunk(knowledge_base_id, document_id)')
    op.execute('CREATE INDEX ix_rag_chunk_embedding_hnsw ON rag_chunk USING hnsw (embedding vector_cosine_ops)')
    op.execute('CREATE INDEX ix_rag_chunk_search_text ON rag_chunk USING gin (to_tsvector(\'simple\', search_text))')
    op.execute('''
    CREATE TABLE rag_query_log (
        id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, knowledge_base_ids JSONB NOT NULL,
        requested_mode VARCHAR(16) NOT NULL, effective_mode VARCHAR(16) NOT NULL, status VARCHAR(32) NOT NULL,
        retrieval_rounds INTEGER NOT NULL DEFAULT 1, tool_calls INTEGER NOT NULL DEFAULT 0,
        source_count INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL DEFAULT 0, trace_id VARCHAR(64),
        created_time TIMESTAMPTZ NOT NULL DEFAULT now(), updated_time TIMESTAMPTZ,
        deleted BIGINT NOT NULL DEFAULT 0, deleted_time TIMESTAMPTZ
    )''')
    op.execute('CREATE INDEX ix_rag_query_log_owner_id ON rag_query_log(owner_id)')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS rag_query_log')
    op.execute('DROP TABLE IF EXISTS rag_chunk')
    op.execute('DROP TABLE IF EXISTS rag_document')
    op.execute('DROP TABLE IF EXISTS rag_knowledge_base')
