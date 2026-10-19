from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.ai.llm import DeepSeekClient
from src.config import KNOWLEDGE_DIR

DOMAIN_TERMS = (
    "审批",
    "通过率",
    "用信",
    "不良",
    "逾期",
    "风险",
    "渠道",
    "产品",
    "客户",
    "金额",
    "件均",
    "期限",
    "vintage",
    "指标",
    "口径",
    "复贷",
    "经营",
    "申请",
    "贷款",
    "贷",
)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            tokens.extend(word[index : index + 2] for index in range(max(len(word) - 1, 1)))
            tokens.extend(word)
        else:
            tokens.append(word)
    return tokens


@dataclass
class Chunk:
    source: str
    section: str
    text: str


class KnowledgeBase:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or KNOWLEDGE_DIR
        self.chunks: list[Chunk] = []
        self._load()
        self.corpus = [tokenize(chunk.text) for chunk in self.chunks]
        self.index = BM25Okapi(self.corpus) if self.corpus else None

    def _load(self) -> None:
        for path in sorted(self.directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            current_section = "概述"
            buffer: list[str] = []
            for line in text.splitlines():
                if line.startswith("## "):
                    if buffer:
                        self.chunks.append(Chunk(path.name, current_section, "\n".join(buffer).strip()))
                    current_section = line[3:].strip()
                    buffer = [line]
                else:
                    buffer.append(line)
            if buffer:
                self.chunks.append(Chunk(path.name, current_section, "\n".join(buffer).strip()))

    def retrieve(self, query: str, top_k: int = 4) -> list[tuple[Chunk, float]]:
        if not self.index:
            return []
        scores = self.index.get_scores(tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        return [(self.chunks[index], float(score)) for index, score in ranked if score > 0]

    def answer(self, question: str, client: DeepSeekClient | None = None) -> dict:
        if not any(term.lower() in question.lower() for term in DOMAIN_TERMS):
            return {
                "answer": "这个问题不在消费金融经营分析知识库的范围内，无法据此回答。",
                "citations": [],
                "refused": True,
            }
        matches = self.retrieve(question, top_k=4)
        if not matches or matches[0][1] < 1.0:
            return {
                "answer": "知识库中没有找到足够依据，建议先补充指标口径或业务规则，再回答这个问题。",
                "citations": [],
                "refused": True,
            }
        context = "\n\n".join(
            f"[{chunk.source}#{chunk.section}]\n{chunk.text}" for chunk, _ in matches
        )
        if client is None:
            return {
                "answer": "检索到的依据如下：\n\n" + context,
                "citations": [f"{chunk.source}#{chunk.section}" for chunk, _ in matches],
                "refused": False,
            }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是消费金融经营分析知识助手。只能依据给定资料回答，"
                    "每个关键结论后必须用 [文件名#章节] 标注引用；资料不足时明确说不知道。"
                ),
            },
            {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
        ]
        response = client.chat(messages, temperature=0.0, max_tokens=900)
        return {
            "answer": response.content,
            "citations": [f"{chunk.source}#{chunk.section}" for chunk, _ in matches],
            "refused": False,
            "latency_ms": response.latency_ms,
        }
