# 消费金融经营分析 AI Copilot

> 一个从 0 到 1 的消费金融经营分析项目：把“申请—审批—用信—放款—还款—逾期—复贷”全链路数据，做成可监控、可归因、可问数的 AI Copilot。

**项目负责人**：Owen 魏  
**协作说明**：本人负责业务定义、指标口径、分析假设、结论判断与验收；Codex 作为 AI 协作工具参与数据管道、分析代码、AI 服务、看板、报告与文档实现。

## 这个项目解决什么问题

消费金融公司的经营分析通常面临三个断点：

1. **数据断点**：申请、审批、用信、还款、逾期分散在不同表，口径不统一。
2. **分析断点**：能看到通过率、用信率、不良率，但说不清是“结构变化”还是“同一客群自身变化”。
3. **工具断点**：业务提一个取数需求要等数据团队排期，AI 问数又容易编造字段和数字。

本项目用一套可复现的数据底座 + 语义层 + 只读 NL2SQL + 报告 Agent，把这三个断点串起来。

## 数据来源与边界

- 数据：Home Credit 公开消费金融数据集（`minhSpaceX/home_credit`），包含申请、历史申请审批、分期还款、POS/信用卡账本、征信等多张表。
- 时间：原始 `DAYS_*` 是相对当前申请日的天数，本项目映射到以 **2026-09-30** 为锚点的业务日历，仅用于趋势与 cohort 分析。
- 金额：统一为“万元（归一化）”，仅用于结构和趋势分析，不代表真实人民币规模。
- 风险标签：`TARGET=1` 表示 30+ 天逾期，不等同于核销率或最终损失率。
- 不计算：CAC、ROI、净利润。数据中没有获客成本、资金成本和真实利润。

## 项目结构

```text
consumer-finance-ai-ops/
├── src/
│   ├── etl/build_warehouse.py      # DuckDB 数据仓库与星型模型
│   ├── analytics/                  # 指标、异常、分解、评分卡
│   ├── ai/                         # DeepSeek、NL2SQL、RAG、Agent
│   ├── dashboard/                  # 离线 HTML 看板
│   ├── reports/                    # 报告、Excel、图表
│   ├── app.py                      # FastAPI 问数服务
│   └── cli.py                      # 命令行入口
├── semantic_layer.yml              # 指标、维度、视图、口径
├── knowledge/                      # 指标字典、业务规则、AI 手册（RAG）
├── prompts/                        # Prompt 版本
├── eval/                           # 评测集与结果
├── tests/                          # 单元测试（不调用真实模型）
├── docs/                           # 学习、产品、面试材料
└── outputs/                        # 看板、Excel、报告、简历、作品集
```

## 当前结果

- 数据底座：7 张表、5,800 万+ 行（申请、历史申请、分期还款、POS、信用卡、征信、征信月度）。
- 2026-09 进件量 36,012 笔（环比 +26.2%），审批通过率 22.9%（环比 -6.5pp），用信率 97.9%。
- 审批通过率变化中，结构效应约 -5.39pp、比率效应约 -1.13pp，合计 -6.52pp；主因是低通过率渠道占比上升、高通过率渠道占比下降。
- 审批金额 188,681 万元（+32.1%），但审批件数 -1.8%，增长主要由件均（+30.5%）和期限（+2.31 个月）驱动。
- WOE/IV + 逻辑回归评分卡：AUC 0.726，KS 0.335，五个风险带 PD 与实际不良率基本一致。
- 42 题 AI 评测：SQL 结果准确率 85.3%，知识问答 87.5%，危险 SQL 拦截率 100%，平均延迟约 1.3 秒。
- 单次月报生成 < 1 分钟（本机实测）。
- 19 个单元测试全部通过（含 12 类危险 SQL 拦截）。

## 快速开始

```powershell
# 1. 创建环境
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 下载数据（约 2.7GB，下载脚本会跳过已完成文件）
.\\.venv\\Scripts\\python.exe scripts/download_data.py

# 3. 建仓
.\\.venv\\Scripts\\python.exe -m src.etl.build_warehouse

# 4. 生成看板与 Excel
.\\.venv\\Scripts\\python.exe -m src.cli dashboard
.\\.venv\\Scripts\\python.exe -m src.cli excel

# 5. 生成月报
.\\.venv\\Scripts\\python.exe -m src.cli report --type monthly --period 2026-09

# 6. 启动问数服务
.\\.venv\\Scripts\\python.exe -m uvicorn src.app:app --port 8000
```

打开 `http://127.0.0.1:8000` 进入问数界面，打开 `outputs/dashboard/index.html` 查看离线看板。

## 配置

复制 `.env.example` 为 `.env`，填入本地 DeepSeek Key：

```text
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

`.env` 已在 `.gitignore` 中，不会进入仓库。不要在日志、截图、报告或作品集中暴露 Key。

## AI 设计原则

- **语义层先行**：NL2SQL 只能查 `mart.v_*` 视图，不能访问 `raw`。
- **只读与限流**：只允许 `SELECT`，禁止 DDL/DML、多语句与注释，结果最多 200 行。
- **数字可追溯**：报告中的数字由 Python 计算后注入，模型只负责解释和建议。
- **无依据就拒答**：RAG 检索不到依据时明确拒答，不编造口径。
- **评测驱动**：Prompt v1/v2 用同一套 42 题评测集对比执行准确率、拒答正确率、延迟与成本。


## 免责声明

本项目为个人学习与分析作品，不代表任何公司的真实经营数据或授信政策。AI 输出仅作辅助决策，发布前需人工复核。

