from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ai.agent import AnalyticsCopilot
from src.ai.llm import DeepSeekClient, LLMError
from src.ai.nl2sql import NL2SQLGenerator, execute_sql
from src.ai.rag import KnowledgeBase
from src.config import EVAL_DIR


def load_questions(path: Path | None = None) -> list[dict]:
    target = path or EVAL_DIR / "questions.jsonl"
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").round(4)
    frame = frame.reindex(sorted(frame.columns), axis=1)
    return frame.sort_values(by=list(frame.columns), na_position="last").reset_index(drop=True)


def _match_columns(expected: pd.DataFrame, actual: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for column in expected.columns:
        if column in actual.columns:
            mapping[column] = column
            continue
        expected_tokens = set(column.split("_"))
        candidates = [
            (len(expected_tokens & set(candidate.split("_"))), candidate) for candidate in actual.columns
        ]
        best_overlap, best_column = max(candidates, default=(0, ""))
        if best_overlap >= 1:
            mapping[column] = best_column
            continue
        if len(expected.columns) == 1 and pd.api.types.is_numeric_dtype(expected[column]):
            numeric_columns = [
                candidate
                for candidate in actual.columns
                if pd.api.types.is_numeric_dtype(actual[candidate])
                and not any(token in candidate for token in ("month", "year", "id", "cohort", "mob"))
            ]
            if len(numeric_columns) == 1:
                mapping[column] = numeric_columns[0]
    return mapping


def compare_frames(expected: pd.DataFrame, actual: pd.DataFrame, tolerance: float = 0.02) -> tuple[bool, bool]:
    expected_n = _normalize(expected)
    actual_n = _normalize(actual)
    mapping = _match_columns(expected_n, actual_n)
    if len(mapping) != len(expected_n.columns):
        return False, False
    if len(expected_n) != len(actual_n):
        return False, False
    expected_view = expected_n[list(mapping.keys())].copy()
    actual_view = actual_n[list(mapping.values())].copy()
    actual_view.columns = expected_view.columns
    sort_columns = list(expected_view.columns)
    expected_view = expected_view.sort_values(by=sort_columns, na_position="last").reset_index(drop=True)
    actual_view = actual_view.sort_values(by=sort_columns, na_position="last").reset_index(drop=True)
    exact = expected_view.equals(actual_view)
    if exact:
        return True, True
    near = True
    for column in expected_view.columns:
        left = expected_view[column]
        right = actual_view[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            left_values = left.to_numpy(dtype=float)
            right_values = right.to_numpy(dtype=float)
            if not np.allclose(left_values, right_values, rtol=tolerance, atol=0.0001, equal_nan=True):
                near = False
                break
        elif not left.astype(str).equals(right.astype(str)):
            near = False
            break
    return False, near


def run_eval(version: str = "v2", limit: int | None = None, category: str | None = None) -> dict:
    questions = load_questions()
    if category:
        questions = [item for item in questions if item["category"] == category]
    if limit:
        questions = questions[:limit]
    client = DeepSeekClient()
    nl2sql = NL2SQLGenerator(client, version=version)
    kb = KnowledgeBase()
    copilot = AnalyticsCopilot(client)
    rows = []
    for item in questions:
        record = {
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "type": item["type"],
            "success": False,
            "exact_match": False,
            "near_match": False,
            "latency_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "error": None,
            "sql": None,
        }
        try:
            if item["type"] == "data":
                result = nl2sql.generate(item["question"])
                expected = execute_sql(item["golden_sql"])
                exact, near = compare_frames(expected, result.data)
                record.update(
                    {
                        "success": True,
                        "exact_match": exact,
                        "near_match": near,
                        "latency_ms": result.latency_ms,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "sql": result.sql,
                    }
                )
            elif item["type"] == "knowledge":
                answer = kb.answer(item["question"], client)
                text = answer.get("answer", "")
                keywords = item.get("expected_keywords", [])
                hit = sum(keyword in text for keyword in keywords) >= min(2, len(keywords))
                record.update(
                    {
                        "success": hit,
                        "exact_match": hit,
                        "near_match": hit,
                        "latency_ms": answer.get("latency_ms"),
                    }
                )
            else:
                answer = copilot.ask(item["question"])
                text = answer.get("answer", "")
                refused = answer.get("route") == "refused" or not answer.get("sql")
                hit = refused and any(keyword in text for keyword in item.get("expected_keywords", []))
                record.update({"success": hit, "exact_match": hit, "near_match": hit, "latency_ms": answer.get("latency_ms")})
        except Exception as exc:  # noqa: BLE001
            record["error"] = str(exc)[:500]
        rows.append(record)

    frame = pd.DataFrame(rows)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = EVAL_DIR / f"results_{version}.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    data_rows = frame[frame["type"] == "data"]
    knowledge_rows = frame[frame["type"].isin(["knowledge", "refusal"])]
    summary = {
        "version": version,
        "questions": len(frame),
        "data_questions": len(data_rows),
        "data_execution_success": round(float(data_rows["success"].mean()), 4) if len(data_rows) else None,
        "data_exact_match": round(float(data_rows["exact_match"].mean()), 4) if len(data_rows) else None,
        "data_near_match": round(float((data_rows["exact_match"] | data_rows["near_match"]).mean()), 4) if len(data_rows) else None,
        "knowledge_accuracy": round(float(knowledge_rows["success"].mean()), 4) if len(knowledge_rows) else None,
        "avg_latency_ms": round(float(frame["latency_ms"].dropna().mean()), 1) if frame["latency_ms"].notna().any() else None,
        "total_prompt_tokens": int(frame["prompt_tokens"].fillna(0).sum()),
        "total_completion_tokens": int(frame["completion_tokens"].fillna(0).sum()),
        "errors": int(frame["error"].notna().sum()),
    }
    (EVAL_DIR / f"summary_{version}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v2", choices=["v1", "v2"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()
    print(json.dumps(run_eval(args.version, args.limit, args.category), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
