import asyncio
import os

import pytest

from backend.scripts.run_rag_celery_fault_injection import run_fault_injection

pytestmark = pytest.mark.skipif(
    os.getenv('RAG_RUN_CELERY_FAULT_INJECTION') != '1',
    reason='需要显式启用真实 Celery Worker/Beat 故障注入验证',
)


def test_real_worker_and_beat_recover_index_failures() -> None:
    report = asyncio.run(run_fault_injection())

    assert report['timeout_retry']['final_status'] == 'FAILED'
    assert report['timeout_retry']['retry_observed'] is True
    assert report['worker_interruption']['final_status'] == 'READY'
    assert report['worker_interruption']['beat_recovery_observed'] is True
    assert report['worker_interruption']['chunk_count'] == 1
    assert report['cleanup']['completed'] is True
