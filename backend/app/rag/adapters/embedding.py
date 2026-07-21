import hashlib
import math

import httpx

from backend.core.conf import settings


class EmbeddingProvider:
    """Embedding 服务适配器"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """生成文本向量"""
        if not settings.RAG_EMBEDDING_BASE_URL or not settings.RAG_EMBEDDING_API_KEY:
            return [self._local_embedding(text) for text in texts]
        payload = {
            'model': settings.RAG_EMBEDDING_MODEL,
            'input': texts,
            'dimensions': settings.RAG_EMBEDDING_DIMENSIONS,
            'encoding_format': 'float',
        }
        headers = {'Authorization': f'Bearer {settings.RAG_EMBEDDING_API_KEY}'}
        async with httpx.AsyncClient(timeout=settings.RAG_EMBEDDING_TIMEOUT_SECONDS) as client:
            response = await client.post(f'{settings.RAG_EMBEDDING_BASE_URL}/embeddings', json=payload, headers=headers)
            response.raise_for_status()
        data = sorted(response.json()['data'], key=lambda item: item.get('index', 0))
        vectors = [item['embedding'] for item in data]
        if len(vectors) != len(texts) or any(len(item) != settings.RAG_EMBEDDING_DIMENSIONS for item in vectors):
            raise ValueError('Embedding 返回向量数量或维度不匹配')
        return vectors

    @staticmethod
    def _local_embedding(text: str) -> list[float]:
        """无模型配置时的确定性开发向量"""
        values = [0.0] * settings.RAG_EMBEDDING_DIMENSIONS
        for index, byte in enumerate(hashlib.sha256(text.encode()).digest()):
            values[index % len(values)] += (byte - 127.5) / 127.5
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


embedding_provider = EmbeddingProvider()
