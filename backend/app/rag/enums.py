from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    READY = 'READY'
    FAILED = 'FAILED'
    DELETING = 'DELETING'


class QueryMode(StrEnum):
    BASIC = 'basic'
    AGENTIC = 'agentic'
    AUTO = 'auto'


class OutboxStatus(StrEnum):
    """Outbox 事件状态。"""

    PENDING = 'PENDING'
    DISPATCHED = 'DISPATCHED'
    FAILED = 'FAILED'
    DEAD = 'DEAD'
