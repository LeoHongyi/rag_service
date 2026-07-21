from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from backend.app.rag.adapters.storage import storage
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Chunk, Document, KnowledgeBase, OutboxEvent
from backend.app.rag.service.outbox_service import enqueue_document_index
from backend.core.conf import settings
from backend.database.db import async_db_session
from backend.utils.timezone import timezone

TIMEOUT_MARKER = 'RAG_FAULT_TIMEOUT'
INTERRUPTION_MARKER = 'RAG_FAULT_WORKER_INTERRUPTION'


class FaultEmbeddingServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(('127.0.0.1', 0), FaultEmbeddingHandler)
        self.request_counts: dict[str, int] = {}
        self.request_lock = threading.Lock()
        self.interruption_started = threading.Event()

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f'http://{host}:{port}/v1'

    def next_request_count(self, marker: str) -> int:
        with self.request_lock:
            count = self.request_counts.get(marker, 0) + 1
            self.request_counts[marker] = count
            return count


class FaultEmbeddingHandler(BaseHTTPRequestHandler):
    server: FaultEmbeddingServer

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length) or b'{}')
        texts = [str(item) for item in payload.get('input', [])]
        combined = '\n'.join(texts)

        if TIMEOUT_MARKER in combined:
            self.server.next_request_count(TIMEOUT_MARKER)
            time.sleep(1.0)
        elif INTERRUPTION_MARKER in combined:
            request_count = self.server.next_request_count(INTERRUPTION_MARKER)
            if request_count == 1:
                self.server.interruption_started.set()
                time.sleep(30.0)

        dimension = int(payload.get('dimensions', 1024))
        body = json.dumps({
            'data': [
                {'index': index, 'embedding': [1.0] + [0.0] * (dimension - 1)} for index, _text in enumerate(texts)
            ]
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, _format: str, *_args: object) -> None:
        return


@dataclass
class ManagedProcess:
    process: subprocess.Popen[str]
    log_path: Path
    log_file: Any

    @classmethod
    def start(cls, *, command: list[str], env: dict[str, str], log_path: Path) -> ManagedProcess:
        log_file = log_path.open('w+', encoding='utf-8')
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return cls(process=process, log_path=log_path, log_file=log_file)

    def read_log(self) -> str:
        self.log_file.flush()
        position = self.log_file.tell()
        self.log_file.seek(0)
        content = self.log_file.read()
        self.log_file.seek(position)
        return content

    async def wait_for_log(self, *patterns: str, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'Celery 进程提前退出，退出码 {self.process.returncode}')
            content = self.read_log()
            if any(pattern in content for pattern in patterns):
                return
            await asyncio.sleep(0.1)
        raise TimeoutError('等待 Celery 进程就绪超时')

    def stop(self, *, force: bool = False) -> None:
        if self.process.poll() is None:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.killpg(self.process.pid, sig)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.log_file.close()


def _redis_url(*, database: int) -> str:
    password = settings.REDIS_PASSWORD
    authentication = f':{password}@' if password else ''
    return f'redis://{authentication}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{database}'


def _process_diagnostics(processes: list[ManagedProcess]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for process in processes:
        content = process.read_log()
        redacted_lines = [
            re.sub(r'\b(?:redis|rediss|amqp|postgresql(?:\+\w+)?|https?)://\S+', '<redacted-url>', line)
            for line in content.splitlines()
        ]
        error_lines = [line for line in redacted_lines if 'ERROR' in line or 'CRITICAL' in line or 'Traceback' in line][
            -8:
        ]
        task_lines = [
            line
            for line in redacted_lines
            if 'rag_' in line or 'Scheduler: Sending due task' in line or 'succeeded in' in line
        ][-30:]
        diagnostics.append({
            'name': process.log_path.name,
            'running': process.process.poll() is None,
            'ready': ' ready.' in content or 'beat: Starting' in content,
            'sent_due_task': 'Scheduler: Sending due task' in content,
            'dispatch_received': 'Task rag_dispatch_outbox' in content,
            'repair_received': 'Task rag_repair_stuck_document' in content,
            'errors': error_lines,
            'task_lines': task_lines,
            'tail': redacted_lines[-30:],
        })
    return diagnostics


async def _broker_diagnostics(client: Redis) -> dict[str, int]:
    return {
        'ready': await client.llen('celery'),
        'unacked': await client.hlen('unacked'),
        'unacked_index': await client.zcard('unacked_index'),
    }


async def _reserve_isolated_redis_database() -> tuple[int, Redis]:
    for database in range(15, 7, -1):
        client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            db=database,
            decode_responses=True,
        )
        if await client.dbsize() == 0:
            return database, client
        await client.aclose()
    raise RuntimeError('Redis 8-15 号数据库均非空，无法安全隔离故障注入 Broker')


def _celery_environment(*, broker_database: int, embedding_base_url: str) -> dict[str, str]:
    env = os.environ.copy()
    # ``CELERY_BROKER`` is also a Celery CLI compatibility variable. Passing
    # the project value ``redis`` directly makes Celery parse it as an AMQP
    # hostname instead of allowing ``init_celery()`` to build the Redis URL.
    env.pop('CELERY_BROKER', None)
    env.update({
        'ENVIRONMENT': 'dev',
        'CELERY_BROKER_REDIS_DATABASE': str(broker_database),
        'RAG_EMBEDDING_BASE_URL': embedding_base_url,
        'RAG_EMBEDDING_API_KEY': 'fault-injection-test-only',
        'RAG_EMBEDDING_MODEL': 'fault-injection-embedding',
        'RAG_EMBEDDING_TIMEOUT_SECONDS': '0.25',
        'RAG_INDEX_MAX_RETRIES': '1',
        'RAG_INDEX_RETRY_BACKOFF_MAX_SECONDS': '1',
        'RAG_INDEX_STALE_SECONDS': '2',
        'RAG_OUTBOX_DISPATCH_INTERVAL_SECONDS': '4',
        'RAG_REPAIR_INTERVAL_SECONDS': '6',
        'RAG_STORAGE_LOCAL_PATH': str(storage.root),
    })
    return env


def _worker_command(*, hostname: str) -> list[str]:
    return [
        sys.executable,
        '-m',
        'celery',
        '-A',
        'backend.app.task.celery',
        'worker',
        '--loglevel=info',
        '--pool=gevent',
        '--concurrency=1',
        '--prefetch-multiplier=1',
        '--without-gossip',
        '--without-mingle',
        f'--hostname={hostname}',
    ]


def _beat_command(*, pidfile: Path, schedule_path: Path) -> list[str]:
    return [
        sys.executable,
        '-m',
        'celery',
        '-A',
        'backend.app.task.celery',
        'beat',
        '--loglevel=info',
        f'--pidfile={pidfile}',
        '--scheduler=celery.beat:PersistentScheduler',
        f'--schedule={schedule_path}',
    ]


async def _create_knowledge_base(*, run_id: str) -> int:
    async with async_db_session.begin() as db:
        knowledge_base = KnowledgeBase(owner_id=9_900_001, name=f'celery-fault-{run_id}')
        db.add(knowledge_base)
        await db.flush()
        return knowledge_base.id


async def _create_document(*, knowledge_base_id: int, run_id: str, marker: str) -> tuple[int, str]:
    content = f'{marker}\n受控故障注入文档。'.encode()
    digest = hashlib.sha256(content).hexdigest()
    storage_key = f'fault-injection/{run_id}/{digest}.txt'
    storage.put(key=storage_key, content=content)
    async with async_db_session.begin() as db:
        document = Document(
            knowledge_base_id=knowledge_base_id,
            filename=f'{marker.lower()}.txt',
            file_type='txt',
            mime_type='text/plain',
            storage_key=storage_key,
            file_size=len(content),
            content_hash=digest,
        )
        db.add(document)
        await db.flush()
        await enqueue_document_index(db=db, document_id=document.id, index_version=document.index_version)
        return document.id, storage_key


async def _get_document_state(document_id: int) -> tuple[str, str | None, int, int] | None:
    async with async_db_session() as db:
        row = (
            await db.execute(
                select(Document.status, Document.error_message, Document.index_version, Document.chunk_count).where(
                    Document.id == document_id,
                    Document.deleted == 0,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        status, error_message, index_version, chunk_count = row
        status_value = status.value if isinstance(status, DocumentStatus) else str(status)
        return status_value, error_message, index_version, chunk_count


def _append_trace(trace: list[dict[str, Any]], state: tuple[str, str | None, int, int]) -> None:
    status, error_message, index_version, chunk_count = state
    if trace and trace[-1]['status'] == status and trace[-1]['error_message'] == error_message:
        return
    trace.append({
        'observed_at': timezone.now().isoformat(),
        'status': status,
        'error_message': error_message,
        'index_version': index_version,
        'chunk_count': chunk_count,
    })


async def _wait_for_document_status(
    *,
    document_id: int,
    expected_status: str,
    trace: list[dict[str, Any]],
    timeout: float,
) -> tuple[str, str | None, int, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = await _get_document_state(document_id)
        if state is not None:
            _append_trace(trace, state)
            if state[0] == expected_status:
                return state
        await asyncio.sleep(0.05)
    raise TimeoutError(f'文档 {document_id} 未在限定时间进入 {expected_status}')


async def _cleanup(*, knowledge_base_id: int | None, document_ids: list[int], storage_keys: list[str]) -> bool:
    async with async_db_session.begin() as db:
        if document_ids:
            await db.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))
            await db.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(document_ids)))
            await db.execute(delete(Document).where(Document.id.in_(document_ids)))
        if knowledge_base_id is not None:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id))
    for storage_key in storage_keys:
        storage.delete(key=storage_key)

    async with async_db_session() as db:
        document_count = 0
        knowledge_base_count = 0
        if document_ids:
            document_count = int(
                await db.scalar(select(func.count(Document.id)).where(Document.id.in_(document_ids))) or 0
            )
        if knowledge_base_id is not None:
            knowledge_base_count = int(
                await db.scalar(select(func.count(KnowledgeBase.id)).where(KnowledgeBase.id == knowledge_base_id)) or 0
            )
    objects_removed = all(not (storage.root / key).exists() for key in storage_keys)
    return document_count == 0 and knowledge_base_count == 0 and objects_removed


async def run_fault_injection() -> dict[str, Any]:
    if os.getenv('RAG_RUN_CELERY_FAULT_INJECTION') != '1':
        raise RuntimeError('必须显式设置 RAG_RUN_CELERY_FAULT_INJECTION=1')

    report: dict[str, Any] = {
        'started_at': timezone.now().isoformat(),
        'timeout_retry': {},
        'worker_interruption': {},
        'cleanup': {'completed': False},
    }
    run_id = uuid4().hex[:12]
    knowledge_base_id: int | None = None
    document_ids: list[int] = []
    storage_keys: list[str] = []
    processes: list[ManagedProcess] = []
    broker_client: Redis | None = None
    fault_server = FaultEmbeddingServer()
    server_thread = threading.Thread(target=fault_server.serve_forever, name='rag-fault-embedding', daemon=True)
    server_thread.start()

    try:
        broker_database, broker_client = await _reserve_isolated_redis_database()
        report['broker_database'] = broker_database
        env = _celery_environment(
            broker_database=broker_database,
            embedding_base_url=fault_server.base_url,
        )

        with tempfile.TemporaryDirectory(prefix='rag-celery-fault-') as temp_directory:
            temp_path = Path(temp_directory)
            worker = ManagedProcess.start(
                command=_worker_command(hostname=f'rag-fault-{run_id}@%h'),
                env=env,
                log_path=temp_path / 'worker-initial.log',
            )
            processes.append(worker)
            beat = ManagedProcess.start(
                command=_beat_command(
                    pidfile=temp_path / 'celerybeat.pid',
                    schedule_path=temp_path / 'celerybeat-schedule',
                ),
                env=env,
                log_path=temp_path / 'beat.log',
            )
            processes.append(beat)
            await worker.wait_for_log(' ready.')
            await beat.wait_for_log('beat: Starting', 'celery beat v')

            knowledge_base_id = await _create_knowledge_base(run_id=run_id)

            timeout_document_id, timeout_storage_key = await _create_document(
                knowledge_base_id=knowledge_base_id,
                run_id=run_id,
                marker=TIMEOUT_MARKER,
            )
            document_ids.append(timeout_document_id)
            storage_keys.append(timeout_storage_key)
            timeout_trace: list[dict[str, Any]] = []
            timeout_state = await _wait_for_document_status(
                document_id=timeout_document_id,
                expected_status=DocumentStatus.FAILED.value,
                trace=timeout_trace,
                timeout=45,
            )
            status_sequence = [item['status'] for item in timeout_trace]
            report['timeout_retry'] = {
                'document_id': timeout_document_id,
                'final_status': timeout_state[0],
                'retry_observed': status_sequence.count(DocumentStatus.PROCESSING.value) >= 2
                and DocumentStatus.PENDING.value in status_sequence[1:],
                'trace': timeout_trace,
            }

            interruption_document_id, interruption_storage_key = await _create_document(
                knowledge_base_id=knowledge_base_id,
                run_id=run_id,
                marker=INTERRUPTION_MARKER,
            )
            document_ids.append(interruption_document_id)
            storage_keys.append(interruption_storage_key)
            interruption_trace: list[dict[str, Any]] = []
            await _wait_for_document_status(
                document_id=interruption_document_id,
                expected_status=DocumentStatus.PROCESSING.value,
                trace=interruption_trace,
                timeout=30,
            )
            interruption_started = await asyncio.to_thread(fault_server.interruption_started.wait, 10)
            if not interruption_started:
                raise TimeoutError('受控 Embedding 端点未观察到 Worker 中断场景请求')

            worker.stop(force=True)
            processes.remove(worker)
            replacement_worker = ManagedProcess.start(
                command=_worker_command(hostname=f'rag-recovery-{run_id}@%h'),
                env=env,
                log_path=temp_path / 'worker-recovery.log',
            )
            processes.append(replacement_worker)
            await replacement_worker.wait_for_log(' ready.')
            ready_state = await _wait_for_document_status(
                document_id=interruption_document_id,
                expected_status=DocumentStatus.READY.value,
                trace=interruption_trace,
                timeout=45,
            )
            recovery_log = replacement_worker.read_log()
            beat_recovery_observed = 'requeued_indexes=1' in recovery_log
            async with async_db_session() as db:
                active_chunks = int(
                    await db.scalar(
                        select(func.count(Chunk.id)).where(
                            Chunk.document_id == interruption_document_id,
                            Chunk.index_version == ready_state[2],
                            Chunk.deleted == 0,
                        )
                    )
                    or 0
                )
            report['worker_interruption'] = {
                'document_id': interruption_document_id,
                'final_status': ready_state[0],
                'beat_recovery_observed': beat_recovery_observed,
                'chunk_count': active_chunks,
                'trace': interruption_trace,
            }

            if report['timeout_retry']['retry_observed'] is not True:
                raise AssertionError('未观察到真实 Worker 的超时重试状态轨迹')
            if not beat_recovery_observed:
                raise AssertionError('未在真实 Worker 日志中观察到 Beat 修复任务重新投递索引')
            if active_chunks != 1:
                raise AssertionError(f'Worker 中断恢复后有效切片数量异常: {active_chunks}')
    except Exception as exc:
        diagnostics = _process_diagnostics(processes)
        broker_diagnostics = await _broker_diagnostics(broker_client) if broker_client is not None else {}
        raise RuntimeError(
            f'{exc}; broker_diagnostics={json.dumps(broker_diagnostics)}; '
            f'celery_diagnostics={json.dumps(diagnostics, ensure_ascii=False)}'
        ) from exc
    finally:
        for process in reversed(processes):
            process.stop()
        fault_server.shutdown()
        fault_server.server_close()
        server_thread.join(timeout=2)
        cleanup_completed = await _cleanup(
            knowledge_base_id=knowledge_base_id,
            document_ids=document_ids,
            storage_keys=storage_keys,
        )
        if broker_client is not None:
            await broker_client.flushdb()
            broker_empty = await broker_client.dbsize() == 0
            await broker_client.aclose()
        else:
            broker_empty = True
        report['cleanup'] = {'completed': cleanup_completed and broker_empty}
        report['finished_at'] = timezone.now().isoformat()

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='运行真实 Celery Worker/Beat RAG 故障注入验收')
    parser.add_argument('--output', type=Path, help='可选的脱敏 JSON 报告输出路径')
    args = parser.parse_args()
    report = asyncio.run(run_fault_injection())
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f'{serialized}\n', encoding='utf-8')
    print(serialized)


if __name__ == '__main__':
    main()
