import sqlalchemy as sa

from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, UniversalText, id_key
from backend.core.conf import settings


class Chunk(Base):
    """RAG 文档切片"""

    __tablename__ = 'rag_chunk'
    __table_args__ = (
        sa.UniqueConstraint('document_id', 'index_version', 'chunk_index', name='uq_rag_chunk_version_index'),
        sa.Index('ix_rag_chunk_kb_document', 'knowledge_base_id', 'document_id'),
        sa.Index('ix_rag_chunk_parent_child', 'parent_chunk_id', 'is_parent'),
    )

    id: Mapped[id_key] = mapped_column(init=False)
    knowledge_base_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='知识库 ID')
    document_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='文档 ID')
    chunk_index: Mapped[int] = mapped_column(comment='文档内顺序')
    content: Mapped[str] = mapped_column(UniversalText, comment='原始正文')
    contextual_content: Mapped[str] = mapped_column(UniversalText, comment='上下文化正文')
    search_text: Mapped[str] = mapped_column(UniversalText, comment='分词检索文本')
    exact_tokens: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), comment='规范化精确检索 Token')
    content_hash: Mapped[str] = mapped_column(sa.String(64), comment='内容哈希')
    char_count: Mapped[int] = mapped_column(comment='字符数')
    token_count: Mapped[int] = mapped_column(comment='Token 估算')
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.RAG_EMBEDDING_DIMENSIONS), comment='向量（父切片不参与召回）'
    )
    index_version: Mapped[int] = mapped_column(comment='索引版本')

    parent_chunk_id: Mapped[int | None] = mapped_column(sa.BigInteger, default=None, index=True, comment='父切片 ID')
    is_parent: Mapped[bool] = mapped_column(default=False, comment='是否为仅供上下文扩展的父切片')
    heading_path: Mapped[list[str]] = mapped_column(sa.JSON, default_factory=list, comment='标题路径')
    location: Mapped[dict[str, int]] = mapped_column(sa.JSON, default_factory=dict, comment='原文位置')
