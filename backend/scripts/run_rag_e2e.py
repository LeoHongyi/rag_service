"""真实端到端验证运行器：API → Outbox → Celery → DashScope → 检索 → 问答。

与单元测试不同，本运行器不使用任何 fake：它启动真实的 uvicorn API 服务、
Celery Worker 与 Beat，通过 HTTP 走完「登录 → 建库 → 上传 → 等待 READY →
混合检索 → 问答 → 异步删除」的完整用户路径，Embedding 与 Chat 均为真实
供应商调用（``RAG_ALLOW_LOCAL_MODEL_FALLBACK=false`` 强制关闭本地回退，
任何回退路径都会以显式错误暴露而不是伪装成功）。

前置条件（不满足时应直接失败，而不是伪造证据）：

- ``docker-compose.infra.yml`` 的 PostgreSQL(pgvector) 与 Redis 已就绪；
- 数据库已初始化（表结构 + ``init_test_data.sql`` 种子用户 admin）；
- ``backend/.env`` 配置了真实可用的 ``RAG_EMBEDDING_API_KEY`` / ``RAG_CHAT_API_KEY``。

安全性：临时知识库与文档在结束时删除（含异步删除链路验证）；Broker 使用
8-15 号中的空闲 Redis 数据库隔离，结束后清空；不打印密钥与文档正文。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from redis.asyncio import Redis

from backend.core.conf import settings

SAMPLE_DOC_NAME = 'rag-e2e-sample.md'
SAMPLE_DOC_CONTENT = """# 织问检索服务运维手册（E2E 测试样例，虚构数据）

## 服务端口

织问检索服务的 HTTP 端口是 18443，管理端口是 19001。健康检查路径是 `/healthz`。

## 数据保留策略

查询日志保留 90 天。向量索引快照每 6 小时生成一次，保留最近 14 份。

## 故障处置

当嵌入服务连续 5 次超时时，应先检查 DashScope 配额，再执行
`systemctl restart zhiwen-embedding-proxy` 重启代理进程。

## 容量上限

单个知识库最多容纳 10 万切片；单份文档大小上限是 20 MB。
"""

QUESTION_PORT = '织问检索服务的 HTTP 端口是多少？'
QUESTION_SNAPSHOT = '向量索引快照多久生成一次，保留多少份？'
QUESTION_OUT_OF_SCOPE = '珠穆朗玛峰有多高？'


@dataclass
class ManagedProcess:
    """带日志文件与进程组清理的子进程。"""

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

    async def wait_for_log(self, *patterns: str, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'进程 {self.log_path.name} 提前退出，退出码 {self.process.returncode}')
            if any(pattern in self.read_log() for pattern in patterns):
                return
            await asyncio.sleep(0.2)
        raise TimeoutError(f'等待进程 {self.log_path.name} 就绪超时')

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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


async def _reserve_isolated_redis_database() -> tuple[int, Redis]:
    """从 8-15 号中挑选空的 Redis 数据库作为隔离 Broker。"""
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
    raise RuntimeError('Redis 8-15 号数据库均非空，无法安全隔离 E2E Broker')


def _service_environment(*, broker_database: int) -> dict[str, str]:
    env = os.environ.copy()
    # CELERY_BROKER 同时是 Celery CLI 的兼容变量，传给子进程会被解析成 AMQP 主机名
    env.pop('CELERY_BROKER', None)
    env.update({
        'ENVIRONMENT': 'dev',
        'CELERY_BROKER_REDIS_DATABASE': str(broker_database),
        # 关闭本地回退：任何凭据/供应商故障都必须显式失败，不能伪装成真实向量或回答
        'RAG_ALLOW_LOCAL_MODEL_FALLBACK': 'false',
        'RAG_OUTBOX_DISPATCH_INTERVAL_SECONDS': '2',
        'RAG_REPAIR_INTERVAL_SECONDS': '30',
    })
    return env


def _api_command(*, port: int) -> list[str]:
    return [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', str(port)]


def _worker_command() -> list[str]:
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
        '--hostname=rag-e2e@%h',
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


class E2EClient:
    """带认证与 {code,msg,data} 信封解析的最小 HTTP 客户端。"""

    def __init__(self, *, base_url: str, username: str, password: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=120)
        self._username = username
        self._password = password
        self.transient_retries_used = 0

    def login(self) -> None:
        # swagger 登录端点以 HTTPBasicCredentials 作为查询依赖（FBA 上游形态），凭据走 query 而非 Basic 头
        response = self._client.post(
            '/api/v1/auth/login/swagger', params={'username': self._username, 'password': self._password}
        )
        response.raise_for_status()
        token = response.json()['access_token']
        self._client.headers['Authorization'] = f'Bearer {token}'

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return self._client.request(method, url, **kwargs)

    def data(self, method: str, url: str, *, transient_retries: int = 0, **kwargs: Any) -> Any:
        """请求并解析 {code,msg,data} 信封。

        transient_retries 只应用于幂等只读请求（检索/问答）：查询路径的供应商调用
        没有服务端重试，宿主机到 DashScope 的瞬时 TLS 连接失败会以单次 500 暴露；
        这里的有限重试模拟真实客户端行为，重试次数记入 transient_retries_used，
        不掩盖失败率。上传与删除等有副作用的请求不得传入该参数。
        """
        attempt = 0
        while True:
            response = self.request(method, url, **kwargs)
            if response.status_code >= 500 and attempt < transient_retries:
                attempt += 1
                self.transient_retries_used += 1
                time.sleep(2 * attempt)
                continue
            response.raise_for_status()
            body = response.json()
            if body.get('code') != 200:
                raise RuntimeError(f'{method} {url} 业务失败：code={body.get("code")} msg={body.get("msg")}')
            return body.get('data')

    def close(self) -> None:
        self._client.close()


async def _wait_document_status(
    client: E2EClient, *, kb_id: int, doc_id: int, target: set[str], timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = client.data('GET', f'/api/v1/rag/knowledge-bases/{kb_id}/documents/{doc_id}')
        if detail['status'] in target:
            return detail
        await asyncio.sleep(2)
    raise TimeoutError(f'等待文档状态 {target} 超时，当前 {detail.get("status")}')


async def _wait_document_gone(client: E2EClient, *, kb_id: int, doc_id: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.request('GET', f'/api/v1/rag/knowledge-bases/{kb_id}/documents/{doc_id}')
        if response.status_code == 404:
            return True
        if response.status_code == 200 and response.json().get('code') == 404:
            return True
        await asyncio.sleep(2)
    return False


async def run_e2e(*, username: str = 'admin', password: str = '123456') -> dict[str, Any]:
    """执行完整真实链路，返回可断言的报告字典。"""
    report: dict[str, Any] = {'observations': {}}
    port = _free_port()
    broker_database, broker_client = await _reserve_isolated_redis_database()
    report['api_port'] = port
    report['broker_database'] = broker_database

    env = _service_environment(broker_database=broker_database)
    processes: list[ManagedProcess] = []
    client: E2EClient | None = None
    kb_id: int | None = None
    doc_id: int | None = None

    with tempfile.TemporaryDirectory(prefix='rag-e2e-') as temp_dir:
        temp_path = Path(temp_dir)
        try:
            api = ManagedProcess.start(command=_api_command(port=port), env=env, log_path=temp_path / 'api.log')
            processes.append(api)
            worker = ManagedProcess.start(command=_worker_command(), env=env, log_path=temp_path / 'worker.log')
            processes.append(worker)
            beat = ManagedProcess.start(
                command=_beat_command(pidfile=temp_path / 'beat.pid', schedule_path=temp_path / 'beat-schedule'),
                env=env,
                log_path=temp_path / 'beat.log',
            )
            processes.append(beat)
            await api.wait_for_log('Application startup complete', timeout=60)
            await worker.wait_for_log(' ready.', timeout=60)
            await beat.wait_for_log('beat: Starting', timeout=60)

            client = E2EClient(base_url=f'http://127.0.0.1:{port}', username=username, password=password)
            client.login()
            report['login'] = True

            kb = client.data(
                'POST',
                '/api/v1/rag/knowledge-bases',
                json={'name': f'e2e-real-{int(time.time())}', 'description': '真实链路 E2E 验证', 'is_public': False},
            )
            kb_id = int(kb['id'])
            report['knowledge_base_id'] = kb_id

            doc = client.data(
                'POST',
                f'/api/v1/rag/knowledge-bases/{kb_id}/documents',
                files={'file': (SAMPLE_DOC_NAME, SAMPLE_DOC_CONTENT.encode(), 'text/markdown')},
            )
            doc_id = int(doc['id'])
            report['document_id'] = doc_id
            report['upload_status'] = doc['status']

            detail = await _wait_document_status(
                client, kb_id=kb_id, doc_id=doc_id, target={'READY', 'FAILED'}, timeout=180
            )
            report['final_index_status'] = detail['status']
            report['error_message'] = detail.get('error_message')
            report['chunk_count'] = detail.get('chunk_count', 0)
            if detail['status'] != 'READY':
                return report

            sources = client.data(
                'POST',
                '/api/v1/rag/retrieve',
                transient_retries=2,
                json={'question': QUESTION_PORT, 'knowledge_base_ids': [kb_id], 'top_k': 5},
            )
            report['retrieve_source_count'] = len(sources)
            report['retrieve_hit'] = any('18443' in source['content'] for source in sources)
            report['retrieve_top_score'] = sources[0]['score'] if sources else None

            answer = client.data(
                'POST',
                '/api/v1/rag/answer',
                transient_retries=2,
                json={'question': QUESTION_PORT, 'knowledge_base_ids': [kb_id], 'top_k': 5, 'mode': 'basic'},
            )
            report['answer_status'] = answer['status']
            report['answer_cites_sources'] = bool(answer['sources'])
            report['answer_contains_fact'] = '18443' in answer['answer']
            report['observations']['answer_preview'] = answer['answer'][:200]

            answer_snapshot = client.data(
                'POST',
                '/api/v1/rag/answer',
                transient_retries=2,
                json={'question': QUESTION_SNAPSHOT, 'knowledge_base_ids': [kb_id], 'top_k': 5, 'mode': 'basic'},
            )
            report['answer2_status'] = answer_snapshot['status']
            report['answer2_contains_facts'] = '6' in answer_snapshot['answer'] and '14' in answer_snapshot['answer']
            report['observations']['answer2_preview'] = answer_snapshot['answer'][:200]

            # 已知缺陷观察项（无相关度下限，见 session-handoff）：只记录，不断言
            out_of_scope = client.data(
                'POST',
                '/api/v1/rag/answer',
                transient_retries=2,
                json={'question': QUESTION_OUT_OF_SCOPE, 'knowledge_base_ids': [kb_id], 'top_k': 5, 'mode': 'basic'},
            )
            report['observations']['out_of_scope_status'] = out_of_scope['status']
            report['observations']['out_of_scope_preview'] = out_of_scope['answer'][:120]

            over_cap = client.request(
                'POST',
                '/api/v1/rag/retrieve',
                json={'question': 'x', 'knowledge_base_ids': list(range(1, 52)), 'top_k': 5},
            )
            report['kb_ids_cap_rejected'] = over_cap.status_code == 422

            delete_response = client.request('DELETE', f'/api/v1/rag/knowledge-bases/{kb_id}/documents/{doc_id}')
            report['delete_accepted'] = delete_response.status_code == 200
            report['async_delete_completed'] = await _wait_document_gone(client, kb_id=kb_id, doc_id=doc_id, timeout=90)
            doc_id = None

            kb_delete = client.request('DELETE', f'/api/v1/rag/knowledge-bases/{kb_id}')
            report['kb_delete_accepted'] = kb_delete.status_code == 200
            kb_id = None
            report['transient_retries_used'] = client.transient_retries_used
            return report
        finally:
            if client is not None and kb_id is not None:
                try:
                    if doc_id is not None:
                        client.request('DELETE', f'/api/v1/rag/knowledge-bases/{kb_id}/documents/{doc_id}')
                        await _wait_document_gone(client, kb_id=kb_id, doc_id=doc_id, timeout=60)
                    client.request('DELETE', f'/api/v1/rag/knowledge-bases/{kb_id}')
                except (httpx.HTTPError, RuntimeError):
                    pass
            if client is not None:
                client.close()
            report['process_logs'] = {managed.log_path.name: managed.read_log()[-2000:] for managed in processes}
            for managed in reversed(processes):
                managed.stop()
            await broker_client.flushdb()
            await broker_client.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default='admin')
    parser.add_argument('--password', default='123456')
    args = parser.parse_args()
    report = asyncio.run(run_e2e(username=args.username, password=args.password))
    print(json.dumps({k: v for k, v in report.items() if k != 'process_logs'}, ensure_ascii=False, indent=2))
    ok = (
        report.get('final_index_status') == 'READY'
        and report.get('retrieve_hit') is True
        and report.get('answer_status') == 'answered'
        and report.get('answer_contains_fact') is True
        and report.get('kb_ids_cap_rejected') is True
        and report.get('async_delete_completed') is True
    )
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
