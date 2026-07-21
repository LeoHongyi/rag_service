import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.rag.enums import DocumentStatus
from backend.common.model import Base, UniversalText, id_key


class Document(Base):
    """RAG 原始文档"""

    __tablename__ = 'rag_document'
    __table_args__ = (sa.Index('ix_rag_document_kb_status', 'knowledge_base_id', 'status'),)

    id: Mapped[id_key] = mapped_column(init=False)
    knowledge_base_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='知识库 ID')
    filename: Mapped[str] = mapped_column(sa.String(256), comment='原始文件名')
    file_type: Mapped[str] = mapped_column(sa.String(16), comment='文件类型')
    storage_key: Mapped[str] = mapped_column(sa.String(512), unique=True, comment='存储对象键')
    file_size: Mapped[int] = mapped_column(sa.BigInteger, comment='文件字节数')
    content_hash: Mapped[str] = mapped_column(sa.String(64), index=True, comment='内容哈希')

    mime_type: Mapped[str | None] = mapped_column(sa.String(128), default=None, comment='MIME 类型')
    parsed_content: Mapped[str | None] = mapped_column(UniversalText, default=None, comment='解析文本')
    status: Mapped[DocumentStatus] = mapped_column(sa.String(32), default=DocumentStatus.PENDING, comment='索引状态')
    error_message: Mapped[str | None] = mapped_column(sa.String(512), default=None, comment='失败摘要')
    chunk_count: Mapped[int] = mapped_column(default=0, comment='切片数量')
    index_version: Mapped[int] = mapped_column(default=1, comment='索引版本')
    index_profile_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, default=None, index=True, comment='索引配置快照 ID'
    )
