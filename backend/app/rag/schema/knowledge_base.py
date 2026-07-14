from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase


class KnowledgeBaseSchemaBase(SchemaBase):
    """知识库基础模型"""

    name: str = Field(min_length=1, max_length=128, description='知识库名称')
    description: str | None = Field(None, max_length=512, description='知识库描述')


class CreateKnowledgeBaseParam(KnowledgeBaseSchemaBase):
    """创建知识库参数"""

    is_public: bool = Field(False, description='是否公开')


class UpdateKnowledgeBaseParam(SchemaBase):
    """更新知识库参数"""

    name: str | None = Field(None, min_length=1, max_length=128, description='知识库名称')
    description: str | None = Field(None, max_length=512, description='知识库描述')
    is_public: bool | None = Field(None, description='是否公开')


class GetKnowledgeBaseDetail(KnowledgeBaseSchemaBase):
    """知识库详情"""

    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description='知识库 ID')
    owner_id: int = Field(description='所有者 ID')
    is_public: bool = Field(description='是否公开')
    document_count: int = Field(description='文档数')
    chunk_count: int = Field(description='切片数')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')
