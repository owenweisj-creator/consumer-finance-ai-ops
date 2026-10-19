from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.ai.agent import AnalyticsCopilot
from src.ai.llm import LLMError
from src.config import DB_PATH, DEEPSEEK_API_KEY
from src.reports.build_reports import build_monthly_report, build_special_report, build_weekly_report

app = FastAPI(title="Consumer Finance AI Copilot", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    session_id: str | None = None


class ReportRequest(BaseModel):
    type: str = Field(pattern="^(weekly|monthly|special)$")
    period: str = "2026-09"
    start: str | None = None
    end: str | None = None


@lru_cache(maxsize=1)
def get_copilot() -> AnalyticsCopilot:
    return AnalyticsCopilot()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if DB_PATH.exists() else "warehouse_missing",
        "warehouse": str(DB_PATH),
        "llm_key_configured": bool(DEEPSEEK_API_KEY),
    }


@app.post("/api/ask")
def ask(payload: AskRequest) -> dict[str, Any]:
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY is not configured")
    try:
        return get_copilot().ask(payload.question)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/report")
def report(payload: ReportRequest) -> dict[str, Any]:
    if payload.type == "monthly":
        result = build_monthly_report(payload.period)
    elif payload.type == "weekly":
        from datetime import date

        result = build_weekly_report(date.fromisoformat(payload.start or "2026-09-21"), date.fromisoformat(payload.end or "2026-09-27"))
    else:
        result = build_special_report(payload.period)
    return {key: str(value) for key, value in result.items() if value}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>经营分析 AI Copilot</title>
<style>
body{margin:0;font-family:"Microsoft YaHei",sans-serif;background:#F4F6F8;color:#1F2937}
.wrap{max-width:980px;margin:0 auto;padding:34px 20px 60px}
h1{color:#173B57;font-size:24px;margin:0 0 6px}
.sub{color:#6B7280;font-size:12px;margin-bottom:24px}
.box{background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:18px}
textarea{width:100%;min-height:78px;border:1px solid #D1D5DB;border-radius:8px;padding:12px;font-size:14px;font-family:inherit;resize:vertical}
button{margin-top:10px;background:#0E7C86;color:#fff;border:0;border-radius:8px;padding:10px 20px;font-size:14px;cursor:pointer}
button:disabled{background:#9CA3AF}
.answer{margin-top:18px;white-space:pre-wrap;line-height:1.7;font-size:14px}
.sql{background:#F8FAFC;border:1px solid #E5E7EB;border-radius:8px;padding:12px;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;margin-top:12px;color:#334155}
table{border-collapse:collapse;width:100%;margin-top:14px;font-size:12px}
th,td{border-bottom:1px solid #EEF1F4;padding:7px 8px;text-align:left}
th{background:#F1F5F9;color:#173B57}
.hint{color:#6B7280;font-size:11px;margin-top:8px}
</style>
</head>
<body>
<div class="wrap">
  <h1>消费金融经营分析 AI Copilot</h1>
  <div class="sub">问数 → 只读 SQL → 结果校验 → 经营解释。示例：最近 6 个月每月的审批通过率和用信率是多少？</div>
  <div class="box">
    <textarea id="q">最近 6 个月每月的审批通过率和用信率是多少？</textarea>
    <button id="btn" onclick="ask()">开始分析</button>
    <div class="hint">模型只负责生成 SQL 与解释；所有数字来自本地数据仓库。危险 SQL 会被拦截。</div>
    <div id="out"></div>
  </div>
</div>
<script>
async function ask(){
  const btn=document.getElementById('btn'); btn.disabled=true; btn.textContent='分析中...';
  const out=document.getElementById('out'); out.innerHTML='';
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:document.getElementById('q').value})});
    const d=await r.json();
    if(!r.ok){out.innerHTML='<div class="answer">错误：'+(d.detail||r.status)+'</div>';return}
    let html='<div class="answer">'+escapeHtml(d.answer||'')+'</div>';
    if(d.sql){html+='<div class="sql">'+escapeHtml(d.sql)+'</div>'}
    if(d.data&&d.data.length){
      const cols=Object.keys(d.data[0]);
      html+='<table><thead><tr>'+cols.map(c=>'<th>'+escapeHtml(c)+'</th>').join('')+'</tr></thead><tbody>';
      d.data.slice(0,12).forEach(row=>{html+='<tr>'+cols.map(c=>'<td>'+escapeHtml(String(row[c]??''))+'</td>').join('')+'</tr>'});
      html+='</tbody></table>';
    }
    if(d.citations&&d.citations.length){html+='<div class="hint">依据：'+d.citations.map(escapeHtml).join('；')+'</div>'}
    out.innerHTML=html;
  }catch(e){out.innerHTML='<div class="answer">请求失败：'+escapeHtml(String(e))+'</div>'}
  finally{btn.disabled=false;btn.textContent='开始分析'}
}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
</script>
</body>
</html>
"""
