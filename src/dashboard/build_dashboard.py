from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.analytics.metrics import (
    anomaly_scan,
    customer_value_segments,
    monthly_kpis,
    query_df,
    rate_decomposition,
    region_summary,
    vintage_matrix,
)
from src.config import DASHBOARD_DIR


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", force_ascii=False))


def build_payload() -> dict:
    kpi = monthly_kpis().tail(12).copy()
    latest = kpi.iloc[-1]
    latest_month = str(latest["year_month"])
    channel = query_df(
        """
        SELECT channel_type,
               sum(applications) AS applications,
               round(sum(approved)/NULLIF(sum(applications),0),4) AS approval_rate,
               round(sum(used)/NULLIF(sum(approved),0),4) AS utilization_rate,
               round(sum(approved_amount),2) AS approved_amount
        FROM mart.v_funnel_monthly
        WHERE year_month = ?
        GROUP BY 1 ORDER BY approved_amount DESC
        """,
        [latest_month],
    )
    products = query_df(
        """
        SELECT contract_type, product_type, sum(applications) AS applications,
               round(sum(approved)/NULLIF(sum(applications),0),4) AS approval_rate
        FROM mart.v_funnel_monthly
        WHERE year_month = ?
        GROUP BY 1,2 ORDER BY applications DESC
        """,
        [latest_month],
    )
    vintage = vintage_matrix()
    if not vintage.empty:
        cohorts = sorted(vintage["cohort"].unique())[-18:]
        vintage = vintage[vintage["cohort"].isin(cohorts) & vintage["mob"].between(0, 12)]
    decomposition = rate_decomposition("channel_type", periods=2)
    return {
        "latest_month": latest_month,
        "latest": json.loads(kpi.tail(1).to_json(orient="records", force_ascii=False))[0],
        "kpi": _records(kpi),
        "funnel": [
            {"stage": "进件", "value": int(latest["applications"])},
            {"stage": "审批通过", "value": int(latest["approved"])},
            {"stage": "实际用信", "value": int(latest["used"])},
        ],
        "channel": _records(channel),
        "products": _records(products),
        "regions": _records(region_summary()),
        "segments": _records(customer_value_segments()),
        "vintage": _records(vintage),
        "alerts": anomaly_scan()[:6],
        "decomposition": _records(decomposition) if not decomposition.empty else [],
    }


def build_dashboard() -> Path:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    html = template.replace("__DATA__", json.dumps(payload, ensure_ascii=False, default=str))
    output = DASHBOARD_DIR / "index.html"
    output.write_text(html, encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build_dashboard())
