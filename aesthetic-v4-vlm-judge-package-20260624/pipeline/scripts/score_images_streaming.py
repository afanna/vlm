#!/usr/bin/env python3
"""Streaming variant of score_images.py.

Writes each completed record to the output JSONL immediately so long jobs can
be monitored and resumed.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import score_images


def existing_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for record in score_images.read_jsonl(path):
        value = record.get("id")
        if isinstance(value, str):
            ids.add(value)
    return ids


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--anchors", default="anchors/anchors.jsonl")
    parser.add_argument("--backend", default=os.environ.get("AESTHETIC_JUDGE_BACKEND", "mock"))
    parser.add_argument("--judge-command", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--aggregate-strategy", choices=["mean", "min"], default="mean")
    parser.add_argument(
        "--viewport-selection",
        choices=score_images.VIEWPORT_SELECTION_CHOICES,
        default="auto",
        help=(
            "auto scores one canonical screenshot inferred from record/query context; "
            "all preserves legacy multi-view scoring."
        ),
    )
    parser.add_argument(
        "--adaptive-viewports",
        choices=score_images.ADAPTIVE_VIEWPORTS_CHOICES,
        default=os.environ.get("AESTHETIC_V4_ADAPTIVE_VIEWPORTS", "auto"),
    )
    parser.add_argument(
        "--score-breakdown",
        choices=score_images.SCORE_BREAKDOWN_CHOICES,
        default=os.environ.get("AESTHETIC_V4_SCORE_BREAKDOWN", "on"),
    )
    parser.add_argument(
        "--designer-review",
        choices=score_images.DESIGNER_REVIEW_CHOICES,
        default=os.environ.get("AESTHETIC_V4_DESIGNER_REVIEW", "off"),
    )
    parser.add_argument(
        "--formal-report",
        action="store_true",
        default=os.environ.get("AESTHETIC_V4_FORMAL_REPORT", "0") == "1",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    quality_config = score_images.resolve_quality_config(args)

    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    out_path = Path(args.out)
    input_records = score_images.load_input_records(Path(args.input))
    if args.limit > 0:
        input_records = input_records[: args.limit]
    if args.resume:
        done = existing_ids(out_path)
        input_records = [record for record in input_records if str(record.get("id")) not in done]
    anchors = score_images.read_jsonl(Path(args.anchors))
    cache = score_images.load_cache(Path(args.cache))

    completed = 0
    scored = 0
    if args.workers <= 1:
        for record in input_records:
            result = score_images.score_record(record, args, anchors, cache)
            append_record(out_path, result)
            completed += 1
            if result.get("status") == "scored":
                scored += 1
            print(
                json.dumps(
                    {
                        "id": result.get("id"),
                        "status": result.get("status"),
                        "final_score": result.get("final_score"),
                        "target_viewport": result.get("target_viewport"),
                        "scored_viewports": result.get("scored_viewports"),
                        "adaptive_viewports": result.get("adaptive_viewports"),
                        "completed": completed,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(score_images.score_record, record, args, anchors, cache): record for record in input_records}
            for future in as_completed(futures):
                record = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "schema_version": 1,
                        "rubric_version": score_images.RUBRIC_VERSION,
                        "id": record.get("id"),
                        "source": record.get("source"),
                        "source_key": record.get("source_key"),
                        "input_path": record.get("input_path"),
                        "sample_relpath": record.get("sample_relpath"),
                        "sample_metadata": record.get("sample_metadata") or {},
                        "status": "failed",
                        "final_score": None,
                        "rationale": f"Unhandled worker error: {exc}",
                        "errors": [{"error": str(exc)}],
                    }
                append_record(out_path, result)
                completed += 1
                if result.get("status") == "scored":
                    scored += 1
                print(
                    json.dumps(
                        {
                            "id": result.get("id"),
                            "status": result.get("status"),
                            "final_score": result.get("final_score"),
                            "target_viewport": result.get("target_viewport"),
                            "scored_viewports": result.get("scored_viewports"),
                            "adaptive_viewports": result.get("adaptive_viewports"),
                            "completed": completed,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    summary = {
        "out": str(out_path),
        "records_attempted": len(input_records),
        "completed": completed,
        "scored": scored,
        "backend": args.backend,
        "workers": args.workers,
        "viewport_selection": args.viewport_selection,
        "quality_config": quality_config,
        "formal_report": bool(args.formal_report),
        "occlusion_overlap_check": score_images.OCCLUSION_OVERLAP_CHECK,
        "resume": args.resume,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary | {"summary": str(summary_path)}, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
