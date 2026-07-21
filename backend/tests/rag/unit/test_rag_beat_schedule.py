import pytest

from backend.app.task.tasks.beat import get_local_beat_schedule
from backend.core.conf import settings


def test_rag_beat_schedule_excludes_blocking_demo_tasks() -> None:
    schedule = get_local_beat_schedule()
    assert all(item['task'] not in {'task_demo', 'task_demo_async', 'task_demo_params'} for item in schedule.values())
    assert {item['task'] for item in schedule.values()} >= {
        'rag_dispatch_outbox',
        'rag_repair_stuck_document',
    }


def test_rag_beat_schedule_uses_configured_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_OUTBOX_DISPATCH_INTERVAL_SECONDS', 2)
    monkeypatch.setattr(settings, 'RAG_REPAIR_INTERVAL_SECONDS', 7)

    schedule = get_local_beat_schedule()

    assert schedule['投递 RAG Outbox 事件']['schedule'].run_every.total_seconds() == pytest.approx(2)
    assert schedule['修复 RAG 卡住索引与删除补偿任务']['schedule'].run_every.total_seconds() == pytest.approx(7.0)
