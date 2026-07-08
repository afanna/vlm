#!/usr/bin/env python3
"""Export score_images JSONL output to the visual sampling gallery CSV format."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


AXIS_COLUMNS = [
    "visual_impact_originality",
    "composition_hierarchy",
    "typography",
    "color_material",
    "detail_finish",
    "basic_usability",
]

BUCKETS = [
    (0, 10, "[0,10)", "bucket_00_10.csv"),
    (10, 20, "[10,20)", "bucket_10_20.csv"),
    (20, 30, "[20,30)", "bucket_20_30.csv"),
    (30, 40, "[30,40)", "bucket_30_40.csv"),
    (40, 50, "[40,50)", "bucket_40_50.csv"),
    (50, 60, "[50,60)", "bucket_50_60.csv"),
    (60, 70, "[60,70)", "bucket_60_70.csv"),
    (70, 80, "[70,80)", "bucket_70_80.csv"),
    (80, 100, "[80,100]", "bucket_80_100.csv"),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def score8_to_100(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(score):
        return None
    return max(0.0, min(100.0, score / 8.0 * 100.0))


def score_bucket(value: Any) -> tuple[str | None, int | None, int | None, str | None]:
    score = to_float(value)
    if score is None:
        return None, None, None, None
    clamped = max(0.0, min(100.0, score))
    if clamped >= 80:
        return "[80,100]", 80, 100, "bucket_80_100.csv"
    lower = int(math.floor(clamped / 10.0) * 10)
    lower = max(0, min(70, lower))
    upper = lower + 10
    label = f"[{lower},{upper})"
    file_name = f"bucket_{lower:02d}_{upper:02d}.csv"
    return label, lower, upper, file_name


def first_view(record: dict[str, Any]) -> dict[str, Any]:
    views = record.get("views")
    if not isinstance(views, dict):
        return {}
    for key in ["desktop", "mobile", "image"]:
        value = views.get(key)
        if isinstance(value, dict):
            return value
    for value in views.values():
        if isinstance(value, dict):
            return value
    return {}


def view_by_name(record: dict[str, Any], name: str) -> dict[str, Any]:
    views = record.get("views")
    if not isinstance(views, dict):
        return {}
    value = views.get(name)
    return value if isinstance(value, dict) else {}


def view_score_100(view: dict[str, Any]) -> float | None:
    return score8_to_100(view.get("score"))


def view_image_path(view: dict[str, Any]) -> str | None:
    image = view.get("image") if isinstance(view.get("image"), dict) else {}
    path = image.get("path")
    return str(path) if path else None


def aggregate_view_name(record: dict[str, Any]) -> str | None:
    value = record.get("aggregate_view")
    if isinstance(value, str) and value:
        return value
    views = record.get("views")
    if not isinstance(views, dict):
        return None
    scored: list[tuple[str, float]] = []
    for name, view in views.items():
        if isinstance(view, dict):
            score = to_float(view.get("score"))
            if score is not None:
                scored.append((str(name), score))
    if not scored:
        return None
    return min(scored, key=lambda item: item[1])[0]


def to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def describe(values: list[Any]) -> dict[str, float | int | None]:
    clean = sorted(value for value in (to_float(value) for value in values) if value is not None)
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "mean": None,
            "median": None,
            "p90": None,
            "max": None,
        }
    def quantile(q: float) -> float:
        if len(clean) == 1:
            return clean[0]
        pos = (len(clean) - 1) * q
        lower = math.floor(pos)
        upper = math.ceil(pos)
        if lower == upper:
            return clean[lower]
        weight = pos - lower
        return clean[lower] * (1.0 - weight) + clean[upper] * weight

    return {
        "count": len(clean),
        "min": clean[0],
        "p10": quantile(0.10),
        "mean": mean(clean),
        "median": quantile(0.50),
        "p90": quantile(0.90),
        "max": clean[-1],
    }


def metadata_list_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_bucket_outputs(
    *,
    rows: list[dict[str, Any]],
    buckets_dir: Path | None,
    bucket_summary_csv: Path | None,
    bucket_summary_html: Path | None,
) -> None:
    bucket_rows: dict[str, list[dict[str, Any]]] = {file_name: [] for _, _, _, file_name in BUCKETS}
    for row in rows:
        file_name = row.get("bucket_file")
        if isinstance(file_name, str) and file_name in bucket_rows:
            bucket_rows[file_name].append(row)

    if buckets_dir is not None:
        buckets_dir.mkdir(parents=True, exist_ok=True)
        bucket_fieldnames = list(rows[0].keys()) if rows else None
        for _, _, _, file_name in BUCKETS:
            write_csv(buckets_dir / file_name, bucket_rows[file_name], bucket_fieldnames)

    source_totals = Counter(str(row.get("source_dir") or "") for row in rows)
    summary_rows: list[dict[str, Any]] = []
    for source in sorted(source_totals):
        total = source_totals[source]
        source_rows = [row for row in rows if str(row.get("source_dir") or "") == source]
        for lower, upper, label, file_name in BUCKETS:
            count = sum(1 for row in source_rows if row.get("score_bucket_100") == label)
            summary_rows.append(
                {
                    "source_dir": source,
                    "total": total,
                    "score_bucket_100": label,
                    "bucket_lower_100": lower,
                    "bucket_upper_100": upper,
                    "bucket_file": file_name,
                    "count": count,
                    "percent": round(count / total * 100.0, 4) if total else 0.0,
                }
            )

    all_total = len(rows)
    for lower, upper, label, file_name in BUCKETS:
        count = sum(1 for row in rows if row.get("score_bucket_100") == label)
        summary_rows.append(
            {
                "source_dir": "__all__",
                "total": all_total,
                "score_bucket_100": label,
                "bucket_lower_100": lower,
                "bucket_upper_100": upper,
                "bucket_file": file_name,
                "count": count,
                "percent": round(count / all_total * 100.0, 4) if all_total else 0.0,
            }
        )

    if bucket_summary_csv is not None:
        write_csv(bucket_summary_csv, summary_rows)
    if bucket_summary_html is not None:
        write_bucket_summary_html(bucket_summary_html, summary_rows)


def write_bucket_summary_html(path: Path, rows: list[dict[str, Any]]) -> None:
    sources = sorted({str(row["source_dir"]) for row in rows})
    buckets = [label for _, _, label, _ in BUCKETS]
    lookup = {(str(row["source_dir"]), str(row["score_bucket_100"])): row for row in rows}
    header = "".join(f"<th>{html.escape(bucket)}</th>" for bucket in buckets)
    body_rows = []
    for source in sources:
        cells = []
        for bucket in buckets:
            row = lookup.get((source, bucket), {})
            cells.append(
                "<td>"
                f"<strong>{html.escape(str(row.get('count', 0)))}</strong>"
                f"<small>{html.escape(str(row.get('percent', 0)))}%</small>"
                "</td>"
            )
        total = lookup.get((source, buckets[0]), {}).get("total", 0)
        body_rows.append(
            f"<tr><th>{html.escape(source)}</th><td>{html.escape(str(total))}</td>{''.join(cells)}</tr>"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Judge Score Bucket Summary</title>
  <style>
    body {{ margin: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #d9dee6; padding: 8px; text-align: right; vertical-align: top; }}
    th:first-child {{ text-align: left; }}
    thead th {{ background: #f4f6f8; position: sticky; top: 0; }}
    small {{ display: block; color: #657282; }}
  </style>
</head>
<body>
  <h1>Judge Score Bucket Summary</h1>
  <table>
    <thead><tr><th>source_dir</th><th>total</th>{header}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--failures", default=None)
    parser.add_argument("--buckets-dir", default=None)
    parser.add_argument("--bucket-summary-csv", default=None)
    parser.add_argument("--bucket-summary-html", default=None)
    args = parser.parse_args()

    records = read_jsonl(Path(args.scores))
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for record in records:
        min_view_name = aggregate_view_name(record)
        view = view_by_name(record, min_view_name) if min_view_name else first_view(record)
        desktop_view = view_by_name(record, "desktop")
        mobile_view = view_by_name(record, "mobile")
        image = view.get("image") if isinstance(view.get("image"), dict) else {}
        axis_scores = view.get("axis_scores") if isinstance(view.get("axis_scores"), dict) else {}
        backend_meta = view.get("backend_meta") if isinstance(view.get("backend_meta"), dict) else {}
        sample_metadata = record.get("sample_metadata") if isinstance(record.get("sample_metadata"), dict) else {}
        final_score = record.get("final_score")
        judge_score_100 = score8_to_100(final_score)
        bucket_label, bucket_lower, bucket_upper, bucket_file = score_bucket(judge_score_100)
        status = record.get("status")
        image_path = image.get("path")
        row: dict[str, Any] = {
            "id": record.get("id"),
            "source_dir": record.get("source_key") or record.get("source") or record.get("source_dir"),
            "image_path": image_path,
            "sample_relpath": record.get("sample_relpath"),
            "status": status,
            "final_score": final_score,
            "judge_score_8": final_score,
            "judge_score_100": judge_score_100,
            "score_bucket_100": bucket_label,
            "bucket_lower_100": bucket_lower,
            "bucket_upper_100": bucket_upper,
            "bucket_file": bucket_file,
            "aggregate_formula": record.get("aggregate_formula"),
            "min_score_view": min_view_name,
            "desktop_score_8": desktop_view.get("score"),
            "desktop_score_100": view_score_100(desktop_view),
            "mobile_score_8": mobile_view.get("score"),
            "mobile_score_100": view_score_100(mobile_view),
            "desktop_image_path": view_image_path(desktop_view),
            "mobile_image_path": view_image_path(mobile_view),
            "is_low_lt_20": judge_score_100 is not None and judge_score_100 < 20,
            "is_low_lt_30": judge_score_100 is not None and judge_score_100 < 30,
            "is_low_lt_40": judge_score_100 is not None and judge_score_100 < 40,
            "rationale": record.get("rationale"),
            "judge_rationale": record.get("rationale"),
            "elapsed_ms": view.get("elapsed_ms"),
            "cache_hit": view.get("cache_hit"),
            "screenshot_width": image.get("width"),
            "screenshot_height": image.get("height"),
            "screenshot_bytes": Path(image.get("path")).stat().st_size if image.get("path") and Path(image.get("path")).exists() else None,
            "canonical_web_size": True,
            "judge_model": backend_meta.get("model"),
            "judge_prompt_version": backend_meta.get("prompt_version"),
            "jout_index": sample_metadata.get("jout_index"),
            "pack": sample_metadata.get("pack"),
            "generator_model": sample_metadata.get("generator_model"),
            "generator_issues": metadata_list_text(sample_metadata.get("generator_issues")),
            "generator_retries_used": sample_metadata.get("generator_retries_used"),
            "html_bytes": sample_metadata.get("html_bytes"),
        }
        for axis in AXIS_COLUMNS:
            row[axis] = axis_scores.get(axis)
        if final_score is None or not image_path or not Path(image_path).exists():
            failure = dict(row)
            failure["errors"] = json.dumps(record.get("errors") or [], ensure_ascii=False)
            failure["render_status"] = record.get("render_status")
            failure["render_errors"] = json.dumps(record.get("render_errors") or [], ensure_ascii=False)
            failures.append(failure)
        else:
            rows.append(row)

    write_csv(Path(args.out), rows)
    if args.failures:
        write_csv(Path(args.failures), failures)
    write_bucket_outputs(
        rows=rows,
        buckets_dir=Path(args.buckets_dir) if args.buckets_dir else None,
        bucket_summary_csv=Path(args.bucket_summary_csv) if args.bucket_summary_csv else None,
        bucket_summary_html=Path(args.bucket_summary_html) if args.bucket_summary_html else None,
    )
    summary = {
        "schema_version": 1,
        "input_records": len(records),
        "records": len(rows),
        "failure_records": len(failures),
        "status_counts": dict(sorted(Counter(str(row.get("status")) for row in rows).items())),
        "failure_status_counts": dict(sorted(Counter(str(row.get("status")) for row in failures).items())),
        "source_counts": dict(sorted(Counter(str(row.get("source_dir")) for row in rows).items())),
        "pack_counts": dict(sorted(Counter(str(row.get("pack")) for row in rows if row.get("pack")).items())),
        "generator_model_counts": dict(sorted(Counter(str(row.get("generator_model")) for row in rows if row.get("generator_model")).items())),
        "with_generator_issues": sum(1 for row in rows if row.get("generator_issues") not in (None, "", "[]")),
        "bucket_counts": dict(sorted(Counter(str(row.get("score_bucket_100")) for row in rows).items())),
        "judge_score_100": describe([row.get("judge_score_100") for row in rows]),
        "judge_model": next((row.get("judge_model") for row in rows if row.get("judge_model")), None),
        "judge_prompt_version": next((row.get("judge_prompt_version") for row in rows if row.get("judge_prompt_version")), None),
        "out": str(Path(args.out).resolve()),
        "failures": str(Path(args.failures).resolve()) if args.failures else None,
        "buckets_dir": str(Path(args.buckets_dir).resolve()) if args.buckets_dir else None,
        "bucket_summary_csv": str(Path(args.bucket_summary_csv).resolve()) if args.bucket_summary_csv else None,
        "bucket_summary_html": str(Path(args.bucket_summary_html).resolve()) if args.bucket_summary_html else None,
    }
    write_json(Path(args.summary), summary)
    print(
        json.dumps(
            {
                "out": args.out,
                "summary": args.summary,
                "records": len(rows),
                "failures": len(failures),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
