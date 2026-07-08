#!/usr/bin/env python3
"""Evaluate aesthetic-v4 scores against bucket-labeled benchmark HTML folders."""

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


def threshold_metrics(rows: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    cutoff = threshold // 10
    tp = fp = fn = tn = 0
    for row in rows:
        truth = BUCKET_INDEX[row["designer_bucket"]] < cutoff
        pred = BUCKET_INDEX[row["pred_bucket"]] < cutoff
        if truth and pred:
            tp += 1
        elif not truth and pred:
            fp += 1
        elif truth and not pred:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "binary_accuracy": accuracy,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def build_rows(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for record in records:
        truth = truth_bucket(record)
        pred_score = score_100(record)
        pred = bucket_for(pred_score)
        if truth is None:
            failures.append({"id": record.get("id"), "reason": "missing_designer_bucket"})
            continue
        if pred not in BUCKET_INDEX:
            failures.append({"id": record.get("id"), "reason": "missing_prediction", "designer_bucket": truth})
            continue
        rows.append(
            {
                "id": record.get("id"),
                "sample_relpath": record.get("sample_relpath"),
                "input_path": record.get("input_path"),
                "status": record.get("status"),
                "designer_bucket": truth,
                "pred_score_100": None if pred_score is None else round(pred_score, 3),
                "pred_bucket": pred,
                "exact_match": pred == truth,
                "aggregate_view": record.get("aggregate_view"),
                "occlusion_detected": record.get("occlusion_overlap_detected"),
                "occlusion_status": record.get("occlusion_overlap_status"),
                "rationale": record.get("rationale"),
            }
        )
    return rows, failures


def summarize(rows: list[dict[str, Any]], *, target: float, thresholds: list[int]) -> dict[str, Any]:
    exact = sum(1 for row in rows if row["exact_match"])
    threshold_rows = [threshold_metrics(rows, threshold) for threshold in thresholds]
    min_recall = min((row["recall"] for row in threshold_rows), default=0.0)
    min_binary_accuracy = min((row["binary_accuracy"] for row in threshold_rows), default=0.0)
    exact_accuracy = exact / len(rows) if rows else 0.0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": len(rows),
        "target": target,
        "exact_match": exact,
        "exact_bucket_accuracy": exact_accuracy,
        "low_score_min_recall": min_recall,
        "low_score_min_binary_accuracy": min_binary_accuracy,
        "target_met": exact_accuracy >= target and min_recall >= target and min_binary_accuracy >= target,
        "thresholds": threshold_rows,
        "designer_bucket_distribution": dict(Counter(row["designer_bucket"] for row in rows)),
        "pred_bucket_distribution": dict(Counter(row["pred_bucket"] for row in rows)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "id",
        "sample_relpath",
        "input_path",
        "status",
        "designer_bucket",
        "pred_score_100",
        "pred_bucket",
        "exact_match",
        "aggregate_view",
        "occlusion_detected",
        "occlusion_status",
        "rationale",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_html(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    threshold_rows = "".join(
        "<tr>"
        f"<td>&lt;{item['threshold']}</td>"
        f"<td>{pct(item['precision'])}</td>"
        f"<td>{pct(item['recall'])}</td>"
        f"<td>{pct(item['binary_accuracy'])}</td>"
        f"<td>{item['tp']}</td><td>{item['fp']}</td><td>{item['fn']}</td><td>{item['tn']}</td>"
        "</tr>"
        for item in summary["thresholds"]
    )
    sample_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['id']))}</td>"
        f"<td>{html.escape(str(row['designer_bucket']))}</td>"
        f"<td>{html.escape(str(row['pred_bucket']))}</td>"
        f"<td>{html.escape(str(row['pred_score_100']))}</td>"
        f"<td>{html.escape(str(row['exact_match']))}</td>"
        f"<td>{html.escape(str(row.get('occlusion_status') or ''))}</td>"
        "</tr>"
        for row in rows
    )
    fail_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in item.values()) + "</tr>"
        for item in failures
    )
    status_class = "pass" if summary["target_met"] else "fail"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>aesthetic-v4 benchmark report</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:28px;background:#f7f7f4;color:#151515;line-height:1.45}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:16px}}.pass{{border-color:#8ac48a;background:#eef8ee}}.fail{{border-color:#e59b73;background:#fff1e8}}
.value{{font-size:30px;font-weight:760}}table{{border-collapse:collapse;width:100%;background:#fff;margin:12px 0}}th,td{{border:1px solid #ddd;padding:6px 7px;font-size:12px;text-align:left;vertical-align:top}}th{{background:#eee}}code{{background:#eee;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>aesthetic-v4 benchmark report</h1>
<div class="card {status_class}"><div>Target: {pct(summary['target'])}</div><div class="value">Target met: {html.escape(str(summary['target_met']))}</div>
<p>Exact bucket accuracy {pct(summary['exact_bucket_accuracy'])}; low-score min recall {pct(summary['low_score_min_recall'])}; min binary accuracy {pct(summary['low_score_min_binary_accuracy'])}; records {summary['records']}.</p></div>
<h2>Low-score thresholds</h2><table><thead><tr><th>threshold</th><th>precision</th><th>recall</th><th>binary accuracy</th><th>TP</th><th>FP</th><th>FN</th><th>TN</th></tr></thead><tbody>{threshold_rows}</tbody></table>
<h2>Samples</h2><table><thead><tr><th>id</th><th>designer bucket</th><th>pred bucket</th><th>pred score100</th><th>exact</th><th>occlusion</th></tr></thead><tbody>{sample_rows}</tbody></table>
<h2>Failures</h2><table><tbody>{fail_rows or '<tr><td>none</td></tr>'}</tbody></table>
</body></html>""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--metrics-json", required=True)
    parser.add_argument("--report-html", required=True)
    parser.add_argument("--target", type=float, default=0.82)
    parser.add_argument("--thresholds", default="20,30,40")
    args = parser.parse_args()

    records = read_jsonl(Path(args.scores))
    rows, failures = build_rows(records)
    thresholds = [int(item) for item in args.thresholds.split(",") if item.strip()]
    summary = summarize(rows, target=args.target, thresholds=thresholds)
    summary["failures"] = failures
    summary["scores"] = str(Path(args.scores).resolve())
    write_csv(Path(args.out_csv), rows)
    Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.metrics_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_html(Path(args.report_html), summary, rows, failures)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
