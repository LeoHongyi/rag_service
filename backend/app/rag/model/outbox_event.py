from datetime import datetime

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.rag.enums import OutboxStatus
from backend.common.model import Base, UniversalText, id_key


class OutboxEvent(Base):
    """在同一数据库事务中写入的待投递任务事件。"""

    __tablename__ = 'rag_outbox_event'
    __table_args__ = (
        sa.UniqueConstraint('event_type', 'aggregate_id', 'dedupe_key', name='uq_rag_outbox_dedupe'),
        sa.Index('ix_rag_outbox_status_created', 'status', 'created_time'),
    )

    id: Mapped[id_key] = mapped_column(init=False)
    event_type: Mapped[str] = mapped_column(sa.String(64), comment='事件类型')
    aggregate_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='聚合对象 ID')
    payload: Mapped[str] = mapped_column(UniversalText, comment='JSON 事件载荷')
    dedupe_key: Mapped[str] = mapped_column(sa.String(128), comment='幂等键')
    status: Mapped[OutboxStatus] = mapped_column(sa.String(16), default=OutboxStatus.PENDING, comment='投递状态')
    dispatch_attempts: Mapped[int] = mapped_column(default=0, comment='投递次数')
    last_error: Mapped[str | None] = mapped_column(sa.String(512), default=None, comment='最后失败摘要')
    dispatched_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None, comment='投递时间'
    )
