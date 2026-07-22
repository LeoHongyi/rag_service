import asyncio

import httpx
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


def test_embedding_batch_http_400_is_split_without_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def fake_embed(texts: list[str]) -> list[list[float]]:  # noqa: RUF029
        calls.append(texts)
        if len(texts) > 1:
            request = httpx.Request('POST', 'https://embedding.example/embeddings')
            raise httpx.HTTPStatusError('bad request', request=request, response=httpx.Response(400, request=request))
        return [[float(len(texts[0]))]]

    monkeypatch.setattr('backend.app.rag.service.document_service.embedding_provider.embed', fake_embed)

    vectors = asyncio.run(embed_texts_in_batches(texts=['甲', '乙', '丙', '丁'], batch_size=4))

    assert vectors == [[1.0], [1.0], [1.0], [1.0]]
    assert calls == [['甲', '乙', '丙', '丁'], ['甲', '乙'], ['甲'], ['乙'], ['丙', '丁'], ['丙'], ['丁']]


def test_embedding_single_text_http_400_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed(texts: list[str]) -> list[list[float]]:  # noqa: RUF029
        request = httpx.Request('POST', 'https://embedding.example/embeddings')
        raise httpx.HTTPStatusError('bad request', request=request, response=httpx.Response(400, request=request))

    monkeypatch.setattr('backend.app.rag.service.document_service.embedding_provider.embed', fake_embed)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(embed_texts_in_batches(texts=['无法接受的文本'], batch_size=10))
