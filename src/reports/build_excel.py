from __future__ import annotations

from pathlib import Path

import pandas as pd
import xlsxwriter

from src.analytics.metrics import (
    anomaly_scan,
    customer_value_segments,
    monthly_kpis,
    query_df,
    region_summary,
    vintage_matrix,
)
from src.config import EXCEL_DIR

NAVY = "#173B57"
TEAL = "#0E7C86"
LIGHT = "#E6F3F4"
GRAY = "#6B7280"


def _write_table(
    workbook,
    worksheet,
    df: pd.DataFrame,
    start_row: int,
    start_col: int = 0,
    header_format=None,
    number_formats: dict | None = None,
    widths: dict | None = None,
) -> int:
    if df.empty:
        worksheet.write(start_row, start_col, "暂无数据", workbook.add_format({"italic": True, "font_color": GRAY}))
        return start_row + 2
    header_format = header_format or workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": NAVY, "border": 0, "align": "center", "valign": "vcenter"}
    )
    for col_index, column in enumerate(df.columns):
        worksheet.write(start_row, start_col + col_index, str(column), header_format)
        if widths and column in widths:
            worksheet.set_column(start_col + col_index, start_col + col_index, widths[column])
    for row_index, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for col_index, column in enumerate(df.columns):
            value = row[column]
            fmt = None
            if number_formats and column in number_formats:
                fmt = number_formats[column]
            if pd.isna(value):
                worksheet.write_blank(row_index, start_col + col_index, None, fmt)
            elif isinstance(value, (int, float)):
                worksheet.write_number(row_index, start_col + col_index, float(value), fmt)
            else:
                worksheet.write(row_index, start_col + col_index, str(value), fmt)
    return start_row + len(df) + 2


def build_excel() -> Path:
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXCEL_DIR / "消费金融经营分析工作簿.xlsx"
    workbook = xlsxwriter.Workbook(str(path))
    workbook.set_properties(
        {
            "title": "消费金融经营分析工作簿",
            "subject": "Home Credit public data operating analytics",
            "author": "魏嗣杰",
            "company": "个人项目",
            "comments": "Data source: Home Credit public dataset. Calendar is synthetic.",
        }
    )

    title_fmt = workbook.add_format({"bold": True, "font_size": 22, "font_color": NAVY, "font_name": "Microsoft YaHei"})
    sub_fmt = workbook.add_format({"font_size": 11, "font_color": GRAY, "font_name": "Microsoft YaHei"})
    section_fmt = workbook.add_format(
        {"bold": True, "font_size": 13, "font_color": NAVY, "bottom": 1, "bottom_color": TEAL, "font_name": "Microsoft YaHei"}
    )
    header_fmt = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": NAVY, "align": "center", "valign": "vcenter", "font_name": "Microsoft YaHei"}
    )
    text_fmt = workbook.add_format({"font_name": "Microsoft YaHei", "font_size": 10})
    pct_fmt = workbook.add_format({"num_format": "0.00%", "font_name": "Microsoft YaHei", "font_size": 10})
    num_fmt = workbook.add_format({"num_format": "#,##0", "font_name": "Microsoft YaHei", "font_size": 10})
    money_fmt = workbook.add_format({"num_format": "#,##0.00", "font_name": "Microsoft YaHei", "font_size": 10})

    # Cover
    cover = workbook.add_worksheet("封面与说明")
    cover.hide_gridlines(2)
    cover.set_column("A:A", 3)
    cover.set_column("B:B", 24)
    cover.set_column("C:C", 90)
    cover.write("B2", "消费金融经营分析工作簿", title_fmt)
    cover.write("B4", "项目定位", section_fmt)
    cover.write("C4", "以 Home Credit 公开消费金融数据复现“申请—审批—用信—放款—还款—逾期—复贷”全链路经营分析。", text_fmt)
    cover.write("B5", "数据来源", section_fmt)
    cover.write("C5", "Home Credit public dataset via Hugging Face (minhSpaceX/home_credit)。", text_fmt)
    cover.write("B6", "时间口径", section_fmt)
    cover.write("C6", "DAYS_* 相对天数映射到以 2026-09-30 为锚点的业务日历，仅用于趋势与 cohort 分析。", text_fmt)
    cover.write("B7", "金额口径", section_fmt)
    cover.write("C7", "金额统一为万元（归一化），仅用于结构与趋势分析，不代表真实人民币规模。", text_fmt)
    cover.write("B8", "协作说明", section_fmt)
    cover.write("C8", "本人负责业务定义、指标口径、分析假设、结论判断与验收；Codex 参与代码、文档与看板实现。", text_fmt)
    cover.write("B10", "工作表目录", section_fmt)
    sheets = [
        ("经营总览", "月度进件、审批、用信、金额、件均与趋势图"),
        ("审批漏斗", "最新月漏斗与渠道/产品拆分"),
        ("组合结构", "合同类型、地区、年龄、收入带的风险与敞口"),
        ("风险迁徙", "Vintage DPD30/60/90 矩阵"),
        ("客户分层", "价值 × 风险九宫格"),
        ("异常清单", "稳健 z 分数识别的经营异常"),
        ("指标口径", "核心指标公式、分母与使用边界"),
    ]
    for index, (name, description) in enumerate(sheets, start=11):
        cover.write(index, 1, name, workbook.add_format({"bold": True, "font_color": TEAL, "font_name": "Microsoft YaHei"}))
        cover.write(index, 2, description, text_fmt)
    cover.write("B20", "重要提示", section_fmt)
    cover.write("C20", "TARGET 表示 30+ 天逾期标签，不等同于核销率；AI 输出仅作辅助决策，发布前需人工复核。", text_fmt)

    # Overview
    kpi = monthly_kpis().tail(18)
    overview = workbook.add_worksheet("经营总览")
    overview.hide_gridlines(2)
    overview.write("A1", "月度经营总览", title_fmt)
    overview.write("A2", "数据锚点 2026-09-30｜金额单位：万元（归一化）", sub_fmt)
    display = kpi[
        ["year_month", "applications", "approved", "used", "approval_rate", "utilization_rate", "approved_amount", "avg_ticket", "avg_term_months"]
    ].rename(
        columns={
            "year_month": "月份",
            "applications": "进件量",
            "approved": "审批通过量",
            "used": "实际用信量",
            "approval_rate": "审批通过率",
            "utilization_rate": "用信率",
            "approved_amount": "审批金额",
            "avg_ticket": "件均",
            "avg_term_months": "平均期限",
        }
    )
    end_row = _write_table(
        workbook,
        overview,
        display,
        4,
        header_format=header_fmt,
        number_formats={
            "进件量": num_fmt,
            "审批通过量": num_fmt,
            "实际用信量": num_fmt,
            "审批通过率": pct_fmt,
            "用信率": pct_fmt,
            "审批金额": money_fmt,
            "件均": money_fmt,
            "平均期限": money_fmt,
        },
        widths={"月份": 12, "进件量": 12, "审批通过量": 14, "实际用信量": 14, "审批通过率": 14, "用信率": 12, "审批金额": 15, "件均": 12, "平均期限": 12},
    )
    chart = workbook.add_chart({"type": "column"})
    chart.add_series(
        {
            "name": "进件量",
            "categories": ["经营总览", 5, 0, end_row - 2, 0],
            "values": ["经营总览", 5, 1, end_row - 2, 1],
            "fill": {"color": TEAL},
        }
    )
    line = workbook.add_chart({"type": "line"})
    line.add_series(
        {
            "name": "审批通过率",
            "categories": ["经营总览", 5, 0, end_row - 2, 0],
            "values": ["经营总览", 5, 4, end_row - 2, 4],
            "y2_axis": True,
            "line": {"color": "#D97706", "width": 2.2},
        }
    )
    chart.combine(line)
    chart.set_title({"name": "月度进件量与审批通过率"})
    chart.set_y_axis({"name": "进件量"})
    chart.set_y2_axis({"name": "审批通过率", "num_format": "0%"})
    chart.set_size({"width": 780, "height": 360})
    overview.insert_chart("K4", chart)

    # Funnel
    latest_month = str(kpi.iloc[-1]["year_month"])
    funnel = query_df(
        """
        SELECT channel_type AS 渠道, sum(applications) AS 进件量, sum(approved) AS 审批通过量,
               sum(used) AS 实际用信量, round(sum(approved)/NULLIF(sum(applications),0),4) AS 审批通过率,
               round(sum(used)/NULLIF(sum(approved),0),4) AS 用信率, sum(approved_amount) AS 审批金额
        FROM mart.v_funnel_monthly WHERE year_month = ? GROUP BY 1 ORDER BY 进件量 DESC
        """,
        [latest_month],
    )
    ws = workbook.add_worksheet("审批漏斗")
    ws.hide_gridlines(2)
    ws.write("A1", f"审批漏斗（{latest_month}）", title_fmt)
    latest = kpi.iloc[-1]
    ws.write("A3", "进件", header_fmt)
    ws.write("B3", int(latest["applications"]), num_fmt)
    ws.write("A4", "审批通过", header_fmt)
    ws.write("B4", int(latest["approved"]), num_fmt)
    ws.write("A5", "实际用信", header_fmt)
    ws.write("B5", int(latest["used"]), num_fmt)
    ws.write("A6", "审批通过率", header_fmt)
    ws.write("B6", float(latest["approval_rate"]), pct_fmt)
    ws.write("A7", "用信率", header_fmt)
    ws.write("B7", float(latest["utilization_rate"]), pct_fmt)
    _write_table(workbook, ws, funnel, 9, header_format=header_fmt, number_formats={"审批通过率": pct_fmt, "用信率": pct_fmt, "审批金额": money_fmt})

    # Portfolio
    portfolio = query_df("SELECT * FROM mart.v_portfolio_current ORDER BY customers DESC")
    portfolio = portfolio.rename(
        columns={
            "contract_type": "合同类型",
            "region_rating": "地区评级",
            "age_band": "年龄带",
            "income_band": "收入带",
            "customers": "客户数",
            "bad_rate": "不良率",
            "exposure": "敞口",
            "avg_credit": "平均授信",
            "avg_annuity": "平均年金",
            "avg_credit_income_ratio": "授信收入比",
            "avg_ext_source": "外部评分均值",
        }
    )
    ws = workbook.add_worksheet("组合结构")
    ws.hide_gridlines(2)
    ws.write("A1", "当前在贷组合结构", title_fmt)
    _write_table(
        workbook,
        ws,
        portfolio,
        3,
        header_format=header_fmt,
        number_formats={"不良率": pct_fmt, "敞口": money_fmt, "平均授信": money_fmt, "平均年金": money_fmt, "授信收入比": money_fmt, "外部评分均值": money_fmt},
    )

    # Vintage
    vintage = vintage_matrix()
    ws = workbook.add_worksheet("风险迁徙")
    ws.hide_gridlines(2)
    ws.write("A1", "Vintage DPD30 迁徙矩阵", title_fmt)
    if not vintage.empty:
        pivot = vintage.pivot_table(index="cohort", columns="mob", values="cum_dpd30_rate", aggfunc="mean")
        ws.write(3, 0, "Cohort", header_fmt)
        for index, mob in enumerate(pivot.columns, start=1):
            ws.write(3, index, f"MOB {mob}", header_fmt)
        for row_index, (cohort, row) in enumerate(pivot.iterrows(), start=4):
            ws.write(row_index, 0, str(cohort), text_fmt)
            for col_index, value in enumerate(row, start=1):
                ws.write_number(row_index, col_index, float(value) if pd.notna(value) else 0, pct_fmt)
        last_row = 3 + len(pivot)
        last_col = len(pivot.columns)
        ws.conditional_format(4, 1, last_row, last_col, {"type": "3_color_scale", "min_color": "#F7FBFC", "mid_color": "#FDE68A", "max_color": "#B42318"})

    # Segments
    segments = customer_value_segments()
    ws = workbook.add_worksheet("客户分层")
    ws.hide_gridlines(2)
    ws.write("A1", "客户价值 × 风险分层", title_fmt)
    if not segments.empty:
        segments = segments.rename(
            columns={
                "value_segment": "价值分层",
                "risk_segment": "风险分层",
                "customers": "客户数",
                "bad_rate": "不良率",
                "avg_credit": "平均授信",
                "avg_income": "平均收入",
                "avg_approved_amount": "平均审批金额",
                "avg_applications": "平均申请次数",
            }
        )
        _write_table(
            workbook,
            ws,
            segments,
            3,
            header_format=header_fmt,
            number_formats={"不良率": pct_fmt, "平均授信": money_fmt, "平均收入": money_fmt, "平均审批金额": money_fmt, "平均申请次数": money_fmt},
        )

    # Alerts
    alerts = pd.DataFrame(anomaly_scan())
    ws = workbook.add_worksheet("异常清单")
    ws.hide_gridlines(2)
    ws.write("A1", "经营异常清单", title_fmt)
    if not alerts.empty:
        alerts = alerts.rename(
            columns={
                "period": "月份",
                "metric": "指标字段",
                "label": "指标",
                "value": "本期值",
                "previous": "上期值",
                "delta_pct": "环比",
                "robust_z": "稳健z",
                "severity": "严重度",
            }
        )
        _write_table(workbook, ws, alerts, 3, header_format=header_fmt, number_formats={"本期值": money_fmt, "上期值": money_fmt, "环比": pct_fmt, "稳健z": money_fmt})

    # Metric dictionary
    metrics = pd.DataFrame(
        [
            ("进件量", "全部申请笔数", "v_kpi_monthly.applications", "包含通过、拒绝、取消、未使用额度"),
            ("审批通过率", "(Approved + Unused offer) / 进件量", "v_kpi_monthly.approval_rate", "Unused offer 计入通过、不计入用信"),
            ("用信率", "Approved / (Approved + Unused offer)", "v_kpi_monthly.utilization_rate", "衡量批而不用的流失"),
            ("审批金额", "Approved 合同的 AMT_CREDIT 合计", "v_kpi_monthly.approved_amount", "万元（归一化）"),
            ("件均", "审批金额 / 实际用信量", "v_kpi_monthly.avg_ticket", "受产品结构影响"),
            ("不良率", "TARGET=1 客户占比", "v_portfolio_current.bad_rate", "30+ 天逾期标签，不等同核销率"),
            ("DPD30", "账龄月内最大逾期>=30天的贷款占比", "v_vintage.dpd30_rate", "按 cohort 与账龄计算"),
            ("复贷率", "申请次数>=2 客户 / 有历史申请客户", "客户粒度计算", "需同时看复贷客户风险"),
        ],
        columns=["指标", "公式", "数据视图/字段", "口径说明"],
    )
    ws = workbook.add_worksheet("指标口径")
    ws.hide_gridlines(2)
    ws.write("A1", "核心指标口径", title_fmt)
    _write_table(workbook, ws, metrics, 3, header_format=header_fmt, widths={"指标": 16, "公式": 42, "数据视图/字段": 34, "口径说明": 46})

    workbook.close()
    return path


if __name__ == "__main__":
    print(build_excel())
