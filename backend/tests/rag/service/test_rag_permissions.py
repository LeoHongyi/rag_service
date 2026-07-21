import asyncio

from typing import Any

from sqlalchemy.dialects import postgresql

from backend.app.rag.crud.crud_rag import knowledge_base_dao


class Database:
    def __init__(self) -> None:
        self.statement = None

    async def scalar(self, statement: Any) -> None:
        await asyncio.sleep(0)
        self.statement = statement


def _compiled_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))


def test_private_knowledge_base_read_scope_allows_owner_or_public() -> None:
    db = Database()
    asyncio.run(knowledge_base_dao.get_authorized(db, pk=9, user_id=5, is_admin=False))
    sql = _compiled_sql(db.statement)
    assert 'rag_knowledge_base.owner_id = 5 OR rag_knowledge_base.is_public' in sql


def test_private_knowledge_base_write_scope_excludes_public_read_permission() -> None:
    db = Database()
    asyncio.run(knowledge_base_dao.get_authorized(db, pk=9, user_id=5, is_admin=False, write=True))
    sql = _compiled_sql(db.statement)
    assert 'rag_knowledge_base.owner_id = 5' in sql
    assert ' OR rag_knowledge_base.is_public' not in sql
