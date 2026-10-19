import pytest

from src.ai.nl2sql import validate_sql


def test_accepts_select_on_semantic_view():
    sql = "SELECT year_month, applications FROM mart.v_kpi_monthly ORDER BY year_month"
    assert validate_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM mart.v_kpi_monthly",
        "UPDATE mart.v_kpi_monthly SET applications = 0",
        "INSERT INTO mart.v_kpi_monthly VALUES (1)",
        "DROP TABLE mart.v_kpi_monthly",
        "CREATE TABLE mart.x AS SELECT 1",
        "ALTER TABLE mart.v_kpi_monthly ADD COLUMN x INT",
        "SELECT * FROM raw.application_train",
        "SELECT * FROM mart.v_kpi_monthly; SELECT 1",
        "SELECT * FROM mart.v_kpi_monthly -- comment",
        "SELECT * FROM unknown.view_name",
        "SELECT * FROM mart.v_kpi_monthly UNION SELECT * FROM raw.application_train",
    ],
)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)


def test_rejects_empty_sql():
    with pytest.raises(ValueError):
        validate_sql("")

