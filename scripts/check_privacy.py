from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
        return [ROOT / line for line in output.splitlines() if line.strip()]
    except Exception:
        return [path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts]


def main() -> int:
    findings = []
    for path in tracked_files():
        if not path.exists():
            continue
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".pdf",
            ".docx",
            ".xlsx",
            ".duckdb",
            ".parquet",
            ".exe",
            ".dll",
            ".zip",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in PHONE.finditer(text):
            findings.append(f"{path.relative_to(ROOT)}: phone-like value")
        for match in EMAIL.finditer(text):
            findings.append(f"{path.relative_to(ROOT)}: email {match.group(0)}")
    if findings:
        print("Privacy scan findings:")
        print("\n".join(findings))
        return 1
    print("No privacy issues found in tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

