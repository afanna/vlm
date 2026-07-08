#!/usr/bin/env python3
"""Validate reader-facing aesthetic-v4 clean JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any


FORBIDDEN_KEYS = {
    "score_8",
    "axis_score_8",
    "final_score_8",
    "weighted_total_8",
    "weighted_contribution_8",
    "weighted_score_from_axis_scores",
    "weighted_score_from_axis_scores_100",
    "occlusion_weighted_loss_from_max",
    "weighted_contribution",
    "weighted_loss_from_max",
    "final_score_100",
    "weighted_total_100",
    "score_100_rounded",
}


def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(walk_keys(child))
    elif isinstance(value, list):
        for item in value:
            keys.extend(walk_keys(item))
    return keys


def read_records(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.glob("*.json") if item.name != "index.json")
    if path.name == "index.json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        paths = []
        for row in payload.get("records") or []:
            if isinstance(row, dict) and row.get("json_path"):
                paths.append(Path(str(row["json_path"])))
        return paths
    return [path]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = walk_keys(payload)
    forbidden = sorted(key for key in set(keys) if key in FORBIDDEN_KEYS or key.endswith("_8"))
    if forbidden:
        errors.append(f"forbidden keys: {', '.join(forbidden)}")
    if "aesthetic_rubric" not in payload or not isinstance(payload["aesthetic_rubric"], list):
        errors.append("missing aesthetic_rubric")
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    if "score_100" not in score:
        errors.append("missing score.score_100")
    axis = score.get("axis_breakdown") if isinstance(score.get("axis_breakdown"), list) else []
    if axis:
        total = sum(
            Decimal(str(item.get("weighted_contribution_100")))
            for item in axis
            if isinstance(item, dict) and item.get("weighted_contribution_100") is not None
        )
        expected = Decimal(str(score.get("score_100")))
        if abs(total - expected) > Decimal("0.01"):
            errors.append(f"score_100 mismatch: {expected} vs axis sum {total}")
    if "rationale" in payload and keys.count("rationale") != 1:
        errors.append(f"duplicated rationale keys: {keys.count('rationale')}")
    occlusion = payload.get("occlusion") if isinstance(payload.get("occlusion"), dict) else {}
    for required in ("detected", "status", "types", "affected_axes", "findings", "score_impact"):
        if required not in occlusion:
            errors.append(f"missing occlusion.{required}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Clean JSON file, index.json, or directory.")
    args = parser.parse_args()

    paths = read_records(Path(args.path))
    failures: dict[str, list[str]] = {}
    for path in paths:
        errors = validate(path)
        if errors:
            failures[str(path)] = errors

    summary = {"records": len(paths), "failed": len(failures), "failures": failures}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
