from datetime import datetime

from pydantic import ConfigDict, Field

from backend.app.rag.enums import DocumentStatus
from backend.common.schema import SchemaBase


class GetDocumentDetail(SchemaBase):
    """文档详情"""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description='文档 ID')
    knowledge_base_id: int = Field(description='知识库 ID')
    filename: str = Field(description='文件名')
    file_type: str = Field(description='文件类型')
    file_size: int = Field(description='文件大小')
    status: DocumentStatus = Field(description='索引状态')
    error_message: str | None = Field(None, description='错误摘要')
    chunk_count: int = Field(description='切片数量')
    index_version: int = Field(description='索引版本')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')


class GetChunkDetail(SchemaBase):
    """切片详情"""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description='切片 ID')
    document_id: int = Field(description='文档 ID')
    chunk_index: int = Field(description='切片序号')
    content: str = Field(description='切片内容')
    heading_path: list[str] = Field(description='标题路径')
    location: dict[str, int] = Field(description='原文位置')
    token_count: int = Field(description='Token 估算')
