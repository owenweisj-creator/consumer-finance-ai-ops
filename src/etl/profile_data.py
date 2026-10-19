from __future__ import annotations

import json

from src.analytics.metrics import connect
from src.config import REPORTS_DIR


def main() -> None:
    con = connect(read_only=True)
    try:
        profile = {}
        profile["application"] = con.execute(
            """
            SELECT count(*) AS rows,
                   round(avg(target), 4) AS bad_rate,
                   round(min(credit_amount), 2) AS min_credit,
                   round(max(credit_amount), 2) AS max_credit
            FROM mart.fact_application
            """
        ).df().to_dict(orient="records")[0]
        profile["previous"] = con.execute(
            """
            SELECT min(decision_date) AS min_date, max(decision_date) AS max_date,
                   count(*) AS rows,
                   count(DISTINCT customer_id) AS customers
            FROM mart.fact_previous_application
            """
        ).df().to_dict(orient="records")[0]
        profile["monthly"] = con.execute(
            """
            SELECT year_month, applications, approved, used, approval_rate, utilization_rate, approved_amount
            FROM mart.v_kpi_monthly
            ORDER BY month_start DESC LIMIT 18
            """
        ).df().to_dict(orient="records")
        profile["status"] = con.execute(
            "SELECT status, count(*) AS count FROM mart.fact_previous_application GROUP BY 1 ORDER BY 2 DESC"
        ).df().to_dict(orient="records")
        profile["installments"] = con.execute(
            "SELECT count(*) AS rows, min(due_date) AS min_due, max(due_date) AS max_due FROM mart.fact_installment"
        ).df().to_dict(orient="records")[0]
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "data_profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(profile, ensure_ascii=False, indent=2, default=str))
    finally:
        con.close()


if __name__ == "__main__":
    main()
