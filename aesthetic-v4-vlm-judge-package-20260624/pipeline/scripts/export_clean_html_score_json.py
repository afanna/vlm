#!/usr/bin/env python3
"""Export one clean review JSON per scored HTML/sample.

The raw score_images.py output is intentionally verbose and preserves nested
per-view payloads. This exporter creates a reader-facing JSON shape with no
duplicated rationale text while keeping score weights and occlusion evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from score_images import AESTHETIC_RUBRIC
except ModuleNotFoundError:
    from scripts.score_images import AESTHETIC_RUBRIC


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def round_3(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def score_100(score: Any) -> float | None:
    if score is None:
        return None
    return round_3(Decimal(str(score)) * Decimal("12.5"))


def qid_for(record: dict[str, Any]) -> str:
    candidates = [
        record.get("id"),
        record.get("sample_relpath"),
        record.get("input_path"),
        (record.get("sample_metadata") or {}).get("html_path"),
        (record.get("sample_metadata") or {}).get("source_id"),
    ]
    for value in candidates:
        if not value:
            continue
        match = re.search(r"q\d+", str(value), flags=re.I)
        if match:
            return match.group(0).lower()
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(record.get("id") or "sample")).strip("_")
    return safe or "sample"


def html_path_for(record: dict[str, Any]) -> str | None:
    metadata = record.get("sample_metadata") if isinstance(record.get("sample_metadata"), dict) else {}
    html_path = metadata.get("html_path")
    if html_path:
        return str(html_path)
    input_path = record.get("input_path")
    if isinstance(input_path, str) and input_path.lower().endswith((".html", ".htm")):
        return input_path
    return None


def view_image(view: dict[str, Any]) -> dict[str, Any]:
    image = view.get("image") if isinstance(view.get("image"), dict) else {}
    return {
        "path": image.get("path"),
        "width": image.get("width"),
        "height": image.get("height"),
        "sha256": image.get("sha256"),
    }


def aggregate_axis_breakdown(record: dict[str, Any]) -> list[dict[str, Any]]:
    aesthetics = (record.get("extra_info_scores") or {}).get("aesthetics") or {}
    axis_scores = aesthetics.get("axis_scores") if isinstance(aesthetics.get("axis_scores"), dict) else {}
    score_breakdown = record.get("score_breakdown") if isinstance(record.get("score_breakdown"), dict) else {}
    weights = score_breakdown.get("rubric_weights") if isinstance(score_breakdown.get("rubric_weights"), dict) else {}
    rows: list[dict[str, Any]] = []
    for axis, score in axis_scores.items():
        weight = weights.get(axis)
        weighted_contribution_8 = (
            round_3(Decimal(str(score)) * Decimal(str(weight)))
            if score is not None and weight is not None
            else None
        )
        rows.append(
            {
                "axis": axis,
                "axis_score_100": score_100(score),
                "weight": weight,
                "weighted_contribution_100": score_100(weighted_contribution_8),
            }
        )
    return sorted(rows, key=lambda row: str(row["axis"]))


def clean_occlusion_impact(impact: Any) -> dict[str, Any]:
    if not isinstance(impact, dict):
        return {}
    affected_axes = []
    for item in impact.get("affected_axes") if isinstance(impact.get("affected_axes"), list) else []:
        if not isinstance(item, dict):
            continue
        affected_axes.append(
            {
                "axis": item.get("axis"),
                "axis_score_100": score_100(item.get("score")),
                "weight": item.get("weight"),
                "weighted_contribution_100": score_100(item.get("weighted_contribution")),
                "weighted_loss_from_full_score_100": score_100(item.get("weighted_loss_from_max")),
                "severity": item.get("severity"),
                "finding_types": item.get("finding_types") if isinstance(item.get("finding_types"), list) else [],
            }
        )
    affected_contribution_100 = round_3(
        sum(
            Decimal(str(item["weighted_contribution_100"]))
            for item in affected_axes
            if item.get("weighted_contribution_100") is not None
        )
    )
    affected_loss_100 = round_3(
        sum(
            Decimal(str(item["weighted_loss_from_full_score_100"]))
            for item in affected_axes
            if item.get("weighted_loss_from_full_score_100") is not None
        )
    )
    return {
        "scoring_rule": "固定权重不变；遮挡只降低 affected_axes 对应轴分，其他轴按原标准评分；总分为所有轴 weighted_contribution_100 相加。",
        "affected_axis_breakdown": affected_axes,
        "affected_axes_weighted_contribution_100": affected_contribution_100,
        "affected_axes_weighted_loss_from_full_score_100": affected_loss_100,
    }


def clean_views(record: dict[str, Any]) -> list[dict[str, Any]]:
    views = record.get("views") if isinstance(record.get("views"), dict) else {}
    cleaned: list[dict[str, Any]] = []
    for viewport, view in views.items():
        if not isinstance(view, dict):
            continue
        item = {
            "viewport": viewport,
            "score_100": score_100(view.get("score")),
            "image": view_image(view),
            "cache_hit": view.get("cache_hit"),
            "elapsed_ms": view.get("elapsed_ms"),
        }
        cleaned.append(item)
    return cleaned


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    aesthetics = (record.get("extra_info_scores") or {}).get("aesthetics") or {}
    sample_metadata = record.get("sample_metadata") if isinstance(record.get("sample_metadata"), dict) else {}
    axis_breakdown = aggregate_axis_breakdown(record)
    weighted_total_100 = (
        round_3(sum(Decimal(str(row["weighted_contribution_100"])) for row in axis_breakdown if row.get("weighted_contribution_100") is not None))
        if axis_breakdown
        else score_100(aesthetics.get("weighted_total"))
    )
    output = {
        "schema_version": 1,
        "id": record.get("id"),
        "qid": qid_for(record),
        "profile": record.get("profile"),
        "rubric_version": record.get("rubric_version"),
        "aesthetic_rubric": AESTHETIC_RUBRIC,
        "source": record.get("source"),
        "source_key": record.get("source_key"),
        "sample_relpath": record.get("sample_relpath"),
        "html_path": html_path_for(record),
        "sample_metadata": sample_metadata,
        "status": record.get("status"),
        "quality_config": record.get("quality_config") or {},
        "score": {
            "score_100": weighted_total_100,
            "aggregate_view": record.get("aggregate_view"),
            "aggregate_formula": record.get("aggregate_formula"),
            "axis_breakdown": axis_breakdown,
        },
        "rationale": record.get("rationale"),
        "occlusion": {
            "check": record.get("occlusion_overlap_check"),
            "detected": record.get("occlusion_overlap_detected"),
            "status": record.get("occlusion_overlap_status"),
            "types": record.get("occlusion_overlap_types") or [],
            "affected_axes": record.get("occlusion_overlap_affected_axes") or [],
            "findings": record.get("occlusion_findings") or [],
            "score_impact": clean_occlusion_impact(record.get("occlusion_score_impact")),
        },
        "views": clean_views(record),
        "links": {
            "html": html_path_for(record),
            "screenshots": [view["image"]["path"] for view in clean_views(record) if view["image"].get("path")],
        },
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", nargs="+", required=True, help="Input scores JSONL files.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--index", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    written: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scores_path in [Path(path) for path in args.scores]:
        for record in read_jsonl(scores_path):
            clean = clean_record(record)
            key = clean.get("html_path") or clean.get("id") or clean.get("qid")
            if str(key) in seen:
                continue
            seen.add(str(key))
            qid = str(clean["qid"])
            out_path = out_dir / f"{qid}.json"
            write_json(out_path, clean)
            written.append(
                {
                    "id": clean.get("id"),
                    "qid": qid,
                    "html_path": clean.get("html_path"),
                    "json_path": str(out_path.resolve()),
                    "score": clean.get("score"),
                    "occlusion": {
                        "detected": clean["occlusion"].get("detected"),
                        "status": clean["occlusion"].get("status"),
                        "types": clean["occlusion"].get("types"),
                        "affected_axes": clean["occlusion"].get("affected_axes"),
                    },
                    "screenshots": clean["links"].get("screenshots") or [],
                }
            )

    index = {
        "schema_version": 1,
        "record_count": len(written),
        "records": sorted(written, key=lambda row: str(row["qid"])),
    }
    index_path = Path(args.index) if args.index else out_dir / "index.json"
    write_json(index_path, index)
    print(json.dumps({"out_dir": str(out_dir.resolve()), "index": str(index_path.resolve()), "records": len(written)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
