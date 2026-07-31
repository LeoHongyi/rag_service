from typing import Literal

from pydantic import Field

from backend.common.schema import SchemaBase


class RetrieveParam(SchemaBase):
    """检索参数"""

    question: str = Field(min_length=1, max_length=4000, description='检索问题')
    # 上限防止单次请求构造超大 SQL IN 子句；50 远超正常跨库检索需求
    knowledge_base_ids: list[int] = Field(min_length=1, max_length=50, description='知识库 ID 列表')
    top_k: int = Field(5, ge=1, le=20, description='返回数量')


class GetSourceDetail(SchemaBase):
    """来源详情"""

    knowledge_base_id: int = Field(description='知识库 ID')
    document_id: int = Field(description='文档 ID')
    document_name: str = Field(description='文档名称')
    chunk_id: int = Field(description='切片 ID')
    chunk_index: int = Field(description='切片序号')
    content: str = Field(description='引用内容')
    score: float = Field(description='相关度')
    rerank_score: float | None = Field(None, description='重排分数；未启用或降级时为空')
    citation: str = Field(description='引用标识')


class AnswerParam(RetrieveParam):
    """问答参数"""

    mode: Literal['basic', 'agentic', 'auto'] = Field('auto', description='问答模式')


class GetAnswerDetail(SchemaBase):
    """问答结果"""

    answer: str = Field(description='回答内容')
    sources: list[GetSourceDetail] = Field(description='引用来源')
    requested_mode: str = Field(description='请求模式')
    effective_mode: str = Field(description='实际模式')
    status: str = Field(description='执行状态')
    retrieval_rounds: int = Field(description='检索轮数')
    stop_reason: str = Field(description='停止原因')
    trace_id: str | None = Field(None, description='追踪 ID')
