from typing import TypedDict


class AgentState(TypedDict):
    """有界 Agentic RAG 状态"""

    question: str
    retrieval_rounds: int
    tool_calls: int
    stop_reason: str
