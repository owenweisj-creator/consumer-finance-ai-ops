param(
    [string]$RepoName = "consumer-finance-ai-ops",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$gh = Join-Path $root "tools\bin\gh.exe"
if (-not (Test-Path $gh)) { throw "GitHub CLI not found: $gh" }

& $gh auth status
$repoFull = (& $gh repo view --json nameWithOwner -q .nameWithOwner 2>$null)
if (-not $repoFull) {
    $visibility = "--public"
    if ($SkipPush) {
        & $gh repo create $RepoName $visibility --source $root --remote origin
    } else {
        & $gh repo create $RepoName $visibility --source $root --remote origin --push `
            --description "Consumer finance operating analytics + AI Copilot, built from public Home Credit data"
    }
    $repoFull = (& $gh repo view --json nameWithOwner -q .nameWithOwner)
}
Write-Output "Repository: $repoFull"

$labels = @(
    @("s1-data", "0E7C86", "Data warehouse and metric definitions"),
    @("s2-analysis", "173B57", "Operating analysis and risk segmentation"),
    @("s3-ai", "D97706", "AI Copilot, NL2SQL, RAG and evaluation"),
    @("s4-product", "7C3AED", "PRD, UAT, training and adoption"),
    @("s5-career", "B42318", "Resume, portfolio and interview"),
    @("bug", "D73A4A", "Something is not working"),
    @("docs", "0075CA", "Documentation"),
    @("experiment", "FBCA04", "Experiment or hypothesis")
)
foreach ($label in $labels) {
    & $gh label create $label[0] --color $label[1] --description $label[2] --force | Out-Null
}

$milestones = @(
    "S1 数据与业务建模",
    "S2 经营分析与风险分层",
    "S3 AI Copilot",
    "S4 产品化与落地",
    "S5 简历与面试"
)
$existingMilestones = (& $gh api "repos/$repoFull/milestones?state=all&per_page=100" | ConvertFrom-Json).title
foreach ($title in $milestones) {
    if ($existingMilestones -notcontains $title) {
        & $gh api "repos/$repoFull/milestones" -f title="$title" -f state="open" | Out-Null
    }
}

function Ensure-Issue {
    param([string]$Title, [string]$Body, [string]$Milestone, [string[]]$Labels)
    $existing = (& $gh issue list --state all --search "$Title in:title" --json number | ConvertFrom-Json)
    if ($existing.Count -gt 0) {
        Write-Output "SKIP issue: $Title"
        return
    }
    $labelArg = $Labels -join ","
    & $gh issue create --title $Title --body $Body --milestone $Milestone --label $labelArg | Out-Null
    Write-Output "CREATED issue: $Title"
}

$issues = @(
    @("S1-01 下载并校验 Home Credit 数据", "验收标准：7 张表文件完整，记录大小与 SHA256；`data/manifest.json` 可复现。", "S1 数据与业务建模", @("s1-data")),
    @("S1-02 构建 DuckDB 星型模型", "验收标准：维度/事实表建成，主键唯一，核心指标可查询。", "S1 数据与业务建模", @("s1-data")),
    @("S1-03 定义指标口径与数据字典", "验收标准：13 个核心指标有公式、分母、边界和面试话术。", "S1 数据与业务建模", @("s1-data", "docs")),
    @("S1-04 输出数据质量报告", "验收标准：行数、缺失率、重复键、日期范围、状态分布可核查。", "S1 数据与业务建模", @("s1-data", "docs")),
    @("S2-01 审批漏斗与渠道结构分析", "验收标准：进件/通过/用信可加总；渠道结构效应可复算。", "S2 经营分析与风险分层", @("s2-analysis")),
    @("S2-02 Vintage 与 DPD 口径", "验收标准：cohort × MOB 矩阵；累计 DPD30/60/90 口径明确。", "S2 经营分析与风险分层", @("s2-analysis")),
    @("S2-03 客户价值 × 风险分层", "验收标准：九宫格客户数、不良率、平均额度可复算。", "S2 经营分析与风险分层", @("s2-analysis")),
    @("S2-04 WOE/IV 风险评分卡", "验收标准：AUC、KS、分箱表、PD 校准结果完整。", "S2 经营分析与风险分层", @("s2-analysis")),
    @("S2-05 异常检测与归因", "验收标准：稳健 z 分数异常清单；结构/比率分解可解释。", "S2 经营分析与风险分层", @("s2-analysis", "experiment")),
    @("S3-01 语义层与只读 NL2SQL", "验收标准：YAML 语义层；只允许 SELECT 和 mart.v_*；200 行上限。", "S3 AI Copilot", @("s3-ai")),
    @("S3-02 RAG 知识库与拒答", "验收标准：指标/规则/SOP 可检索；回答带引用；无依据拒答。", "S3 AI Copilot", @("s3-ai")),
    @("S3-03 报告 Agent 数字校验", "验收标准：数字由 Python 注入；一致性校验失败自动回退模板。", "S3 AI Copilot", @("s3-ai")),
    @("S3-04 42 题评测与 Prompt v1/v2", "验收标准：SQL 准确率、知识准确率、拒答率、延迟、token 可对比。", "S3 AI Copilot", @("s3-ai", "experiment")),
    @("S3-05 安全护栏与危险 SQL 拦截", "验收标准：DELETE/UPDATE/DROP/raw/多语句等 12 类输入全部拦截。", "S3 AI Copilot", @("s3-ai", "bug")),
    @("S4-01 HTML 经营看板", "验收标准：六个模块；离线打开；筛选与数字和仓库一致。", "S4 产品化与落地", @("s4-product")),
    @("S4-02 Excel 经营分析工作簿", "验收标准：8 张表；原生图表；指标口径页；无损坏。", "S4 产品化与落地", @("s4-product")),
    @("S4-03 周报/月报/专项报告", "验收标准：数字可追溯；月报 DOCX/PDF 渲染正常。", "S4 产品化与落地", @("s4-product")),
    @("S4-04 PRD/UAT/培训手册", "验收标准：需求池、30 条 UAT、60 分钟培训大纲、采纳指标齐全。", "S4 产品化与落地", @("s4-product", "docs")),
    @("S4-05 AI 行业简报与创新提案", "验收标准：5 个趋势、3 个提案，每个有场景、指标、风险。", "S4 产品化与落地", @("s4-product", "docs")),
    @("S5-01 一页简历与作品集", "验收标准：简历一页；公开仓库不含手机/邮箱/照片；作品集 6–8 页。", "S5 简历与面试", @("s5-career", "docs")),
    @("S5-02 项目讲解稿与模拟面试", "验收标准：5 分钟讲解稿；20 题追问答案；完成一次模拟面试。", "S5 简历与面试", @("s5-career"))
)

foreach ($issue in $issues) {
    Ensure-Issue -Title $issue[0] -Body $issue[1] -Milestone $issue[2] -Labels $issue[3]
}

Write-Output "GitHub setup complete for $repoFull"
