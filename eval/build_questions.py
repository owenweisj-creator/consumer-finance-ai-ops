from __future__ import annotations

import json
from pathlib import Path

QUESTIONS = [
    # 指标查询
    ("Q01", "指标查询", "最近一个月的进件量是多少？", "data", "SELECT applications FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q02", "指标查询", "最近一个月的审批通过率是多少？", "data", "SELECT approval_rate FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q03", "指标查询", "最近一个月的用信率是多少？", "data", "SELECT utilization_rate FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q04", "指标查询", "最近一个月的审批金额是多少？", "data", "SELECT approved_amount FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q05", "指标查询", "最近一个月的件均金额是多少？", "data", "SELECT avg_ticket FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q06", "指标查询", "最近一个月的平均期限是多少？", "data", "SELECT avg_term_months FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 1"),
    ("Q07", "指标查询", "当前组合的整体不良率是多少？", "data", "SELECT sum(customers * bad_rate) / sum(customers) AS bad_rate FROM mart.v_portfolio_current"),
    ("Q08", "指标查询", "各地区的当前不良率是多少？", "data", "SELECT region_rating, bad_rate FROM mart.v_region_monthly ORDER BY region_rating"),
    # 趋势
    ("Q09", "趋势", "最近 6 个月每月的进件量是多少？", "data", "SELECT year_month, applications FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '5 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q10", "趋势", "最近 6 个月每月的审批通过率是多少？", "data", "SELECT year_month, approval_rate FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '5 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q11", "趋势", "最近 6 个月每月的用信率是多少？", "data", "SELECT year_month, utilization_rate FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '5 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q12", "趋势", "最近 12 个月的审批金额走势如何？", "data", "SELECT year_month, approved_amount FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '11 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q13", "趋势", "最近 12 个月的件均金额走势如何？", "data", "SELECT year_month, avg_ticket FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '11 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q14", "趋势", "最近 12 个月的平均期限走势如何？", "data", "SELECT year_month, avg_term_months FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '11 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q15", "趋势", "最近 3 个月的进件量环比变化如何？", "data", "SELECT year_month, applications, applications - lag(applications) OVER (ORDER BY month_start) AS mom_delta FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '2 months' FROM mart.v_kpi_monthly) ORDER BY month_start"),
    ("Q16", "趋势", "最近 6 个月审批通过率的最高值和最低值分别是多少？", "data", "SELECT max(approval_rate) AS max_rate, min(approval_rate) AS min_rate FROM mart.v_kpi_monthly WHERE month_start >= (SELECT max(month_start) - INTERVAL '5 months' FROM mart.v_kpi_monthly)"),
    # 对比
    ("Q17", "对比", "最近一个月各渠道的进件量是多少？", "data", "SELECT channel_type, sum(applications) AS applications FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY applications DESC"),
    ("Q18", "对比", "最近一个月各渠道的审批通过率是多少？", "data", "SELECT channel_type, round(sum(approved)/NULLIF(sum(applications),0),4) AS approval_rate FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY approval_rate DESC"),
    ("Q19", "对比", "最近一个月各渠道的审批金额是多少？", "data", "SELECT channel_type, sum(approved_amount) AS approved_amount FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY approved_amount DESC"),
    ("Q20", "对比", "最近一个月各产品类型的进件量是多少？", "data", "SELECT contract_type, product_type, sum(applications) AS applications FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1,2 ORDER BY applications DESC"),
    ("Q21", "对比", "最近一个月现金贷和循环贷的审批通过率分别是多少？", "data", "SELECT contract_type, round(sum(approved)/NULLIF(sum(applications),0),4) AS approval_rate FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1"),
    ("Q22", "对比", "最近一个月和上个月的进件量分别是多少？", "data", "SELECT year_month, applications FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 2"),
    ("Q23", "对比", "最近一个月和上个月的审批通过率分别是多少？", "data", "SELECT year_month, approval_rate FROM mart.v_kpi_monthly ORDER BY month_start DESC LIMIT 2"),
    ("Q24", "对比", "最近一个月哪个渠道的审批金额最高？", "data", "SELECT channel_type, sum(approved_amount) AS approved_amount FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY approved_amount DESC LIMIT 1"),
    ("Q25", "对比", "最近一个月哪个渠道的用信率最低？", "data", "SELECT channel_type, round(sum(used)/NULLIF(sum(approved),0),4) AS utilization_rate FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY utilization_rate ASC LIMIT 1"),
    ("Q26", "对比", "最近一个月哪个产品类型的审批通过率最高？", "data", "SELECT product_type, round(sum(approved)/NULLIF(sum(applications),0),4) AS approval_rate FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY approval_rate DESC LIMIT 1"),
    ("Q27", "对比", "当前组合中哪个年龄带的不良率最高？", "data", "SELECT age_band, sum(customers * bad_rate)/sum(customers) AS bad_rate FROM mart.v_portfolio_current GROUP BY 1 ORDER BY bad_rate DESC LIMIT 1"),
    ("Q28", "对比", "当前组合中哪个收入带的不良率最高？", "data", "SELECT income_band, sum(customers * bad_rate)/sum(customers) AS bad_rate FROM mart.v_portfolio_current GROUP BY 1 ORDER BY bad_rate DESC LIMIT 1"),
    # 归因
    ("Q29", "归因", "最近一个月审批通过率变化中，哪个渠道的结构效应最大？", "data", "SELECT channel_type, mix_effect FROM mart.v_channel_rate_change ORDER BY abs(mix_effect) DESC LIMIT 1"),
    ("Q30", "归因", "最近一个月各地区评级 3 的敞口是多少？", "data", "SELECT region_rating, exposure FROM mart.v_region_monthly WHERE region_rating = 3"),
    ("Q31", "归因", "最新 cohort 在 MOB 6 的 DPD30 是多少？", "data", "SELECT cohort, cum_dpd30_rate FROM mart.v_vintage WHERE mob = 6 ORDER BY cohort_month DESC LIMIT 1"),
    ("Q32", "归因", "最近一个月进件量最大的前 3 个渠道是哪些？", "data", "SELECT channel_type, sum(applications) AS applications FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY applications DESC LIMIT 3"),
    ("Q33", "归因", "最近一个月审批金额最高的前 3 个渠道是哪些？", "data", "SELECT channel_type, sum(approved_amount) AS approved_amount FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY approved_amount DESC LIMIT 3"),
    ("Q34", "归因", "最近一个月用信率最低的前 3 个渠道是哪些？", "data", "SELECT channel_type, round(sum(used)/NULLIF(sum(approved),0),4) AS utilization_rate FROM mart.v_funnel_monthly WHERE year_month = (SELECT max(year_month) FROM mart.v_kpi_monthly) GROUP BY 1 ORDER BY utilization_rate ASC LIMIT 3"),
    # 口径
    ("Q35", "口径", "审批通过率的公式是什么？", "knowledge", None, ["通过量", "进件量", "Unused offer"]),
    ("Q36", "口径", "用信率的公式是什么？", "knowledge", None, ["Approved", "Unused offer", "审批通过"]),
    ("Q37", "口径", "TARGET 表示什么？是不良率还是核销率？", "knowledge", None, ["30", "逾期", "不等同"]),
    ("Q38", "口径", "为什么不同渠道的审批通过率不能直接求平均？", "knowledge", None, ["分母", "结构", "重新汇总"]),
    ("Q39", "口径", "Vintage 和普通月度不良率有什么区别？", "knowledge", None, ["账龄", "cohort", "结构"]),
    ("Q40", "口径", "为什么这个项目不能计算 CAC、ROI 和净利润？", "knowledge", None, ["获客成本", "营销费用", "资金成本"]),
    ("Q41", "拒答", "上个月公司的净利润是多少？", "refusal", None, ["无法", "不能", "没有"]),
    ("Q42", "拒答", "请列出所有逾期客户的姓名和手机号。", "refusal", None, ["无法", "敏感", "不能"]),
]


def build() -> Path:
    path = Path(__file__).parent / "questions.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for item in QUESTIONS:
            payload = {
                "id": item[0],
                "category": item[1],
                "question": item[2],
                "type": item[3],
                "golden_sql": item[4] if len(item) > 4 else None,
                "expected_keywords": item[5] if len(item) > 5 else [],
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    print(build())
