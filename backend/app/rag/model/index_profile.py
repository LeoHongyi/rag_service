import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, id_key


class IndexProfile(Base):
    """不可变的文档索引配置快照。"""

    __tablename__ = 'rag_index_profile'
    __table_args__ = (sa.UniqueConstraint('profile_hash', name='uq_rag_index_profile_hash'),)

    id: Mapped[id_key] = mapped_column(init=False)
    profile_hash: Mapped[str] = mapped_column(sa.String(64), index=True, comment='配置哈希')
    parser_name: Mapped[str] = mapped_column(sa.String(128), comment='解析器名称')
    parser_version: Mapped[str] = mapped_column(sa.String(64), comment='解析器版本')
    chunker_name: Mapped[str] = mapped_column(sa.String(128), comment='切分器名称')
    chunker_version: Mapped[str] = mapped_column(sa.String(64), comment='切分器版本')
    chunk_size: Mapped[int] = mapped_column(comment='切片长度')
    chunk_overlap: Mapped[int] = mapped_column(comment='切片重叠长度')
    tokenizer_name: Mapped[str] = mapped_column(sa.String(128), comment='分词器名称')
    tokenizer_version: Mapped[str] = mapped_column(sa.String(64), comment='分词器版本')
    embedding_model: Mapped[str] = mapped_column(sa.String(256), comment='Embedding 模型')
    embedding_dimensions: Mapped[int] = mapped_column(comment='向量维度')
    lexical_config: Mapped[str] = mapped_column(sa.String(64), comment='词法检索配置')
    embedding_instruction: Mapped[str | None] = mapped_column(
        sa.String(512), default=None, comment='Embedding 指令版本'
    )
