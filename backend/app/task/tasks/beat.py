from typing import Any

from celery.schedules import schedule  # type: ignore[import-untyped]

from backend.app.task.utils.tzcrontab import TzAwareCrontab
from backend.core.conf import settings


def get_local_beat_schedule() -> dict[str, dict[str, Any]]:
    """获取本地 Celery beat 任务配置"""
    # 参考：https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
    return {
        '投递 RAG Outbox 事件': {
            'task': 'rag_dispatch_outbox',
            'schedule': schedule(settings.RAG_OUTBOX_DISPATCH_INTERVAL_SECONDS),
        },
        '修复 RAG 卡住索引与删除补偿任务': {
            'task': 'rag_repair_stuck_document',
            'schedule': schedule(settings.RAG_REPAIR_INTERVAL_SECONDS),
        },
        '清理操作日志': {
            'task': 'backend.app.task.tasks.db_log.tasks.delete_db_opera_log',
            'schedule': TzAwareCrontab('0', '0', day_of_week='6'),
        },
        '清理登录日志': {
            'task': 'backend.app.task.tasks.db_log.tasks.delete_db_login_log',
            'schedule': TzAwareCrontab('0', '0', day_of_month='15'),
        },
    }
