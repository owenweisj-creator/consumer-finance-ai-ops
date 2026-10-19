from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_SAMPLE = ROOT / "data" / "sample"
OUTPUTS = ROOT / "outputs"
DASHBOARD_DIR = OUTPUTS / "dashboard"
EXCEL_DIR = OUTPUTS / "excel"
REPORTS_DIR = OUTPUTS / "reports"
RESUME_DIR = OUTPUTS / "resume"
PORTFOLIO_DIR = OUTPUTS / "portfolio"
KNOWLEDGE_DIR = ROOT / "knowledge"
PROMPTS_DIR = ROOT / "prompts"
EVAL_DIR = ROOT / "eval"

DB_PATH = DATA_PROCESSED / "consumer_finance.duckdb"

# All Home Credit DAYS_* fields are relative to the application date.
# We map them onto a synthetic business calendar anchored at the latest
# complete month before this project started.
ANCHOR_DATE = date(2026, 9, 30)

load_dotenv(ROOT / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def ensure_dirs() -> None:
    for path in (
        DATA_RAW,
        DATA_PROCESSED,
        DATA_SAMPLE,
        DASHBOARD_DIR,
        EXCEL_DIR,
        REPORTS_DIR,
        RESUME_DIR,
        PORTFOLIO_DIR,
        KNOWLEDGE_DIR,
        EVAL_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
