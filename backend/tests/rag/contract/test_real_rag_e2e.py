import asyncio
import os

import pytest

from backend.scripts.run_rag_e2e import run_e2e

pytestmark = pytest.mark.skipif(
    os.getenv('RAG_RUN_REAL_E2E') != '1',
    reason='需要真实基础设施（pgvector/Redis）、已初始化的数据库与真实供应商凭据；显式设置 RAG_RUN_REAL_E2E=1 后运行',
)


def test_real_rag_end_to_end() -> None:
    report = asyncio.run(run_e2e())

    assert report['final_index_status'] == 'READY', report.get('error_message')
    assert report['chunk_count'] > 0
    assert report['retrieve_hit'] is True
    assert report['answer_status'] == 'answered'
    assert report['answer_contains_fact'] is True
    assert report['answer_cites_sources'] is True
    assert report['answer2_status'] == 'answered'
    assert report['kb_ids_cap_rejected'] is True
    assert report['delete_accepted'] is True
    assert report['async_delete_completed'] is True
    assert report['kb_delete_accepted'] is True
