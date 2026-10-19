from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

from src.ai.llm import DeepSeekClient, LLMError
from src.ai.semantic import allowed_tables, metrics_text, schema_text
from src.config import DB_PATH, PROMPTS_DIR


@dataclass
class NL2SQLResult:
    question: str
    sql: str
    explanation: str
    assumptions: list[str] = field(default_factory=list)
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    latency_ms: int = 0
    attempts: int = 1
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _load_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"nl2sql_{version}.md"
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    return text.replace("{{SCHEMA}}", schema_text()).replace("{{METRICS}}", metrics_text())


def validate_sql(sql: str | None) -> str:
    if not sql or not str(sql).strip():
        raise ValueError("模型未返回 SQL")
    sql = str(sql).strip()
    if ";" in sql:
        raise ValueError("禁止多语句或分号")
    if re.search(r"--|/\*", sql):
        raise ValueError("禁止 SQL 注释")
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"SQL 语法解析失败: {exc}") from exc
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise ValueError("只允许 SELECT 查询")
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if any(tree.find(node) for node in forbidden):
        raise ValueError("检测到写操作")
    tables = {table.name if not table.db else f"{table.db}.{table.name}" for table in tree.find_all(exp.Table)}
    unknown = {table for table in tables if table not in allowed_tables()}
    if unknown:
        raise ValueError(f"不允许访问的视图: {sorted(unknown)}")
    if not tables:
        raise ValueError("查询未使用语义层视图")
    return sql


def execute_sql(sql: str, row_limit: int = 200) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        wrapped = f"SELECT * FROM ({sql}) AS q LIMIT {int(row_limit)}"
        return con.execute(wrapped).df()
    finally:
        con.close()


class NL2SQLGenerator:
    def __init__(self, client: DeepSeekClient | None = None, version: str = "v2") -> None:
        self.client = client or DeepSeekClient()
        self.version = version
        self.system_prompt = _load_prompt(version)

    def generate(self, question: str, retries: int = 2) -> NL2SQLResult:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, retries + 2):
            payload, response = self.client.chat_json(messages, temperature=0.0, max_tokens=1200)
            if payload.get("sql") is None:
                raise LLMError(payload.get("reason", "该问题无法用现有视图回答"))
            sql = payload["sql"]
            try:
                sql = validate_sql(sql)
                data = execute_sql(sql)
                return NL2SQLResult(
                    question=question,
                    sql=sql,
                    explanation=payload.get("explanation", ""),
                    assumptions=payload.get("assumptions", []),
                    data=data,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempt,
                    model=response.model,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt > retries:
                    break
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": f"上一条 SQL 执行失败：{exc}。请只返回修正后的 JSON，不要解释。",
                    },
                ]
        raise LLMError(f"NL2SQL 失败: {last_error}")


def summarize_result(data: pd.DataFrame, max_rows: int = 8) -> str:
    if data.empty:
        return "查询结果为空。"
    preview = data.head(max_rows).to_string(index=False)
    return f"返回 {len(data)} 行，前 {min(len(data), max_rows)} 行如下：\n\n{preview}"
