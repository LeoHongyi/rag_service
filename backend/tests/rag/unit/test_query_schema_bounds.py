"""检索/问答请求体的边界约束回归测试。

`knowledge_base_ids` 是查询热路径上唯一没有上限的输入：它会直接进入
`KnowledgeBase.id.in_(...)` 与 `Chunk.knowledge_base_id.in_(...)`，
不设上限意味着单个已登录用户可以用一次请求构造超大 SQL IN 子句。
"""

import pytest

from pydantic import ValidationError

from backend.app.rag.schema.query import AnswerParam, RetrieveParam


def test_retrieve_rejects_more_than_fifty_knowledge_bases() -> None:
    with pytest.raises(ValidationError):
        RetrieveParam(question='问题', knowledge_base_ids=list(range(51)))


def test_retrieve_accepts_the_upper_bound() -> None:
    obj = RetrieveParam(question='问题', knowledge_base_ids=list(range(50)))

    assert len(obj.knowledge_base_ids) == 50


def test_retrieve_still_requires_at_least_one_knowledge_base() -> None:
    with pytest.raises(ValidationError):
        RetrieveParam(question='问题', knowledge_base_ids=[])


def test_answer_inherits_the_same_bound() -> None:
    """AnswerParam 继承自 RetrieveParam，/answer 与 /retrieve 必须同样受限。"""
    with pytest.raises(ValidationError):
        AnswerParam(question='问题', knowledge_base_ids=list(range(51)))
