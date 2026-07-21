from pathlib import Path

from backend.scripts.run_rag_celery_fault_injection import _beat_command, _celery_environment


def test_fault_injection_beat_uses_isolated_scheduler(tmp_path: Path) -> None:
    schedule_path = tmp_path / 'celerybeat-schedule'
    command = _beat_command(pidfile=tmp_path / 'celerybeat.pid', schedule_path=schedule_path)

    assert '--scheduler=celery.beat:PersistentScheduler' in command
    assert f'--schedule={schedule_path}' in command


def test_fault_injection_periodic_load_leaves_worker_capacity() -> None:
    environment = _celery_environment(broker_database=15, embedding_base_url='http://127.0.0.1:9999/v1')

    dispatch_interval = int(environment['RAG_OUTBOX_DISPATCH_INTERVAL_SECONDS'])
    repair_interval = int(environment['RAG_REPAIR_INTERVAL_SECONDS'])
    assert dispatch_interval >= 4
    assert repair_interval >= 6
