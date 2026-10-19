from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from src.analytics.metrics import customer_value_segments
from src.config import PORTFOLIO_DIR, REPORTS_DIR, ROOT
from src.reports.charts import NAVY, TEAL, GRAY, set_chinese_font

NAVY_RGB = RGBColor(0x17, 0x3B, 0x57)
TEAL_RGB = RGBColor(0x0E, 0x7C, 0x86)
GRAY_RGB = RGBColor(0x4B, 0x55, 0x63)


def _font(run, size=10, bold=False, color=GRAY_RGB):
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color


def _body(doc, text, size=10, bold=False, color=GRAY_RGB, space_after=5):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    paragraph.paragraph_format.line_spacing = 1.35
    run = paragraph.add_run(text)
    _font(run, size=size, bold=bold, color=color)
    return paragraph


def _heading(doc, text, level=1):
    paragraph = doc.add_heading(text, level=level)
    for run in paragraph.runs:
        _font(run, size=17 if level == 1 else 13, bold=True, color=NAVY_RGB if level == 1 else TEAL_RGB)
    return paragraph


def _bullet(doc, text, size=9.8):
    paragraph = doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing = 1.28
    run = paragraph.add_run(text)
    _font(run, size=size)


def _table(doc, df: pd.DataFrame, widths=None):
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = "Table Grid"
    for index, column in enumerate(df.columns):
        cell = table.rows[0].cells[index]
        cell.text = str(column)
        tc_pr = cell._tc.get_or_add_tcPr()
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "173B57")
        tc_pr.append(shading)
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                _font(run, size=8.5, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    for _, row in df.iterrows():
        cells = table.add_row().cells
        for index, column in enumerate(df.columns):
            cells[index].text = str(row[column])
            for paragraph in cells[index].paragraphs:
                for run in paragraph.runs:
                    _font(run, size=8.5)
    if widths:
        for row in table.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Inches(width)
    return table


def _architecture(path: Path) -> Path:
    set_chinese_font()
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.axis("off")
    boxes = [
        (0.02, 0.62, 0.17, 0.24, "7 张公开数据表\n申请/审批/还款/账本/征信", "#E6F3F4"),
        (0.23, 0.62, 0.17, 0.24, "DuckDB 星型模型\n维度 + 事实 + 质量检查", "#D7EEF0"),
        (0.44, 0.62, 0.17, 0.24, "语义层 YAML\n指标/维度/口径/同义词", "#C9E7EA"),
        (0.65, 0.62, 0.17, 0.24, "AI Copilot\nNL2SQL + RAG + 校验", "#B9DFE2"),
        (0.86, 0.62, 0.12, 0.24, "交付\n看板/Excel/报告", "#A8D6DA"),
        (0.44, 0.18, 0.17, 0.24, "只读执行\nDuckDB read_only", "#F3F7F8"),
        (0.65, 0.18, 0.17, 0.24, "评测与护栏\n42 题 + 拦截", "#F3F7F8"),
        (0.23, 0.18, 0.17, 0.24, "知识库 BM25\n指标/规则/SOP", "#F3F7F8"),
    ]
    for x, y, w, h, text, color in boxes:
        rect = plt.Rectangle((x, y), w, h, facecolor=color, edgecolor="#9DB9C7", linewidth=1)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5, color=NAVY)
    arrows = [
        ((0.19, 0.74), (0.23, 0.74)),
        ((0.40, 0.74), (0.44, 0.74)),
        ((0.61, 0.74), (0.65, 0.74)),
        ((0.82, 0.74), (0.86, 0.74)),
        ((0.52, 0.62), (0.52, 0.45)),
        ((0.61, 0.30), (0.65, 0.30)),
        ((0.40, 0.30), (0.44, 0.30)),
        ((0.31, 0.42), (0.31, 0.62)),
    ]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="->", color="#5B7C8D", lw=1.2))
    ax.text(0.5, 0.96, "从数据到 AI 经营分析的产品化链路", ha="center", va="center", fontsize=12, color=NAVY, fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _segment_chart(path: Path) -> Path:
    set_chinese_font()
    df = customer_value_segments()
    if df.empty:
        return path
    df = df.copy()
    df["label"] = df["value_segment"].astype(str) + "/" + df["risk_segment"].astype(str)
    df = df.sort_values("bad_rate")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    colors = [TEAL if value < 0.1 else "#D97706" if value < 0.3 else "#B42318" for value in df["bad_rate"]]
    ax.barh(df["label"], df["bad_rate"] * 100, color=colors, height=0.6)
    for index, value in enumerate(df["bad_rate"] * 100):
        ax.text(value + 0.4, index, f"{value:.1f}%", va="center", fontsize=8, color=NAVY)
    ax.set_xlabel("不良率 (%)", color=GRAY)
    ax.set_title("客户价值 × 风险分层：不良率差异明显", loc="left", fontsize=12, color=NAVY, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=GRAY, labelsize=8)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _scorecard_chart(path: Path) -> Path:
    set_chinese_font()
    metrics = json.loads((REPORTS_DIR / "scorecard_metrics.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(metrics["risk_band_summary"])
    fig, ax = plt.subplots(figsize=(8, 3.3))
    x = range(len(df))
    ax.bar([i - 0.18 for i in x], df["bad_rate"] * 100, width=0.35, color=TEAL, label="实际不良率")
    ax.bar([i + 0.18 for i in x], df["avg_pd"] * 100, width=0.35, color="#D97706", label="预测 PD")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["risk_band"], fontsize=8, color=GRAY)
    ax.set_ylabel("%", color=GRAY)
    ax.set_title(f"风险评分卡：AUC {metrics['auc']:.3f}，KS {metrics['ks']:.3f}，PD 校准良好", loc="left", fontsize=12, color=NAVY, fontweight="bold")
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def build_portfolio() -> Path:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((REPORTS_DIR / "project_metrics.json").read_text(encoding="utf-8"))
    scorecard = json.loads((REPORTS_DIR / "scorecard_metrics.json").read_text(encoding="utf-8"))
    architecture = _architecture(PORTFOLIO_DIR / "architecture.png")
    segment = _segment_chart(PORTFOLIO_DIR / "segments.png")
    scorecard_chart = _scorecard_chart(PORTFOLIO_DIR / "scorecard.png")

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    # Cover
    _body(doc, "个人项目作品集", size=11, bold=True, color=TEAL_RGB, space_after=16)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(10)
    run = title.add_run("消费金融经营分析\nAI Copilot")
    _font(run, size=30, bold=True, color=NAVY_RGB)
    _body(doc, "从 0 到 1：把申请—审批—用信—放款—还款—逾期—复贷全链路数据，做成可监控、可归因、可问数的 AI 助手。", size=12, space_after=18)
    _body(doc, "项目负责人：魏嗣杰", size=10.5, bold=True, color=NAVY_RGB)
    _body(doc, "协作说明：本人负责业务定义、指标口径、分析假设、结论判断与验收；Codex 参与数据管道、分析代码、AI 服务、看板与文档实现。", size=9.5)
    _body(doc, "数据来源：Home Credit 公开消费金融数据集｜业务日历锚点：2026-09-30｜编制日期：2026-10", size=9.5)
    doc.add_page_break()

    # 1. Business problem
    _heading(doc, "01 业务问题与项目目标")
    _body(doc, "消费金融经营分析常见的三个断点：申请、审批、用信、还款、逾期分散在不同表；通过率变化说不清是结构还是能力；业务取数依赖排期，AI 问数又容易编造字段和数字。")
    _body(doc, "这个项目要回答三个问题：", bold=True, color=NAVY_RGB)
    _bullet(doc, "为什么 2026 年 9 月进件量上升，审批通过率却降到 22.9%？是渠道结构变化，还是同一渠道自身审批变严？")
    _bullet(doc, "审批金额增长 32.1%，是靠件数扩张，还是靠件均和期限上升？这种增长可持续吗？")
    _bullet(doc, "AI 能不能让业务人员用自然语言问数，同时保证口径正确、数字可追溯、危险 SQL 被拦截？")
    _body(doc, "项目边界：使用公开历史数据，业务日历为映射后的模拟时间；金额归一化为万元；不计算 CAC、ROI 和净利润。所有结论优先看结构和趋势，不对外声称绝对规模。")

    # 2. Data & architecture
    _heading(doc, "02 数据底座与技术架构")
    doc.add_picture(str(architecture), width=Inches(6.7))
    _body(doc, "数据底座采用 DuckDB 星型模型：客户、产品、渠道、地区、日期五个维度，申请、历史申请、分期还款、POS/信用卡账本、征信五类事实。原始表约 5,800 万行，覆盖 7 张业务表。")
    data_table = pd.DataFrame(
        [
            ("application_train", "307,511", "当前申请/在贷客户快照，含 TARGET"),
            ("previous_application", "1,670,214", "历史申请与审批结果，支撑漏斗"),
            ("installments_payments", "13,605,401", "每期应还/实还/逾期天数"),
            ("POS_CASH_balance", "10,001,358", "POS 分期月度账本"),
            ("credit_card_balance", "3,840,312", "信用卡额度与余额账本"),
            ("bureau", "1,716,428", "外部征信与历史信用表现"),
            ("bureau_balance", "27,299,925", "征信月度状态账本"),
        ],
        columns=["表", "行数", "业务用途"],
    )
    _table(doc, data_table, widths=[1.8, 1.0, 3.4])
    _body(doc, "关键口径：审批通过率 =（Approved + Unused offer）/ 进件量；用信率 = Approved /（Approved + Unused offer）；TARGET 为 30+ 天逾期标签，不等同于核销率。", size=9.5)

    # 3. Findings
    _heading(doc, "03 关键发现")
    _body(doc, "发现一：审批通过率下降 6.5 个百分点，主要是渠道结构效应，而不是全渠道审批能力同步恶化。", bold=True, color=NAVY_RGB)
    _body(doc, "2026-09 进件量 36,012 笔（环比 +26.2%），审批通过率 22.9%（环比 -6.5pp，稳健 z = -7.11）。Credit and cash offices 申请占比从 60.3% 升至 65.1%，该渠道通过率仅 7.84%，贡献结构效应约 -1.00pp；Country-wide 占比从 16.7% 降至 12.2%，贡献结构效应约 -2.75pp。渠道结构合计效应约 -6.52pp，说明‘低通过率渠道扩张 + 高通过率渠道收缩’是主因。")
    doc.add_picture(str(REPORTS_DIR / "chart_kpi_trend.png"), width=Inches(6.6))
    _body(doc, "发现二：审批金额增长由‘价’驱动，不是‘量’驱动。", bold=True, color=NAVY_RGB)
    _body(doc, "审批金额 188,681 万元（环比 +32.1%），但审批件数 8,245 笔（环比 -1.8%），实际用信 8,070 笔（环比 +1.2%）；件均 23.38 万元（+30.5%），平均期限 15.97 个月（+2.31 个月），平均利率档位 12.86%（+1.16pp）。规模增长依赖单笔金额和期限，若件均回落，金额增长不可持续。")
    _body(doc, "发现三：Vintage 显示早期账龄风险可控，但口径与 TARGET 不可混用。", bold=True, color=NAVY_RGB)
    _body(doc, "按放款 cohort 观察，MOB 6 的累计 DPD30 约 0.44%–0.49%，MOB 12 约 0.69%。installments 的 DPD30 累计率显著低于 application_train 的 TARGET 不良率 8.07%，说明两个口径覆盖的风险事件不同：前者是分期逾期，后者是 30+ 天违约标签。报告中不混用，避免把不同风险口径当成同一件事。")
    doc.add_picture(str(REPORTS_DIR / "chart_vintage.png"), width=Inches(6.7))
    _body(doc, "发现四：客户价值 × 风险九宫格差异明显，高价值高风险客群需要单独策略。", bold=True, color=NAVY_RGB)
    _body(doc, "高价值低风险客户 5,458 人，不良率 0%；高价值高风险客户 14,346 人，不良率 40.8%；高价值中风险客户 69,211 人，不良率 1.3%。这说明‘高价值’不等于‘低风险’，不能用同一套提额和复贷策略覆盖全部高价值客户。")
    doc.add_picture(str(segment), width=Inches(6.4))
    _body(doc, "发现五：评分卡 PD 校准良好，可用于分层而非直接授信。", bold=True, color=NAVY_RGB)
    _body(doc, f"WOE/IV + 逻辑回归评分卡在测试集上 AUC {scorecard['auc']:.3f}、KS {scorecard['ks']:.3f}；五个风险带的实际不良率从 2.27% 单调上升到 19.19%，预测 PD 与实测不良率基本一致。定位是客户分层工具，不是生产级授信模型。")
    doc.add_picture(str(scorecard_chart), width=Inches(6.4))
    _body(doc, "发现六：账本结构在从分期向循环额度迁移。", bold=True, color=NAVY_RGB)
    _body(doc, "信用卡额度使用率从 2026-06 的 41.1% 升至 2026-08 的 52.3%，但 POS 活跃合同从 18.4 万降到 9.5 万。循环额度使用上升、分期活跃下降，意味着存量客户更依赖信用卡额度；后续需要把额度使用率与 DPD30 联动监控，避免‘额度越用越满、风险越滚越大’。")
    doc.add_page_break()

    # 4. AI Copilot
    _heading(doc, "04 AI Copilot：怎么让 AI 可信")
    _body(doc, "AI 链路不是‘把数据库接给大模型’，而是‘语义层 + 只读执行 + 校验 + 评测’：")
    for item in [
        "语义层 YAML 定义 13 个指标、7 个视图、同义词、口径和使用边界；模型只能查 mart.v_* 视图。",
        "NL2SQL 生成 SQL 后用 sqlglot 校验：只允许 SELECT，禁止 DDL/DML、多语句、注释和 raw schema。",
        "DuckDB read_only 执行，结果最多 200 行；失败时把错误回传给模型，最多重试 2 次。",
        "RAG 覆盖指标口径、业务规则和 AI 使用手册，回答必须带 [文件名#章节] 引用；无依据时拒答。",
        "报告数字由 Python 计算后注入，LLM 只负责解释和建议；生成后做数字一致性校验，不一致自动回退模板。",
    ]:
        _bullet(doc, item)
    _body(doc, "评测结果（42 题，DeepSeek）：", bold=True, color=NAVY_RGB)
    eval_table = pd.DataFrame(
        [
            ("Prompt v1", "82.35%", "87.5%", "100%", "1.28s"),
            ("Prompt v2", "85.29%", "87.5%", "100%", "1.30s"),
        ],
        columns=["版本", "SQL 结果准确率", "知识问答准确率", "危险 SQL 拦截率", "平均延迟"],
    )
    _table(doc, eval_table, widths=[1.1, 1.5, 1.5, 1.4, 1.0])
    _body(doc, "v2 相对 v1 准确率提升 2.94pp，但 prompt token 增加约 22.7%。这说明 Prompt 不是越长越好：v2 的‘先拆指标/时间/维度/过滤 + 少样本 + 拒答规则’对复杂问题有帮助，但简单问题用 v1 更省成本。", size=9.5)
    _body(doc, "一个真实失败案例：模型对‘各产品类型进件量’只按 product_type 聚合，忽略了同一 product_type 在现金贷/循环贷下重复出现，导致口径歧义。修正方式是在语义层把产品维度定义为 contract_type × product_type，并在评测集中保留该题。", size=9.5)

    # 5. Productization
    _heading(doc, "05 产品化与落地")
    _body(doc, "交付物不是只有一个 notebook，而是一套能进入经营例会的工具：")
    for item in [
        "HTML 看板：经营总览、审批漏斗、组合与风险、Vintage、异常与归因、AI 示例六个模块，离线可打开。",
        "Excel 工作簿：9 张表、原生图表、指标口径页，可直接用于经营例会。",
        "三类报告：周报、月报、专项（审批通过率结构分解），数字与 SQL 可追溯。",
        "产品文档：PRD、需求池、RACI、30 条 UAT、60 分钟培训手册、推广与采纳指标。",
        "AI 行业简报与 3 个创新提案：经营例会助手、审批策略 Copilot、客户经营 Agent。",
    ]:
        _bullet(doc, item)
    screenshot = ROOT / "outputs" / "dashboard" / "dashboard_screenshot.png"
    if screenshot.exists():
        doc.add_picture(str(screenshot), width=Inches(6.7))
    _body(doc, "采纳度量：激活率 ≥60%、周活持续 4 周、人均问数 ≥3 次/周、报告节省时间 ≥60%、失败问题闭环率 ≥80%。这些指标是产品是否真正被使用的判断标准，不是模型跑分的替代品。", size=9.5)

    # 6. Reflection & transfer
    _heading(doc, "06 复盘、局限与跨行业迁移")
    _body(doc, "这个项目最大的收获不是‘做了一个 AI 工具’，而是理解了 AI 落地真正的难点在数据口径、验证机制和业务采纳，不在模型调用。")
    _body(doc, "局限：公开数据、模拟日历、金额归一化；没有获客成本、资金成本和真实利润，不能计算 CAC/ROI/净利润；installments 的 DPD 与 TARGET 口径不同，不能混用；评分卡只做分层，不直接授信。")
    _body(doc, "如果继续做，我会优先补三件事：接入 POS/信用卡/征信表，做更完整的在贷余额与额度使用分析；把评测集扩展到 100 题并加入人工复核；用真实试点数据验证采纳率和报告节省时间。")
    _body(doc, "跨行业迁移（回应电商/零售 JD）：", bold=True, color=NAVY_RGB)
    mapping = pd.DataFrame(
        [
            ("进件量", "流量 / 新客数", "获客规模"),
            ("审批通过率", "下单转化率", "流量质量与规则"),
            ("用信率", "支付/复购转化率", "批而不用 vs 加购未支付"),
            ("件均", "客单价", "结构升级"),
            ("复贷率", "复购率", "客户经营"),
            ("风险成本", "退货/履约成本", "经营质量"),
            ("Vintage", "cohort 复购/留存", "同账龄比较"),
        ],
        columns=["消费金融指标", "电商/零售对应指标", "共同的分析逻辑"],
    )
    _table(doc, mapping, widths=[1.7, 2.0, 3.0])
    _body(doc, "本质上，两边都在回答同一个问题：增长来自结构、价格还是效率？哪些增长可持续，哪些只是把风险或成本推后？这套指标体系、归因方法和 AI 工作流可以迁移，但口径必须重新定义。")
    _body(doc, "协作说明：本人负责业务定义、指标口径、分析假设、结论判断与验收；Codex 参与数据管道、分析代码、AI 服务、看板与文档实现。", size=9)

    output = PORTFOLIO_DIR / "消费金融经营分析AI项目_作品集.docx"
    doc.save(output)
    return output


if __name__ == "__main__":
    print(build_portfolio())
