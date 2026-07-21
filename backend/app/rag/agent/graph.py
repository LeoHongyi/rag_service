from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.rag.agent.state import AgentState
from backend.core.conf import settings


def build_agent_graph() -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """构建不含任意工具的有界状态图"""

    def route(state: AgentState) -> AgentState:
        rounds = min(1, settings.RAG_AGENT_MAX_RETRIEVAL_ROUNDS)
        calls = min(1, settings.RAG_AGENT_MAX_TOOL_CALLS)
        return {**state, 'retrieval_rounds': rounds, 'tool_calls': calls, 'stop_reason': 'bounded_retrieval'}

    graph = StateGraph(AgentState)
    graph.add_node('route', route)
    graph.add_edge(START, 'route')
    graph.add_edge('route', END)
    return graph.compile()


agent_graph = build_agent_graph()
