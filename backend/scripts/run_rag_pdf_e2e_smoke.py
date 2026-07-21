"""在本地环境验证 PDF 上传、索引、检索和问答闭环。"""

import argparse
import asyncio
import json
import secrets
import time

from pathlib import Path

import httpx

from backend.app.admin.model import User
from backend.app.admin.utils.password_security import get_hash_password
from backend.database.db import async_db_session


async def create_temporary_user(*, username: str, password: str) -> int:
    """创建没有管理权限、仅能访问自身测试知识库的临时用户。"""
    async with async_db_session.begin() as db:
        user = User(
            username=username,
            nickname='RAG PDF E2E 临时用户',
            password=get_hash_password(password, None),
            salt=None,
            is_multi_login=True,
        )
        db.add(user)
        await db.flush()
        return user.id


async def delete_temporary_user(*, user_id: int) -> None:
    """物理删除不含关联业务数据的临时验证用户。"""
    async with async_db_session.begin() as db:
        user = await db.get(User, user_id)
        if user:
            await db.delete(user)


async def wait_for_documents(
    *, client: httpx.AsyncClient, headers: dict[str, str], knowledge_base_id: int, document_ids: list[int]
) -> dict[int, str]:
    """等待全部异步索引任务进入终态。"""
    deadline = time.monotonic() + 180
    statuses: dict[int, str] = {}
    while time.monotonic() < deadline:
        for document_id in document_ids:
            response = await client.get(
                f'/api/v1/rag/knowledge-bases/{knowledge_base_id}/documents/{document_id}', headers=headers
            )
            response.raise_for_status()
            statuses[document_id] = response.json()['data']['status']
        if all(status in {'READY', 'FAILED'} for status in statuses.values()):
            return statuses
        await asyncio.sleep(2)
    raise TimeoutError('PDF 索引任务未在 180 秒内进入终态')


async def run(*, api_base_url: str, files: list[Path]) -> dict[str, object]:
    """执行隔离的端到端冒烟测试并始终清理临时账户与知识库。"""
    if any(path.suffix.lower() != '.pdf' for path in files):
        raise ValueError('只允许传入 PDF 文件')
    if any(not path.is_file() for path in files):
        raise ValueError('存在无法读取的 PDF 文件')

    suffix = secrets.token_hex(6)
    username = f'rag_pdf_e2e_{suffix}'
    password = f'Rag{secrets.token_urlsafe(18)}9'
    user_id = await create_temporary_user(username=username, password=password)
    knowledge_base_id: int | None = None
    try:
        async with httpx.AsyncClient(base_url=api_base_url, timeout=30) as client:
            login = await client.post('/api/v1/auth/login/swagger', params={'username': username, 'password': password})
            login.raise_for_status()
            token = login.json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}
            knowledge_base = await client.post(
                '/api/v1/rag/knowledge-bases',
                headers=headers,
                json={'name': f'PDF E2E 临时知识库 {suffix}', 'description': '自动化 PDF 端到端验证'},
            )
            knowledge_base.raise_for_status()
            knowledge_base_id = int(knowledge_base.json()['data']['id'])

            document_ids: list[int] = []
            for path in files:
                upload = await client.post(
                    f'/api/v1/rag/knowledge-bases/{knowledge_base_id}/documents',
                    headers=headers,
                    files={'file': (path.name, path.read_bytes(), 'application/pdf')},
                )
                upload.raise_for_status()
                document_ids.append(int(upload.json()['data']['id']))

            statuses = await wait_for_documents(
                client=client,
                headers=headers,
                knowledge_base_id=knowledge_base_id,
                document_ids=document_ids,
            )
            if any(status != 'READY' for status in statuses.values()):
                raise RuntimeError('存在 PDF 索引失败')

            retrieval = await client.post(
                '/api/v1/rag/retrieve',
                headers=headers,
                json={
                    'question': '简历中有哪些大模型、NLP 或算法工程相关的技能与项目经历？',
                    'knowledge_base_ids': [knowledge_base_id],
                    'top_k': 5,
                },
            )
            retrieval.raise_for_status()
            source_count = len(retrieval.json()['data'])
            answer = await client.post(
                '/api/v1/rag/answer',
                headers=headers,
                json={
                    'question': '简历中有哪些大模型、NLP 或算法工程相关的技能与项目经历？',
                    'knowledge_base_ids': [knowledge_base_id],
                    'top_k': 5,
                    'mode': 'basic',
                },
            )
            answer.raise_for_status()
            answer_data = answer.json()['data']
            return {
                'uploaded_pdf_count': len(files),
                'ready_pdf_count': sum(status == 'READY' for status in statuses.values()),
                'retrieval_source_count': source_count,
                'answer_status': answer_data['status'],
                'answer_source_count': len(answer_data['sources']),
            }
    finally:
        if knowledge_base_id is not None:
            async with httpx.AsyncClient(base_url=api_base_url, timeout=30) as client:
                login = await client.post(
                    '/api/v1/auth/login/swagger', params={'username': username, 'password': password}
                )
                if login.is_success:
                    await client.delete(
                        f'/api/v1/rag/knowledge-bases/{knowledge_base_id}',
                        headers={'Authorization': f'Bearer {login.json()["access_token"]}'},
                    )
        await delete_temporary_user(user_id=user_id)


def main() -> None:
    """解析命令行参数并输出不包含私有正文的摘要。"""
    parser = argparse.ArgumentParser(description='运行本地 RAG PDF 端到端冒烟测试')
    parser.add_argument('--api-base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--file', action='append', required=True, type=Path)
    result = asyncio.run(run(api_base_url=parser.parse_args().api_base_url, files=parser.parse_args().file))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
