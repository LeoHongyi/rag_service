"""从固定数据库调用真实 RAG Service 并写入离线评测结果。"""

import argparse
import asyncio

from pathlib import Path

from backend.app.rag.evaluation.dataset import load_dataset
from backend.app.rag.evaluation.runner import write_results
from backend.app.rag.evaluation.service_executor import run_service_evaluation
from backend.database.db import async_db_session


async def run(args: argparse.Namespace) -> None:
    """在只读评测事务中运行一次固定索引配置的服务评测。"""
    cases = load_dataset(args.dataset, require_approved=args.require_approved)
    async with async_db_session() as db:
        results = await run_service_evaluation(
            db=db,
            cases=cases,
            user_id=args.user_id,
            is_admin=args.is_admin,
            index_profile_hash=args.index_profile_hash,
            answer_mode=args.answer_mode,
        )
    write_results(results=results, output_path=args.output)


def main() -> None:
    """解析真实服务评测命令参数。"""
    parser = argparse.ArgumentParser(description='运行真实 RAG Service 离线评测')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--index-profile-hash', required=True)
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--is-admin', action='store_true')
    parser.add_argument('--answer-mode', choices=['basic', 'agentic', 'auto'])
    parser.add_argument('--require-approved', action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
