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
