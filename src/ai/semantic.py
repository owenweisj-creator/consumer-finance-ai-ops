from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from src.config import ROOT

SEMANTIC_PATH = ROOT / "semantic_layer.yml"


@lru_cache(maxsize=1)
def load_semantic_layer(path: Path | None = None) -> dict:
    target = path or SEMANTIC_PATH
    with target.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def schema_text() -> str:
    layer = load_semantic_layer()
    lines = []
    for name, view in layer["views"].items():
        lines.append(f"### mart.{name}")
        lines.append(view["description"])
        lines.append("columns: " + ", ".join(view["columns"]))
        lines.append("grain: " + view["grain"])
        lines.append("")
    lines.append("### 规则")
    for rule in layer.get("rules", []):
        lines.append(f"- {rule}")
    return "\n".join(lines)


def metrics_text() -> str:
    layer = load_semantic_layer()
    lines = []
    for metric in layer["metrics"]:
        synonyms = "、".join(metric.get("synonyms", []))
        lines.append(f"- {metric['name']}（{synonyms}）：{metric['definition']}；视图 {metric['view']}，字段 {metric['expr']}")
    return "\n".join(lines)


def allowed_tables() -> set[str]:
    layer = load_semantic_layer()
    return {f"mart.{name}" for name in layer["views"]}


def metric_names() -> list[str]:
    layer = load_semantic_layer()
    names: list[str] = []
    for metric in layer["metrics"]:
        names.append(metric["name"])
        names.extend(metric.get("synonyms", []))
    return names
