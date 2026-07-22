import json

import pytest

from backend.app.rag.evaluation.public_sources import extract_aliyun_document


def _page(content: str) -> str:
    state = {'docDetailData': {'storeData': {'data': {'docTitle': '知识检索', 'content': content}}}}
    return (
        '<html><head><script>window.pageStartTime = Date.now()</script></head>'
        f'<script>window.__ICE_PAGE_PROPS__={json.dumps(state, ensure_ascii=False)};</script>'
        '<body><nav>控制台 导航</nav></body></html>'
    )


def test_extract_aliyun_document_keeps_structured_body_only() -> None:
    text = extract_aliyun_document(
        _page(
            '<main><h2>检索流程</h2><p>依次执行以下步骤。</p>'
            '<ol><li><p>Query 改写</p></li><li><p>向量检索 + 关键词检索</p></li><li>Rerank</li></ol>'
            '<table><tr><th><p>模型</p></th><th>用途</th></tr>'
            '<tr><td><p>qwen3-rerank</p></td><td>精排</td></tr></table></main>'
        ),
        min_chars=20,
    )

    assert text.startswith('# 知识检索\n\n## 检索流程')
    assert '- Query 改写' in text
    assert '模型 | 用途' in text
    assert 'qwen3-rerank | 精排' in text
    assert 'window.pageStartTime' not in text
    assert '__ICE_PAGE_PROPS__' not in text
    assert '控制台 导航' not in text


@pytest.mark.parametrize(
    'page',
    [
        '<html>没有页面状态</html>',
        _page(''),
        _page('<p>太短</p>'),
        _page('<p>正文包含 window.pageStartTime 噪声标记，必须拒绝。</p>'),
    ],
)
def test_extract_aliyun_document_rejects_unusable_body(page: str) -> None:
    with pytest.raises(ValueError):
        extract_aliyun_document(page, min_chars=10)
