import asyncio

import pytest

from backend.app.rag.service.document_service import embed_texts_in_batches


def test_embedding_texts_are_sent_in_configured_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    # 测试替身必须保持与生产适配器一致的可等待接口。
    async def fake_embed(texts: list[str]) -> list[list[float]]:  # noqa: RUF029
        calls.append(texts)
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr('backend.app.rag.service.document_service.embedding_provider.embed', fake_embed)

    vectors = asyncio.run(embed_texts_in_batches(texts=['a', 'b', 'c', 'd', 'e'], batch_size=2))

    assert calls == [['a', 'b'], ['c', 'd'], ['e']]
    assert vectors == [[1.0], [1.0], [1.0], [1.0], [1.0]]
