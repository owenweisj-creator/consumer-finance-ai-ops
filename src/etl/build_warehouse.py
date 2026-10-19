from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from src.config import ANCHOR_DATE, DATA_PROCESSED, DATA_RAW, DB_PATH, REPORTS_DIR, ensure_dirs

RAW_TABLES = {
    "application_train": "application_train.csv",
    "previous_application": "previous_application.csv",
    "installments_payments": "installments_payments.csv",
    "pos_cash_balance": "POS_CASH_balance.csv",
    "credit_card_balance": "credit_card_balance.csv",
    "bureau": "bureau.csv",
    "bureau_balance": "bureau_balance.csv",
}

PLACEHOLDER_SCHEMAS = {
    "installments_payments": (
        "SK_ID_PREV BIGINT, SK_ID_CURR BIGINT, NUM_INSTALMENT_VERSION BIGINT, "
        "NUM_INSTALMENT_NUMBER BIGINT, DAYS_INSTALMENT BIGINT, DAYS_ENTRY_PAYMENT BIGINT, "
        "AMT_INSTALMENT DOUBLE, AMT_PAYMENT DOUBLE"
    ),
    "pos_cash_balance": (
        "SK_ID_PREV BIGINT, SK_ID_CURR BIGINT, MONTHS_BALANCE BIGINT, "
        "CNT_INSTALMENT DOUBLE, CNT_INSTALMENT_FUTURE DOUBLE, NAME_CONTRACT_STATUS VARCHAR, "
        "SK_DPD BIGINT, SK_DPD_DEF BIGINT"
    ),
    "credit_card_balance": (
        "SK_ID_PREV BIGINT, SK_ID_CURR BIGINT, MONTHS_BALANCE BIGINT, AMT_BALANCE DOUBLE, "
        "AMT_CREDIT_LIMIT_ACTUAL DOUBLE, AMT_DRAWINGS_CURRENT DOUBLE, AMT_PAYMENT_TOTAL_CURRENT DOUBLE, "
        "AMT_RECEIVABLE_PRINCIPAL DOUBLE, NAME_CONTRACT_STATUS VARCHAR, SK_DPD BIGINT, SK_DPD_DEF BIGINT"
    ),
    "bureau": (
        "SK_ID_BUREAU BIGINT, SK_ID_CURR BIGINT, CREDIT_ACTIVE VARCHAR, CREDIT_CURRENCY VARCHAR, "
        "CREDIT_TYPE VARCHAR, DAYS_CREDIT BIGINT, CREDIT_DAY_OVERDUE BIGINT, AMT_CREDIT_SUM DOUBLE, "
        "AMT_CREDIT_SUM_DEBT DOUBLE, AMT_CREDIT_SUM_OVERDUE DOUBLE, AMT_ANNUITY DOUBLE"
    ),
    "bureau_balance": "SK_ID_BUREAU BIGINT, MONTHS_BALANCE BIGINT, STATUS VARCHAR",
}


def _sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _load_raw(
    con: duckdb.DuckDBPyConnection,
    sample_rows: int | None = None,
    allow_missing: bool = False,
    skip_tables: set[str] | None = None,
) -> dict[str, int]:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    counts: dict[str, int] = {}
    skip_tables = skip_tables or set()
    for table, filename in RAW_TABLES.items():
        if table in skip_tables:
            con.execute(f"CREATE OR REPLACE TABLE raw.{table} ({PLACEHOLDER_SCHEMAS[table]})")
            counts[table] = 0
            print(f"skip raw.{table} by request; created empty placeholder")
            continue
        path = DATA_RAW / filename
        if not path.exists() or path.stat().st_size < 1000:
            if allow_missing:
                con.execute(f"CREATE OR REPLACE TABLE raw.{table} ({PLACEHOLDER_SCHEMAS[table]})")
                counts[table] = 0
                print(f"skip missing raw.{table}: {path}; created empty placeholder")
                continue
            raise FileNotFoundError(f"Missing or incomplete data file: {path}")
        source = f"read_csv_auto('{_sql_path(path)}', header=true, sample_size=200000"
        if sample_rows:
            source += f", all_varchar=false) LIMIT {sample_rows}"
        else:
            source += ")"
        con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM {source}")
        counts[table] = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
        print(f"loaded raw.{table}: {counts[table]:,} rows")
    return counts


def _build_dimensions(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS mart")
    anchor = ANCHOR_DATE.isoformat()

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.dim_date AS
        SELECT
            d::DATE AS date_key,
            date_trunc('month', d)::DATE AS month_start,
            date_trunc('week', d)::DATE AS week_start,
            year(d) AS year,
            month(d) AS month,
            day(d) AS day,
            strftime(d, '%Y-%m') AS year_month,
            strftime(d, '%Y-W%W') AS year_week
        FROM generate_series(DATE '2013-01-01', DATE '{anchor}', INTERVAL 1 DAY) AS t(d)
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.dim_customer AS
        SELECT
            SK_ID_CURR AS customer_id,
            CODE_GENDER AS gender,
            NAME_FAMILY_STATUS AS family_status,
            NAME_EDUCATION_TYPE AS education,
            NAME_INCOME_TYPE AS income_type,
            OCCUPATION_TYPE AS occupation,
            NAME_HOUSING_TYPE AS housing_type,
            ORGANIZATION_TYPE AS organization_type,
            CNT_CHILDREN AS children_count,
            CNT_FAM_MEMBERS AS family_members,
            REGION_RATING_CLIENT AS region_rating,
            REGION_RATING_CLIENT_W_CITY AS city_rating,
            REGION_POPULATION_RELATIVE AS region_population_relative,
            ROUND(-DAYS_BIRTH / 365.25, 1) AS age_years,
            CASE WHEN DAYS_EMPLOYED >= 365243 THEN NULL
                 ELSE ROUND(-DAYS_EMPLOYED / 365.25, 1) END AS employed_years,
            AMT_INCOME_TOTAL / 10000.0 AS income,
            AMT_CREDIT / 10000.0 AS credit_amount,
            AMT_ANNUITY / 10000.0 AS annuity,
            AMT_GOODS_PRICE / 10000.0 AS goods_price,
            ROUND(AMT_CREDIT / NULLIF(AMT_INCOME_TOTAL, 0), 3) AS credit_income_ratio,
            ROUND(AMT_ANNUITY / NULLIF(AMT_INCOME_TOTAL, 0), 3) AS annuity_income_ratio,
            ROUND(
                (COALESCE(EXT_SOURCE_1, 0) + COALESCE(EXT_SOURCE_2, 0) + COALESCE(EXT_SOURCE_3, 0))
                / NULLIF(
                    (CASE WHEN EXT_SOURCE_1 IS NOT NULL THEN 1 ELSE 0 END)
                    + (CASE WHEN EXT_SOURCE_2 IS NOT NULL THEN 1 ELSE 0 END)
                    + (CASE WHEN EXT_SOURCE_3 IS NOT NULL THEN 1 ELSE 0 END), 0
                  ), 4
            ) AS ext_source_mean
        FROM raw.application_train
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.dim_product AS
        SELECT row_number() OVER () AS product_id, *
        FROM (
            SELECT DISTINCT
                NAME_CONTRACT_TYPE AS contract_type,
                NAME_PRODUCT_TYPE AS product_type,
                NAME_PORTFOLIO AS portfolio,
                PRODUCT_COMBINATION AS product_combination,
                NAME_GOODS_CATEGORY AS goods_category,
                NAME_CASH_LOAN_PURPOSE AS loan_purpose
            FROM raw.previous_application
        )
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.dim_channel AS
        SELECT row_number() OVER () AS channel_id, *
        FROM (
            SELECT DISTINCT
                CHANNEL_TYPE AS channel_type,
                NAME_CLIENT_TYPE AS client_type,
                NAME_SELLER_INDUSTRY AS seller_industry
            FROM raw.previous_application
        )
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.dim_region AS
        SELECT DISTINCT
            REGION_RATING_CLIENT AS region_rating,
            REGION_RATING_CLIENT_W_CITY AS city_rating,
            REGION_POPULATION_RELATIVE AS region_population_relative
        FROM raw.application_train
        """
    )


def _build_facts(con: duckdb.DuckDBPyConnection) -> None:
    anchor = ANCHOR_DATE.isoformat()

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.fact_application AS
        SELECT
            SK_ID_CURR AS customer_id,
            TARGET AS target,
            NAME_CONTRACT_TYPE AS contract_type,
            NAME_TYPE_SUITE AS application_type,
            AMT_INCOME_TOTAL / 10000.0 AS income,
            AMT_CREDIT / 10000.0 AS credit_amount,
            AMT_ANNUITY / 10000.0 AS annuity,
            AMT_GOODS_PRICE / 10000.0 AS goods_price,
            CNT_CHILDREN AS children_count,
            CNT_FAM_MEMBERS AS family_members,
            REGION_RATING_CLIENT AS region_rating,
            REGION_RATING_CLIENT_W_CITY AS city_rating,
            REGION_POPULATION_RELATIVE AS region_population_relative,
            ROUND(-DAYS_BIRTH / 365.25, 1) AS age_years,
            CASE WHEN DAYS_EMPLOYED >= 365243 THEN NULL
                 ELSE ROUND(-DAYS_EMPLOYED / 365.25, 1) END AS employed_years,
            ROUND(AMT_CREDIT / NULLIF(AMT_INCOME_TOTAL, 0), 3) AS credit_income_ratio,
            ROUND(AMT_ANNUITY / NULLIF(AMT_INCOME_TOTAL, 0), 3) AS annuity_income_ratio,
            ROUND(
                (COALESCE(EXT_SOURCE_1, 0) + COALESCE(EXT_SOURCE_2, 0) + COALESCE(EXT_SOURCE_3, 0))
                / NULLIF(
                    (CASE WHEN EXT_SOURCE_1 IS NOT NULL THEN 1 ELSE 0 END)
                    + (CASE WHEN EXT_SOURCE_2 IS NOT NULL THEN 1 ELSE 0 END)
                    + (CASE WHEN EXT_SOURCE_3 IS NOT NULL THEN 1 ELSE 0 END), 0
                  ), 4
            ) AS ext_source_mean,
            WEEKDAY_APPR_PROCESS_START AS application_weekday,
            HOUR_APPR_PROCESS_START AS application_hour
        FROM raw.application_train
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.fact_previous_application AS
        SELECT
            SK_ID_PREV AS previous_id,
            SK_ID_CURR AS customer_id,
            NAME_CONTRACT_TYPE AS contract_type,
            NAME_CONTRACT_STATUS AS status,
            AMT_APPLICATION / 10000.0 AS applied_amount,
            AMT_CREDIT / 10000.0 AS approved_amount,
            AMT_ANNUITY / 10000.0 AS annuity,
            AMT_GOODS_PRICE / 10000.0 AS goods_price,
            AMT_DOWN_PAYMENT / 10000.0 AS down_payment,
            RATE_DOWN_PAYMENT AS down_payment_rate,
            RATE_INTEREST_PRIMARY AS interest_rate_primary,
            RATE_INTEREST_PRIVILEGED AS interest_rate_privileged,
            CNT_PAYMENT AS term_months,
            CHANNEL_TYPE AS channel_type,
            NAME_CLIENT_TYPE AS client_type,
            NAME_PRODUCT_TYPE AS product_type,
            NAME_PORTFOLIO AS portfolio,
            NAME_GOODS_CATEGORY AS goods_category,
            NAME_CASH_LOAN_PURPOSE AS loan_purpose,
            PRODUCT_COMBINATION AS product_combination,
            NAME_YIELD_GROUP AS yield_group,
            NAME_SELLER_INDUSTRY AS seller_industry,
            DAYS_DECISION AS days_decision,
            DATE '{anchor}' + CAST(DAYS_DECISION AS INTEGER) AS decision_date,
            DATE '{anchor}' + CAST(DAYS_FIRST_DRAWING AS INTEGER) AS first_drawing_date,
            DATE '{anchor}' + CAST(DAYS_LAST_DUE AS INTEGER) AS last_due_date
        FROM raw.previous_application
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.fact_installment AS
        WITH base AS (
            SELECT
                SK_ID_PREV AS previous_id,
                SK_ID_CURR AS customer_id,
                NUM_INSTALMENT_VERSION AS version,
                NUM_INSTALMENT_NUMBER AS installment_number,
                DAYS_INSTALMENT AS days_instalment,
                DAYS_ENTRY_PAYMENT AS days_entry_payment,
                AMT_INSTALMENT / 10000.0 AS amount_due,
                AMT_PAYMENT / 10000.0 AS amount_paid,
                DATE '{anchor}' + CAST(DAYS_INSTALMENT AS INTEGER) AS due_date,
                CASE WHEN DAYS_ENTRY_PAYMENT IS NULL THEN NULL
                     ELSE DATE '{anchor}' + CAST(DAYS_ENTRY_PAYMENT AS INTEGER) END AS paid_date,
                CASE
                    WHEN DAYS_ENTRY_PAYMENT IS NULL AND DAYS_INSTALMENT < 0
                        THEN CAST(-DAYS_INSTALMENT AS INTEGER)
                    WHEN DAYS_ENTRY_PAYMENT IS NULL THEN NULL
                    ELSE CAST(DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT AS INTEGER)
                END AS late_days
            FROM raw.installments_payments
        )
        SELECT
            *,
            CASE WHEN late_days >= 30 THEN 1 ELSE 0 END AS dpd30_flag,
            CASE WHEN late_days >= 60 THEN 1 ELSE 0 END AS dpd60_flag,
            CASE WHEN late_days >= 90 THEN 1 ELSE 0 END AS dpd90_flag
        FROM base
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.fact_pos_monthly AS
        SELECT
            SK_ID_PREV AS previous_id,
            SK_ID_CURR AS customer_id,
            MONTHS_BALANCE AS months_balance,
            DATE '{anchor}' + to_months(CAST(MONTHS_BALANCE AS INTEGER)) AS snapshot_date,
            CNT_INSTALMENT AS installment_count,
            CNT_INSTALMENT_FUTURE AS future_installment_count,
            NAME_CONTRACT_STATUS AS contract_status,
            SK_DPD AS dpd,
            SK_DPD_DEF AS dpd_default
        FROM raw.pos_cash_balance
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.fact_credit_card_monthly AS
        SELECT
            SK_ID_PREV AS previous_id,
            SK_ID_CURR AS customer_id,
            MONTHS_BALANCE AS months_balance,
            DATE '{anchor}' + to_months(CAST(MONTHS_BALANCE AS INTEGER)) AS snapshot_date,
            AMT_BALANCE / 10000.0 AS balance,
            AMT_CREDIT_LIMIT_ACTUAL / 10000.0 AS credit_limit,
            AMT_DRAWINGS_CURRENT / 10000.0 AS drawings_current,
            AMT_PAYMENT_TOTAL_CURRENT / 10000.0 AS payment_total_current,
            AMT_RECEIVABLE_PRINCIPAL / 10000.0 AS receivable_principal,
            NAME_CONTRACT_STATUS AS contract_status,
            SK_DPD AS dpd,
            SK_DPD_DEF AS dpd_default
        FROM raw.credit_card_balance
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE mart.fact_bureau AS
        SELECT
            SK_ID_BUREAU AS bureau_id,
            SK_ID_CURR AS customer_id,
            CREDIT_ACTIVE AS credit_active,
            CREDIT_CURRENCY AS credit_currency,
            CREDIT_TYPE AS credit_type,
            DAYS_CREDIT AS days_credit,
            DATE '{anchor}' + CAST(DAYS_CREDIT AS INTEGER) AS credit_date,
            CREDIT_DAY_OVERDUE AS credit_day_overdue,
            AMT_CREDIT_SUM / 10000.0 AS credit_sum,
            AMT_CREDIT_SUM_DEBT / 10000.0 AS credit_sum_debt,
            AMT_CREDIT_SUM_OVERDUE / 10000.0 AS credit_sum_overdue,
            AMT_ANNUITY / 10000.0 AS annuity
        FROM raw.bureau
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TABLE mart.fact_bureau_balance AS
        SELECT
            SK_ID_BUREAU AS bureau_id,
            MONTHS_BALANCE AS months_balance,
            STATUS AS status
        FROM raw.bureau_balance
        """
    )


def _build_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_funnel_monthly AS
        SELECT
            date_trunc('month', decision_date)::DATE AS month_start,
            strftime(decision_date, '%Y-%m') AS year_month,
            contract_type,
            channel_type,
            product_type,
            count(*) AS applications,
            sum(CASE WHEN status IN ('Approved', 'Unused offer') THEN 1 ELSE 0 END) AS approved,
            sum(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS used,
            sum(CASE WHEN status = 'Refused' THEN 1 ELSE 0 END) AS refused,
            sum(CASE WHEN status = 'Canceled' THEN 1 ELSE 0 END) AS canceled,
            sum(CASE WHEN status = 'Unused offer' THEN 1 ELSE 0 END) AS unused_offer,
            round(sum(CASE WHEN status IN ('Approved', 'Unused offer') THEN 1 ELSE 0 END)
                  / NULLIF(count(*), 0), 4) AS approval_rate,
            round(sum(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END)
                  / NULLIF(sum(CASE WHEN status IN ('Approved', 'Unused offer') THEN 1 ELSE 0 END), 0), 4) AS utilization_rate,
            sum(CASE WHEN status = 'Approved' THEN approved_amount ELSE 0 END) AS approved_amount,
            round(avg(CASE WHEN status = 'Approved' THEN approved_amount END), 2) AS avg_ticket,
            round(avg(CASE WHEN status = 'Approved' THEN term_months END), 2) AS avg_term_months,
            round(avg(CASE WHEN status = 'Approved' THEN interest_rate_primary END), 4) AS avg_interest_rate_primary
        FROM mart.fact_previous_application
        WHERE decision_date BETWEEN DATE '2024-01-01' AND DATE '2026-09-30'
        GROUP BY 1, 2, 3, 4, 5
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_kpi_monthly AS
        SELECT
            f.month_start,
            f.year_month,
            sum(f.applications) AS applications,
            sum(f.approved) AS approved,
            sum(f.used) AS used,
            sum(f.refused) AS refused,
            sum(f.unused_offer) AS unused_offer,
            round(sum(f.approved) / NULLIF(sum(f.applications), 0), 4) AS approval_rate,
            round(sum(f.used) / NULLIF(sum(f.approved), 0), 4) AS utilization_rate,
            round(sum(f.approved_amount), 2) AS approved_amount,
            round(sum(f.approved_amount) / NULLIF(sum(f.used), 0), 2) AS avg_ticket,
            round(sum(f.avg_term_months * f.used) / NULLIF(sum(f.used), 0), 2) AS avg_term_months,
            round(sum(f.avg_interest_rate_primary * f.used) / NULLIF(sum(f.used), 0), 4) AS avg_interest_rate_primary
        FROM mart.v_funnel_monthly f
        GROUP BY 1, 2
        ORDER BY 1
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_portfolio_current AS
        SELECT
            contract_type,
            region_rating,
            CASE
                WHEN age_years < 25 THEN '18-24'
                WHEN age_years < 35 THEN '25-34'
                WHEN age_years < 45 THEN '35-44'
                WHEN age_years < 55 THEN '45-54'
                ELSE '55+'
            END AS age_band,
            CASE
                WHEN income < 100000 THEN '<10万'
                WHEN income < 200000 THEN '10-20万'
                WHEN income < 500000 THEN '20-50万'
                ELSE '50万+'
            END AS income_band,
            count(*) AS customers,
            round(avg(target), 4) AS bad_rate,
            round(sum(credit_amount), 2) AS exposure,
            round(avg(credit_amount), 2) AS avg_credit,
            round(avg(annuity), 2) AS avg_annuity,
            round(avg(credit_income_ratio), 3) AS avg_credit_income_ratio,
            round(avg(ext_source_mean), 4) AS avg_ext_source
        FROM mart.fact_application
        GROUP BY 1, 2, 3, 4
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_vintage AS
        WITH first_due AS (
            SELECT
                previous_id,
                min(due_date) AS first_due_date,
                date_trunc('month', min(due_date))::DATE AS cohort_month
            FROM mart.fact_installment
            GROUP BY 1
        ),
        loan_mob AS (
            SELECT
                i.previous_id,
                f.cohort_month,
                date_diff('month', f.cohort_month, date_trunc('month', i.due_date)::DATE) AS mob,
                max(i.late_days) AS max_late_days,
                max(i.dpd30_flag) AS dpd30,
                max(i.dpd60_flag) AS dpd60,
                max(i.dpd90_flag) AS dpd90
            FROM mart.fact_installment i
            JOIN first_due f USING (previous_id)
            WHERE i.due_date <= DATE '2026-09-30'
            GROUP BY 1, 2, 3
        ),
        cumulative AS (
            SELECT
                *,
                max(dpd30) OVER (PARTITION BY previous_id ORDER BY mob ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_dpd30,
                max(dpd60) OVER (PARTITION BY previous_id ORDER BY mob ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_dpd60,
                max(dpd90) OVER (PARTITION BY previous_id ORDER BY mob ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_dpd90
            FROM loan_mob
        )
        SELECT
            cohort_month,
            strftime(cohort_month, '%Y-%m') AS cohort,
            mob,
            count(*) AS loans,
            round(avg(dpd30), 4) AS dpd30_rate,
            round(avg(dpd60), 4) AS dpd60_rate,
            round(avg(dpd90), 4) AS dpd90_rate,
            round(avg(cum_dpd30), 4) AS cum_dpd30_rate,
            round(avg(cum_dpd60), 4) AS cum_dpd60_rate,
            round(avg(cum_dpd90), 4) AS cum_dpd90_rate,
            round(avg(max_late_days), 2) AS avg_max_late_days
        FROM cumulative
        WHERE mob BETWEEN 0 AND 24
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_product_monthly AS
        SELECT
            year_month,
            contract_type,
            product_type,
            sum(applications) AS applications,
            sum(approved) AS approved,
            round(sum(approved) / NULLIF(sum(applications), 0), 4) AS approval_rate,
            sum(approved_amount) AS approved_amount,
            round(sum(approved_amount) / NULLIF(sum(used), 0), 2) AS avg_ticket
        FROM mart.v_funnel_monthly
        GROUP BY 1, 2, 3
        ORDER BY 1
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_channel_monthly AS
        SELECT
            year_month,
            channel_type,
            sum(applications) AS applications,
            sum(approved) AS approved,
            round(sum(approved) / NULLIF(sum(applications), 0), 4) AS approval_rate,
            sum(approved_amount) AS approved_amount,
            round(sum(approved_amount) / NULLIF(sum(used), 0), 2) AS avg_ticket
        FROM mart.v_funnel_monthly
        GROUP BY 1, 2
        ORDER BY 1
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_region_monthly AS
        SELECT
            region_rating,
            count(*) AS customers,
            round(avg(target), 4) AS bad_rate,
            round(sum(credit_amount), 2) AS exposure,
            round(avg(credit_amount), 2) AS avg_credit,
            round(avg(ext_source_mean), 4) AS avg_ext_source
        FROM mart.fact_application
        GROUP BY 1
        ORDER BY 1
        """
    )

    con.execute(
        """
        CREATE OR REPLACE VIEW mart.v_channel_rate_change AS
        WITH bounds AS (
            SELECT max(year_month) AS current_month,
                   (SELECT max(year_month) FROM mart.v_kpi_monthly
                    WHERE year_month < (SELECT max(year_month) FROM mart.v_kpi_monthly)) AS previous_month
            FROM mart.v_kpi_monthly
        ),
        current AS (
            SELECT f.channel_type,
                   sum(f.applications) AS applications,
                   sum(f.approved) AS approved,
                   sum(f.approved) / NULLIF(sum(f.applications), 0) AS approval_rate
            FROM mart.v_funnel_monthly f, bounds b
            WHERE f.year_month = b.current_month
            GROUP BY 1
        ),
        previous AS (
            SELECT f.channel_type,
                   sum(f.applications) AS applications,
                   sum(f.approved) AS approved,
                   sum(f.approved) / NULLIF(sum(f.applications), 0) AS approval_rate
            FROM mart.v_funnel_monthly f, bounds b
            WHERE f.year_month = b.previous_month
            GROUP BY 1
        ),
        totals AS (
            SELECT
                (SELECT sum(applications) FROM current) AS current_apps,
                (SELECT sum(approved) FROM current) AS current_approved,
                (SELECT sum(applications) FROM previous) AS previous_apps,
                (SELECT sum(approved) FROM previous) AS previous_approved
        ),
        merged AS (
            SELECT
                coalesce(c.channel_type, p.channel_type) AS channel_type,
                coalesce(p.applications, 0) AS previous_applications,
                coalesce(c.applications, 0) AS current_applications,
                coalesce(p.approved, 0) AS previous_approved,
                coalesce(c.approved, 0) AS current_approved,
                coalesce(p.approval_rate, 0) AS previous_rate,
                coalesce(c.approval_rate, 0) AS current_rate
            FROM current c FULL OUTER JOIN previous p USING (channel_type)
        )
        SELECT
            channel_type,
            round(previous_applications / NULLIF(t.previous_apps, 0), 4) AS weight_previous,
            round(current_applications / NULLIF(t.current_apps, 0), 4) AS weight_current,
            round(previous_rate, 4) AS previous_rate,
            round(current_rate, 4) AS current_rate,
            round((current_applications / NULLIF(t.current_apps, 0) - previous_applications / NULLIF(t.previous_apps, 0))
                  * (previous_rate - t.previous_approved / NULLIF(t.previous_apps, 0)), 6) AS mix_effect,
            round((current_applications / NULLIF(t.current_apps, 0)) * (current_rate - previous_rate), 6) AS rate_effect,
            round(
                (current_applications / NULLIF(t.current_apps, 0) - previous_applications / NULLIF(t.previous_apps, 0))
                * (previous_rate - t.previous_approved / NULLIF(t.previous_apps, 0))
                + (current_applications / NULLIF(t.current_apps, 0)) * (current_rate - previous_rate), 6
            ) AS total_effect
        FROM merged, totals t
        ORDER BY total_effect
        """
    )


def _data_quality(con: duckdb.DuckDBPyConnection, counts: dict[str, int]) -> dict:
    checks = []
    for table in counts:
        checks.append(
            {
                "table": f"raw.{table}",
                "rows": con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0],
                "columns": len(con.execute(f"DESCRIBE raw.{table}").fetchall()),
            }
        )

    key_checks = [
        ("raw.application_train", "SK_ID_CURR"),
        ("raw.previous_application", "SK_ID_PREV"),
        ("raw.installments_payments", "SK_ID_PREV,NUM_INSTALMENT_NUMBER"),
        ("raw.bureau", "SK_ID_BUREAU"),
    ]
    duplicates = {}
    for table, key in key_checks:
        if counts.get(table.replace("raw.", ""), 0) == 0:
            continue
        if "," in key:
            sql = (
                f"SELECT count(*) - (SELECT count(*) FROM "
                f"(SELECT DISTINCT {key} FROM {table})) FROM {table}"
            )
        else:
            sql = f"SELECT count(*) - count(DISTINCT {key}) FROM {table}"
        duplicates[f"{table}:{key}"] = con.execute(sql).fetchone()[0]

    null_checks = {}
    for table, column in [
        ("raw.application_train", "AMT_CREDIT"),
        ("raw.application_train", "AMT_ANNUITY"),
        ("raw.previous_application", "NAME_CONTRACT_STATUS"),
        ("raw.installments_payments", "DAYS_ENTRY_PAYMENT"),
    ]:
        if counts.get(table.replace("raw.", ""), 0) == 0:
            continue
        nulls = con.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NULL").fetchone()[0]
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        null_checks[f"{table}:{column}"] = round(nulls / total, 4) if total else None

    status = con.execute(
        "SELECT NAME_CONTRACT_STATUS, count(*) FROM raw.previous_application GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()

    report = {
        "source": "Home Credit public dataset via Hugging Face (minhSpaceX/home_credit)",
        "anchor_date": ANCHOR_DATE.isoformat(),
        "row_counts": counts,
        "table_checks": checks,
        "duplicate_keys": duplicates,
        "null_rates": null_checks,
        "previous_application_status": [{"status": s, "count": c} for s, c in status],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "data_quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 数据质量报告",
        "",
        f"- 数据源：{report['source']}",
        f"- 业务日历锚点：{report['anchor_date']}",
        "",
        "## 表级检查",
        "",
        "| 表 | 行数 | 字段数 |",
        "|---|---:|---:|",
    ]
    for item in checks:
        lines.append(f"| {item['table']} | {item['rows']:,} | {item['columns']} |")
    lines += ["", "## 主键重复", "", "| 表:主键 | 重复数 |", "|---|---:|"]
    for key, value in duplicates.items():
        lines.append(f"| {key} | {value:,} |")
    lines += ["", "## 关键字段缺失率", "", "| 字段 | 缺失率 |", "|---|---:|"]
    for key, value in null_checks.items():
        lines.append(f"| {key} | {value:.2%} |")
    lines += ["", "## 历史申请状态分布", "", "| 状态 | 笔数 |", "|---|---:|"]
    for item in report["previous_application_status"]:
        lines.append(f"| {item['status']} | {item['count']:,} |")
    (REPORTS_DIR / "data_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the consumer finance DuckDB warehouse.")
    parser.add_argument("--sample", type=int, default=None, help="Load only N rows per table for development.")
    parser.add_argument("--reuse-raw", action="store_true", help="Reuse raw tables already loaded in the database.")
    parser.add_argument("--allow-missing", action="store_true", help="Create empty placeholders for missing data files.")
    parser.add_argument("--skip-tables", nargs="*", default=[], help="Tables to skip even if files exist.")
    args = parser.parse_args()

    ensure_dirs()
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        if args.reuse_raw and con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name='application_train'"
        ).fetchone()[0]:
            counts = {
                table: con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0] for table in RAW_TABLES
            }
        else:
            counts = _load_raw(
                con,
                sample_rows=args.sample,
                allow_missing=args.allow_missing,
                skip_tables=set(args.skip_tables),
            )
        _build_dimensions(con)
        _build_facts(con)
        _build_views(con)
        report = _data_quality(con, counts)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    print(json.dumps(report["row_counts"], ensure_ascii=False, indent=2))
    print(f"warehouse: {DB_PATH}")


if __name__ == "__main__":
    main()
