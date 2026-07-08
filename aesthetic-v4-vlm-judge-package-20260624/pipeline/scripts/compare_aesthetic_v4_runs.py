#!/usr/bin/env python3
"""Compare two aesthetic-v4 score JSONL runs at sample level."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BUCKETS = [
    "[0,10)",
    "[10,20)",
    "[20,30)",
    "[30,40)",
    "[40,50)",
    "[50,60)",
    "[60,70)",
    "[70,80)",
    "[80,100]",
]
BUCKET_INDEX = {bucket: index for index, bucket in enumerate(BUCKETS)}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_100(record: dict[str, Any]) -> float | None:
    aesthetics = ((record.get("extra_info_scores") or {}).get("aesthetics") or {})
    value = aesthetics.get("score_100")
    if value is None and record.get("final_score") is not None:
        value = float(record["final_score"]) * 12.5
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def bucket_for(value: float | None) -> str:
    if value is None:
        return "failed"
    if value >= 80:
        return "[80,100]"
    if value < 0:
        return "[0,10)"
    for bucket in BUCKETS[:-1]:
        lower = int(bucket.split(",", 1)[0].strip("["))
        upper = int(bucket.split(",", 1)[1].strip(")"))
        if lower <= value < upper:
            return bucket
    return "[80,100]"


def join_key(record: dict[str, Any]) -> str:
    return str(record.get("input_path") or record.get("sample_relpath") or record.get("id") or "")


def truth_bucket(record: dict[str, Any]) -> str | None:
    candidates = [
        record.get("source"),
        record.get("source_key"),
        str(record.get("sample_relpath") or "").split("/", 1)[0],
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text in BUCKET_INDEX:
            return text
    return None


def model_name(record: dict[str, Any]) -> str:
    view_name = record.get("aggregate_view")
    views = record.get("views") if isinstance(record.get("views"), dict) else {}
    view = views.get(view_name) if isinstance(view_name, str) else None
    if not isinstance(view, dict):
        view = next((item for item in views.values() if isinstance(item, dict)), {})
    meta = view.get("backend_meta") if isinstance(view.get("backend_meta"), dict) else {}
    return str(meta.get("model") or "")


def summarize_model(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    truth_rows = [row for row in rows if row.get("truth_bucket") in BUCKET_INDEX]
    exact = sum(1 for row in truth_rows if row.get(f"{label}_bucket") == row.get("truth_bucket"))
    return {
        "records": len(rows),
        "with_truth": len(truth_rows),
        "exact_match": exact,
        "exact_bucket_accuracy": exact / len(truth_rows) if truth_rows else None,
        "bucket_distribution": dict(Counter(str(row.get(f"{label}_bucket")) for row in rows)),
        "occlusion_detected": sum(1 for row in rows if row.get(f"{label}_occlusion_detected")),
    }


def build_rows(left: list[dict[str, Any]], right: list[dict[str, Any]], left_label: str, right_label: str) -> list[dict[str, Any]]:
    right_by_key = {join_key(record): record for record in right}
    rows: list[dict[str, Any]] = []
    for left_record in left:
        key = join_key(left_record)
        right_record = right_by_key.get(key)
        left_score = score_100(left_record)
        right_score = score_100(right_record) if right_record else None
        left_bucket = bucket_for(left_score)
        right_bucket = bucket_for(right_score)
        truth = truth_bucket(left_record) or (truth_bucket(right_record) if right_record else None)
        score_delta = None if left_score is None or right_score is None else round(left_score - right_score, 3)
        rows.append(
            {
                "join_key": key,
                "id": left_record.get("id"),
                "sample_relpath": left_record.get("sample_relpath"),
                "input_path": left_record.get("input_path"),
                "truth_bucket": truth,
                f"{left_label}_model": model_name(left_record),
                f"{left_label}_score_100": None if left_score is None else round(left_score, 3),
                f"{left_label}_bucket": left_bucket,
                f"{left_label}_exact": None if truth not in BUCKET_INDEX else left_bucket == truth,
                f"{left_label}_occlusion_detected": bool(left_record.get("occlusion_overlap_detected")),
                f"{left_label}_occlusion_status": left_record.get("occlusion_overlap_status"),
                f"{right_label}_model": model_name(right_record) if right_record else "",
                f"{right_label}_score_100": None if right_score is None else round(right_score, 3),
                f"{right_label}_bucket": right_bucket,
                f"{right_label}_exact": None if truth not in BUCKET_INDEX else right_bucket == truth,
                f"{right_label}_occlusion_detected": bool(right_record.get("occlusion_overlap_detected")) if right_record else None,
                f"{right_label}_occlusion_status": right_record.get("occlusion_overlap_status") if right_record else None,
                "score_delta_left_minus_right": score_delta,
                "abs_score_delta": None if score_delta is None else abs(score_delta),
                "bucket_match": left_bucket == right_bucket,
                "occlusion_match": (
                    bool(left_record.get("occlusion_overlap_detected"))
                    == (bool(right_record.get("occlusion_overlap_detected")) if right_record else None)
                ),
                f"{left_label}_rationale": left_record.get("rationale"),
                f"{right_label}_rationale": right_record.get("rationale") if right_record else "",
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]], left_label: str, right_label: str, left_path: Path, right_path: Path) -> dict[str, Any]:
    deltas = [float(row["abs_score_delta"]) for row in rows if row.get("abs_score_delta") is not None]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "left_label": left_label,
        "right_label": right_label,
        "left_scores": str(left_path.resolve()),
        "right_scores": str(right_path.resolve()),
        "records": len(rows),
        "joined_records": sum(1 for row in rows if row.get(f"{right_label}_score_100") is not None),
        "bucket_match_count": sum(1 for row in rows if row.get("bucket_match")),
        "bucket_match_rate": sum(1 for row in rows if row.get("bucket_match")) / len(rows) if rows else 0.0,
        "occlusion_match_count": sum(1 for row in rows if row.get("occlusion_match")),
        "occlusion_match_rate": sum(1 for row in rows if row.get("occlusion_match")) / len(rows) if rows else 0.0,
        "mean_abs_score_delta": sum(deltas) / len(deltas) if deltas else None,
        "max_abs_score_delta": max(deltas) if deltas else None,
        left_label: summarize_model(rows, left_label),
        right_label: summarize_model(rows, right_label),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_html(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    left = summary["left_label"]
    right = summary["right_label"]
    sample_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('truth_bucket') or ''))}</td>"
        f"<td>{html.escape(str(row.get(f'{left}_score_100') or ''))}</td>"
        f"<td>{html.escape(str(row.get(f'{left}_bucket') or ''))}</td>"
        f"<td>{html.escape(str(row.get(f'{right}_score_100') or ''))}</td>"
        f"<td>{html.escape(str(row.get(f'{right}_bucket') or ''))}</td>"
        f"<td>{html.escape(str(row.get('abs_score_delta') or ''))}</td>"
        f"<td>{html.escape(str(row.get('bucket_match')))}</td>"
        f"<td>{html.escape(str(row.get('occlusion_match')))}</td>"
        "</tr>"
        for row in rows
    )
    left_acc = summary[left]["exact_bucket_accuracy"]
    right_acc = summary[right]["exact_bucket_accuracy"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>aesthetic-v4 model comparison</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:28px;background:#f7f7f4;color:#151515;line-height:1.45}}.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:16px}}.value{{font-size:28px;font-weight:760}}table{{border-collapse:collapse;width:100%;background:#fff;margin:12px 0}}th,td{{border:1px solid #ddd;padding:6px 7px;font-size:12px;text-align:left;vertical-align:top}}th{{background:#eee}}code{{background:#eee;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>aesthetic-v4 model comparison</h1>
<div class="card"><div class="value">{html.escape(left)} vs {html.escape(right)}</div>
<p>Records {summary['records']}; bucket match {pct(summary['bucket_match_rate'])}; occlusion match {pct(summary['occlusion_match_rate'])}; mean abs score delta {summary['mean_abs_score_delta']}; max abs score delta {summary['max_abs_score_delta']}.</p>
<p>{html.escape(left)} exact accuracy {'' if left_acc is None else pct(left_acc)}; {html.escape(right)} exact accuracy {'' if right_acc is None else pct(right_acc)}.</p></div>
<table><thead><tr><th>id</th><th>truth</th><th>{html.escape(left)} score</th><th>{html.escape(left)} bucket</th><th>{html.escape(right)} score</th><th>{html.escape(right)} bucket</th><th>abs delta</th><th>bucket match</th><th>occlusion match</th></tr></thead><tbody>{sample_rows}</tbody></table>
</body></html>""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--left-label", default="claude47")
    parser.add_argument("--right-label", default="gpt55")
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--metrics-json", required=True)
    parser.add_argument("--report-html", required=True)
    args = parser.parse_args()

    left_path = Path(args.left)
    right_path = Path(args.right)
    rows = build_rows(read_jsonl(left_path), read_jsonl(right_path), args.left_label, args.right_label)
    summary = summarize(rows, args.left_label, args.right_label, left_path, right_path)
    write_csv(Path(args.out_csv), rows)
    Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.metrics_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_html(Path(args.report_html), summary, rows)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
