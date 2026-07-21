"""对指定文档的 Embedding 批次做不输出正文的诊断。"""

import argparse
import asyncio

from pathlib import Path

import httpx

from backend.app.rag.adapters.embedding import embedding_provider
from backend.app.rag.chunking import contextualize_chunk, split_text
from backend.app.rag.parsers.text import parse_document
from backend.core.conf import settings


async def diagnose_file(path: Path) -> None:
    """输出每个批次的安全元数据及供应商结果。"""
    data = await asyncio.to_thread(path.read_bytes)
    text = parse_document(filename=path.name, data=data)
    pieces = split_text(text, chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)
    contextualized = [contextualize_chunk(filename=path.name, heading_path=[], content=piece) for piece in pieces]
    for start in range(0, len(contextualized), settings.RAG_EMBEDDING_BATCH_SIZE):
        batch = contextualized[start : start + settings.RAG_EMBEDDING_BATCH_SIZE]
        details = {
            'file': path.name,
            'start': start,
            'count': len(batch),
            'max_char_count': max(map(len, batch)),
        }
        try:
            await embedding_provider.embed(batch)
            details['result'] = 'ok'
        except httpx.HTTPStatusError as exc:
            details['result'] = f'http_{exc.response.status_code}'
            try:
                details['provider_code'] = exc.response.json().get('code', 'unknown')
            except ValueError:
                details['provider_code'] = 'non_json_error'
        print(details)


def main() -> None:
    """解析指定的 PDF 文件路径。"""
    parser = argparse.ArgumentParser(description='诊断 Embedding 批次，不输出正文')
    parser.add_argument('--file', action='append', required=True, type=Path)
    args = parser.parse_args()
    for path in args.file:
        asyncio.run(diagnose_file(path))


if __name__ == '__main__':
    main()
