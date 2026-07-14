from backend.app.rag.agent.graph import agent_graph


def test_agent_graph_is_bounded() -> None:
    result = agent_graph.invoke({'question': '测试', 'retrieval_rounds': 0, 'tool_calls': 0, 'stop_reason': ''})
    assert result['retrieval_rounds'] == 1
    assert result['tool_calls'] == 1
    assert result['stop_reason'] == 'bounded_retrieval'
