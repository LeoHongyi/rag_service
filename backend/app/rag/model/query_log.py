import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, id_key


class QueryLog(Base):
    """RAG 查询诊断日志"""

    __tablename__ = 'rag_query_log'

    id: Mapped[id_key] = mapped_column(init=False)
    owner_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='查询用户 ID')
    knowledge_base_ids: Mapped[list[int]] = mapped_column(sa.JSON, comment='知识库 ID 列表')
    requested_mode: Mapped[str] = mapped_column(sa.String(16), comment='请求模式')
    effective_mode: Mapped[str] = mapped_column(sa.String(16), comment='实际模式')
    status: Mapped[str] = mapped_column(sa.String(32), comment='执行状态')
    retrieval_rounds: Mapped[int] = mapped_column(default=1, comment='检索轮数')
    tool_calls: Mapped[int] = mapped_column(default=0, comment='工具调用次数')
    source_count: Mapped[int] = mapped_column(default=0, comment='来源数量')
    latency_ms: Mapped[int] = mapped_column(default=0, comment='耗时毫秒')
    trace_id: Mapped[str | None] = mapped_column(sa.String(64), default=None, comment='追踪 ID')
