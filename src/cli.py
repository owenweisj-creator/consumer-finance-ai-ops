from __future__ import annotations

import argparse
import json
from datetime import date

from src.ai.agent import AnalyticsCopilot, result_to_json
from src.dashboard.build_dashboard import build_dashboard
from src.reports.build_excel import build_excel
from src.reports.build_reports import build_monthly_report, build_special_report, build_weekly_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Consumer finance AI copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Ask a business question")
    ask.add_argument("question")
    ask.add_argument("--knowledge", action="store_true", help="Prefer knowledge-base answer")

    report = sub.add_parser("report", help="Generate a report")
    report.add_argument("--type", choices=["weekly", "monthly", "special"], default="monthly")
    report.add_argument("--period", default="2026-09")
    report.add_argument("--start", default="2026-09-21")
    report.add_argument("--end", default="2026-09-27")

    sub.add_parser("dashboard", help="Build the HTML dashboard")
    sub.add_parser("excel", help="Build the Excel workbook")

    args = parser.parse_args()
    if args.command == "ask":
        copilot = AnalyticsCopilot()
        print(result_to_json(copilot.ask(args.question, prefer_knowledge=args.knowledge)))
    elif args.command == "report":
        if args.type == "monthly":
            print(json.dumps({k: str(v) for k, v in build_monthly_report(args.period).items()}, ensure_ascii=False, indent=2))
        elif args.type == "weekly":
            print(json.dumps({k: str(v) for k, v in build_weekly_report(date.fromisoformat(args.start), date.fromisoformat(args.end)).items()}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({k: str(v) for k, v in build_special_report(args.period).items()}, ensure_ascii=False, indent=2))
    elif args.command == "dashboard":
        print(build_dashboard())
    elif args.command == "excel":
        print(build_excel())


if __name__ == "__main__":
    main()
