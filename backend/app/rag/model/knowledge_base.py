import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, id_key


class KnowledgeBase(Base):
    """RAG 知识库"""

    __tablename__ = 'rag_knowledge_base'
    __table_args__ = (sa.UniqueConstraint('owner_id', 'name', 'deleted', name='uq_rag_kb_owner_name_deleted'),)

    id: Mapped[id_key] = mapped_column(init=False)
    owner_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='所有者用户 ID')
    name: Mapped[str] = mapped_column(sa.String(128), comment='知识库名称')
    description: Mapped[str | None] = mapped_column(sa.String(512), default=None, comment='知识库描述')
    is_public: Mapped[bool] = mapped_column(default=False, comment='是否公开')
    document_count: Mapped[int] = mapped_column(default=0, comment='可用文档数量')
    chunk_count: Mapped[int] = mapped_column(default=0, comment='可用切片数量')
