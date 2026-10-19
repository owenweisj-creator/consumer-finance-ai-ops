from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.config import DB_PATH, REPORTS_DIR


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Warehouse not found: {DB_PATH}. Run src.etl.build_warehouse first.")
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def query_df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    con = connect()
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


def monthly_kpis() -> pd.DataFrame:
    return query_df("SELECT * FROM mart.v_kpi_monthly ORDER BY month_start")


def funnel_by(dimension: str, months: int = 12) -> pd.DataFrame:
    allowed = {"contract_type", "channel_type", "product_type"}
    if dimension not in allowed:
        raise ValueError(f"Unsupported dimension: {dimension}")
    return query_df(
        f"""
        SELECT year_month, {dimension},
               sum(applications) AS applications,
               sum(approved) AS approved,
               sum(used) AS used,
               round(sum(approved) / NULLIF(sum(applications), 0), 4) AS approval_rate,
               round(sum(used) / NULLIF(sum(approved), 0), 4) AS utilization_rate,
               round(sum(approved_amount), 2) AS approved_amount,
               round(sum(approved_amount) / NULLIF(sum(used), 0), 2) AS avg_ticket
        FROM mart.v_funnel_monthly
        WHERE month_start >= (
            SELECT max(month_start) - INTERVAL '{int(months) - 1} months' FROM mart.v_funnel_monthly
        )
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    )


def portfolio_current() -> pd.DataFrame:
    return query_df("SELECT * FROM mart.v_portfolio_current ORDER BY customers DESC")


def region_summary() -> pd.DataFrame:
    return query_df("SELECT * FROM mart.v_region_monthly ORDER BY region_rating")


def vintage_matrix() -> pd.DataFrame:
    return query_df("SELECT * FROM mart.v_vintage ORDER BY cohort_month, mob")


def latest_snapshot() -> dict[str, Any]:
    df = monthly_kpis()
    if df.empty:
        return {}
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    result = {}
    for col in [
        "applications",
        "approved",
        "used",
        "approval_rate",
        "utilization_rate",
        "approved_amount",
        "avg_ticket",
        "avg_term_months",
        "avg_interest_rate_primary",
    ]:
        current_value = _to_number(latest.get(col))
        previous_value = _to_number(previous.get(col))
        result[col] = {
            "value": current_value,
            "previous": previous_value,
            "delta": None if current_value is None or previous_value is None else current_value - previous_value,
            "delta_pct": None
            if current_value is None or not previous_value
            else (current_value - previous_value) / previous_value,
        }
    result["period"] = str(latest["year_month"])
    result["previous_period"] = str(previous["year_month"])
    return result


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _robust_z(series: pd.Series, value: float, window: int = 6) -> float | None:
    history = series.dropna().tail(window)
    if len(history) < 4:
        return None
    median = float(history.median())
    mad = float((history - median).abs().median())
    if mad == 0:
        return None
    return 0.6745 * (value - median) / mad


def anomaly_scan() -> list[dict[str, Any]]:
    df = monthly_kpis()
    if len(df) < 6:
        return []
    metrics = {
        "applications": {"label": "进件量", "threshold": 2.5, "direction": "both"},
        "approval_rate": {"label": "审批通过率", "threshold": 2.5, "direction": "both"},
        "utilization_rate": {"label": "用信率", "threshold": 2.5, "direction": "both"},
        "approved_amount": {"label": "审批金额", "threshold": 2.5, "direction": "both"},
        "avg_ticket": {"label": "件均金额", "threshold": 2.5, "direction": "both"},
    }
    alerts: list[dict[str, Any]] = []
    for metric, config in metrics.items():
        series = pd.to_numeric(df[metric], errors="coerce")
        for idx in range(4, len(df)):
            value = series.iloc[idx]
            z = _robust_z(series.iloc[:idx], float(value), window=6)
            if z is None or abs(z) < config["threshold"]:
                continue
            prev = series.iloc[idx - 1]
            alerts.append(
                {
                    "period": str(df["year_month"].iloc[idx]),
                    "metric": metric,
                    "label": config["label"],
                    "value": float(value),
                    "previous": None if pd.isna(prev) else float(prev),
                    "delta_pct": None
                    if pd.isna(prev) or float(prev) == 0
                    else float((value - prev) / prev),
                    "robust_z": round(float(z), 2),
                    "severity": "high" if abs(z) >= 3.5 else "medium",
                }
            )
    return sorted(alerts, key=lambda item: (item["period"], -abs(item["robust_z"])), reverse=True)


def rate_decomposition(dimension: str = "channel_type", periods: int = 2) -> pd.DataFrame:
    """Decompose approval-rate change into mix and within-segment rate effects."""
    allowed = {"contract_type", "channel_type", "product_type"}
    if dimension not in allowed:
        raise ValueError(f"Unsupported dimension: {dimension}")
    df = funnel_by(dimension, months=max(periods, 2))
    if df.empty:
        return df
    months = sorted(df["year_month"].unique())[-periods:]
    if len(months) < 2:
        return pd.DataFrame()
    current_month, previous_month = months[-1], months[-2]

    current = df[df["year_month"] == current_month].copy()
    previous = df[df["year_month"] == previous_month].copy()
    current_total = current["applications"].sum()
    previous_total = previous["applications"].sum()
    current_rate = current["approved"].sum() / current_total if current_total else 0
    previous_rate = previous["approved"].sum() / previous_total if previous_total else 0

    merged = current.merge(
        previous[[dimension, "applications", "approved", "approval_rate"]],
        on=dimension,
        how="outer",
        suffixes=("_current", "_previous"),
    ).fillna(0)
    merged["weight_current"] = merged["applications_current"] / current_total if current_total else 0
    merged["weight_previous"] = merged["applications_previous"] / previous_total if previous_total else 0
    merged["mix_effect"] = (
        merged["weight_current"] - merged["weight_previous"]
    ) * (merged["approval_rate_previous"] - previous_rate)
    merged["rate_effect"] = merged["weight_current"] * (
        merged["approval_rate_current"] - merged["approval_rate_previous"]
    )
    merged["total_effect"] = merged["mix_effect"] + merged["rate_effect"]
    merged["current_month"] = current_month
    merged["previous_month"] = previous_month
    merged["overall_current_rate"] = current_rate
    merged["overall_previous_rate"] = previous_rate
    return merged.sort_values("total_effect").reset_index(drop=True)


def customer_value_segments() -> pd.DataFrame:
    """A transparent RFM-like segmentation using application and repayment behaviour."""
    apps = query_df(
        """
        SELECT
            a.customer_id,
            a.target,
            a.credit_amount,
            a.income,
            a.age_years,
            a.region_rating,
            a.ext_source_mean,
            coalesce(p.application_count, 0) AS application_count,
            coalesce(p.approved_count, 0) AS approved_count,
            coalesce(p.approved_amount, 0) AS approved_amount,
            coalesce(i.max_late_days, 0) AS max_late_days
        FROM mart.fact_application a
        LEFT JOIN (
            SELECT customer_id,
                   count(*) AS application_count,
                   sum(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved_count,
                   sum(CASE WHEN status = 'Approved' THEN approved_amount ELSE 0 END) AS approved_amount
            FROM mart.fact_previous_application
            GROUP BY 1
        ) p USING (customer_id)
        LEFT JOIN (
            SELECT customer_id, max(late_days) AS max_late_days
            FROM mart.fact_installment
            GROUP BY 1
        ) i USING (customer_id)
        """
    )
    if apps.empty:
        return apps
    apps["value_score"] = (
        apps["approved_amount"].rank(pct=True) * 0.5
        + apps["application_count"].rank(pct=True) * 0.3
        + apps["income"].rank(pct=True) * 0.2
    )
    apps["risk_score"] = (
        apps["target"].rank(pct=True) * 0.4
        + apps["max_late_days"].rank(pct=True) * 0.3
        + (1 - apps["ext_source_mean"].fillna(apps["ext_source_mean"].median())).rank(pct=True) * 0.3
    )
    apps["value_segment"] = pd.cut(
        apps["value_score"], bins=[-0.01, 0.33, 0.66, 1.01], labels=["低价值", "中价值", "高价值"]
    )
    apps["risk_segment"] = pd.cut(
        apps["risk_score"], bins=[-0.01, 0.33, 0.66, 1.01], labels=["低风险", "中风险", "高风险"]
    )
    summary = (
        apps.groupby(["value_segment", "risk_segment"], observed=True)
        .agg(
            customers=("customer_id", "count"),
            bad_rate=("target", "mean"),
            avg_credit=("credit_amount", "mean"),
            avg_income=("income", "mean"),
            avg_approved_amount=("approved_amount", "mean"),
            avg_applications=("application_count", "mean"),
        )
        .reset_index()
    )
    summary["bad_rate"] = summary["bad_rate"].round(4)
    for col in ["avg_credit", "avg_income", "avg_approved_amount", "avg_applications"]:
        summary[col] = summary[col].round(2)
    return summary


def save_insight_pack(path: Path | None = None) -> Path:
    """Compute the core facts used by dashboard, report and interview material."""
    path = path or REPORTS_DIR / "insight_pack.json"
    snapshot = latest_snapshot()
    alerts = anomaly_scan()
    decomposition = rate_decomposition("channel_type", periods=2)
    segments = customer_value_segments()
    vintage = vintage_matrix()
    region = region_summary()
    payload = {
        "snapshot": snapshot,
        "alerts": alerts[:8],
        "decomposition": decomposition.to_dict(orient="records") if not decomposition.empty else [],
        "segments": segments.to_dict(orient="records") if not segments.empty else [],
        "vintage_latest": vintage.tail(12).to_dict(orient="records") if not vintage.empty else [],
        "region": region.to_dict(orient="records") if not region.empty else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
