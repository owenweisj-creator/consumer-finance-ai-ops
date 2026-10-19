from __future__ import annotations

import json
from typing import Any

from src.ai.llm import DeepSeekClient, LLMError
from src.ai.nl2sql import NL2SQLGenerator, summarize_result
from src.ai.rag import KnowledgeBase

DEFINITION_HINTS = ("口径", "定义", "是什么", "怎么算", "公式", "含义", "规则", "为什么", "区别")


class AnalyticsCopilot:
    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()
        self.nl2sql = NL2SQLGenerator(self.client, version="v2")
        self.kb = KnowledgeBase()

    def ask(self, question: str, prefer_knowledge: bool = False) -> dict[str, Any]:
        if prefer_knowledge or any(hint in question for hint in DEFINITION_HINTS):
            knowledge = self.kb.answer(question, self.client)
            if not knowledge["refused"]:
                return {"route": "knowledge", **knowledge}
        try:
            result = self.nl2sql.generate(question)
            records = json.loads(result.data.to_json(orient="records", force_ascii=False))
            return {
                "route": "data",
                "answer": result.explanation or summarize_result(result.data),
                "sql": result.sql,
                "data": records,
                "columns": list(result.data.columns),
                "assumptions": result.assumptions,
                "latency_ms": result.latency_ms,
                "attempts": result.attempts,
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            }
        except (LLMError, Exception) as exc:  # noqa: BLE001
            knowledge = self.kb.answer(question, self.client)
            if not knowledge["refused"]:
                return {"route": "knowledge_fallback", "error": str(exc), **knowledge}
            return {
                "route": "refused",
                "answer": "这个问题暂时无法用现有数据视图或知识库回答。请补充口径或换一种问法。",
                "error": str(exc),
            }


def result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
