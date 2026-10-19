from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "data", "logs", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".env"}
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"),
]


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
        return [ROOT / line for line in output.splitlines() if line.strip()]
    except Exception:
        files = []
        for path in ROOT.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                files.append(path)
        return files


def main() -> int:
    findings = []
    for path in tracked_files():
        if path.name in SKIP_FILES or not path.exists():
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
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                findings.append(f"{path.relative_to(ROOT)}: {match.group(0)[:12]}...")
    if findings:
        print("Potential secrets found:")
        print("\n".join(findings))
        return 1
    print("No secret patterns found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

