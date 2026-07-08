#!/usr/bin/env python3
"""Build the aesthetic-v4 handoff zip without private local secrets."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = Path("/Volumes/TU820/aesthetic/outputs")
TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".txt",
}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
]

ALLOWED_ACCEPTANCE_DIRS = {
    "benchmark_claude47_final_default",
    "occlusion_claude47_final_default",
    "occlusion_inputs",
}
ALLOWED_ACCEPTANCE_FILES = {
    "DELIVERY_REVIEW.md",
    "occlusion_claude47_final_default_summary.json",
}
ALLOWED_RUN_DIRS = {
    "final_mock_validation_default_aesthetic_v4",
    "final_smoke_pangu_claude47_default_aesthetic_v4",
    "packy_gpt55_q10252_score_only",
    "packy_gpt55_q10252_smoke",
    "packy_gpt55_q10903_occlusion_smoke",
}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if path.name.startswith("._"):
        return True
    if path.name in {".DS_Store", "aesthetic-v4.env"}:
        return True
    if "__pycache__" in parts or "node_modules" in parts:
        return True
    if path.suffix in {".pyc", ".zip"}:
        return True
    if rel.parts and rel.parts[0] == "acceptance":
        if len(rel.parts) == 2:
            return rel.parts[1] not in ALLOWED_ACCEPTANCE_FILES
        return rel.parts[1] not in ALLOWED_ACCEPTANCE_DIRS
    if rel.parts and rel.parts[0] == "runs":
        return len(rel.parts) < 2 or rel.parts[1] not in ALLOWED_RUN_DIRS
    return False


def looks_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name.endswith(".env.example")


def assert_no_secret(path: Path) -> None:
    if not looks_text(path):
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"(?i)^\s*(?:packy|pangu|openai|anthropic)_api_key\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            if value and value not in {"...", "<...>", "<redacted>", "REDACTED", "sk-REDACTED"}:
                raise ValueError(f"possible API key in {path.relative_to(ROOT)}:{line_no}")
    for pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            raise ValueError(f"possible secret in {path.relative_to(ROOT)}: {match.group(0)[:24]}...")


def build_zip(out: Path) -> dict[str, object]:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    written = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or should_skip(path):
                continue
            assert_no_secret(path)
            arcname = Path(ROOT.name) / path.relative_to(ROOT)
            zf.write(path, arcname.as_posix())
            written += 1

    return {"zip": str(out), "files": written, "bytes": out.stat().st_size}


def parse_args() -> argparse.Namespace:
    today = dt.datetime.now().strftime("%Y%m%d")
    default_out = DEFAULT_OUT_DIR / f"aesthetic-v4-pangu-claude47-handoff-{today}.zip"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=default_out)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = build_zip(args.out.resolve())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
