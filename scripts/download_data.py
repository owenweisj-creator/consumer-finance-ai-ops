from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from src.config import DATA_RAW, ensure_dirs

BASE = "https://huggingface.co/datasets/minhSpaceX/home_credit/resolve/main"
FILES = {
    "HomeCredit_columns_description.csv": 37_383,
    "application_train.csv": 166_133_370,
    "previous_application.csv": 404_973_293,
    "installments_payments.csv": 723_118_349,
    "POS_CASH_balance.csv": 392_703_158,
    "credit_card_balance.csv": 424_582_605,
    "bureau.csv": 170_016_717,
    "bureau_balance.csv": 375_592_889,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024 * 8), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        import requests

        with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "codex"}) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024 * 8):
                    if chunk:
                        handle.write(chunk)
        return
    except Exception as exc:  # noqa: BLE001
        print(f"requests failed ({exc}); falling back to PowerShell")
    if sys.platform != "win32":
        raise RuntimeError("Download failed and PowerShell fallback is only available on Windows")
    command = (
        "$ErrorActionPreference='Stop'; "
        f"Invoke-WebRequest -Uri '{url}' -OutFile '{destination}' -Headers @{{'User-Agent'='codex'}} -TimeoutSec 1200"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True)


def main() -> None:
    ensure_dirs()
    manifest = {"source": BASE, "files": {}}
    for filename, expected_size in FILES.items():
        path = DATA_RAW / filename
        if path.exists() and path.stat().st_size == expected_size:
            print(f"skip {filename}")
        else:
            print(f"download {filename} ({expected_size / 1024 / 1024:.1f} MB)")
            download(f"{BASE}/{filename}", path)
        actual = path.stat().st_size
        if actual != expected_size:
            raise RuntimeError(f"Size mismatch for {filename}: expected {expected_size}, got {actual}")
        manifest["files"][filename] = {"bytes": actual, "sha256": sha256(path)}
    manifest_path = DATA_RAW / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
