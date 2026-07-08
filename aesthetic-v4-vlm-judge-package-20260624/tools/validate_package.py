#!/usr/bin/env python3
"""Validate the aesthetic-v4 package layout and public naming."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PUBLIC_TOKENS = [
    "bo" + "bo_human",
    "bo" + "bo_low",
    "bo" + "bo_combo",
]
REQUIRED = [
    "README.md",
    "config/aesthetic-v4.env.example",
    "docs/AESTHETIC_V4_WORKFLOW.md",
    "input_html/sample_aesthetic_v4_dashboard.html",
    ".gitignore",
    "pipeline/run_aesthetic_v4.sh",
    "pipeline/package.json",
    "pipeline/scripts/build_html_manifest.py",
    "pipeline/scripts/build_aesthetic_v4_report.py",
    "pipeline/scripts/build_manual_qc.py",
    "pipeline/scripts/compare_aesthetic_v4_runs.py",
    "pipeline/scripts/codex_rubric_judge.py",
    "pipeline/scripts/evaluate_aesthetic_v4_benchmark.py",
    "pipeline/scripts/export_clean_html_score_json.py",
    "pipeline/scripts/packy_rubric_judge.py",
    "pipeline/scripts/pangu_rubric_judge.py",
    "pipeline/scripts/score_images.py",
    "pipeline/scripts/validate_clean_json.py",
    "pipeline/scripts/render_screenshots.mjs",
    "tools/build_handoff_zip.py",
    "runs/aesthetic-v4/report.html",
    "runs/aesthetic-v4/scores.jsonl",
]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        return fail("missing required files: " + ", ".join(missing))

    forbidden: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name.startswith("._"):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".jsonl", ".html", ".sh", ".txt", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits = [token for token in FORBIDDEN_PUBLIC_TOKENS if token in text]
        if hits:
            forbidden.append(f"{path.relative_to(ROOT)} ({', '.join(hits)})")
    if forbidden:
        return fail("forbidden public token found in: " + ", ".join(forbidden))

    env_text = (ROOT / "config/aesthetic-v4.env.example").read_text(encoding="utf-8")
    if "AESTHETIC_V4_MODEL_PROVIDER=pangu" not in env_text:
        return fail("env example must default to Pangu provider")
    if "PANGU_BASE_URL=http://43.139.21.243:4000" not in env_text:
        return fail("env example must use the Pangu gateway base URL")
    if "PANGU_JUDGE_MODEL=claude-opus-4-7-thinking" not in env_text:
        return fail("env example must default Pangu to Claude 4.7")
    if "PANGU_JUDGE_OUTPUT_MODE=full" not in env_text:
        return fail("env example must default to full output mode")
    for line in env_text.splitlines():
        if line.startswith(("PACKY_API_KEY=", "PANGU_API_KEY=")) and not line.strip().endswith("="):
            return fail("env example must not contain a real API key")

    prompt_path = ROOT / "pipeline/scripts/codex_rubric_judge.py"
    spec = importlib.util.spec_from_file_location("codex_rubric_judge", prompt_path)
    if spec is None or spec.loader is None:
        return fail("cannot load prompt module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = module.build_prompt(
        {
            "rubric_version": "aesthetic_static_v1",
            "image": {"sample_id": "validate", "viewport": "desktop", "width": 1440, "height": 900},
        },
        "aesthetic-v4",
    )
    if "aesthetic-v4" not in prompt or any(token in prompt.lower() for token in FORBIDDEN_PUBLIC_TOKENS):
        return fail("prompt public naming validation failed")

    print("OK: aesthetic-v4 package validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
