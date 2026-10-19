from src.ai.rag import KnowledgeBase


def test_retrieves_approval_rate_definition():
    kb = KnowledgeBase()
    matches = kb.retrieve("审批通过率的公式和口径是什么", top_k=3)
    assert matches
    assert any("metric_dictionary.md" in chunk.source for chunk, _ in matches)


def test_refuses_unrelated_question_without_llm():
    kb = KnowledgeBase()
    result = kb.answer("公司食堂今天有什么菜", client=None)
    assert result["refused"] is True

