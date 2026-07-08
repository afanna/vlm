#!/usr/bin/env python3
"""Apply the accepted aesthetic-v4 first-view + full-page surface policy.

This is not a model judge. It combines two already-produced raw/direct model
outputs:

1. first-view prediction
2. full-page prediction

Policy:
- default to the full-page prediction;
- if the first-view prediction is high ([70,80) or above) and the full-page
  prediction collapses to [40,50) or below, use first-view as a high-signal
  rescue.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def bucket_idx(bucket: str) -> int:
    if bucket in {"[80,100]", "[80,90)", "[90,100)", "[100]"}:
        return 8
    if not bucket.startswith("[") or "," not in bucket:
        raise ValueError(f"unsupported bucket: {bucket!r}")
    return int(bucket.split(",", 1)[0].strip("[")) // 10


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def exact(row: dict[str, Any]) -> bool | None:
    if "designer_bucket" not in row or not row.get("designer_bucket"):
        return None
    return bucket_idx(str(row["designer_bucket"])) == bucket_idx(pred_bucket(row))


def pred_bucket(row: dict[str, Any]) -> str:
    for key in ("raw_bucket", "bucket", "score_bucket_100"):
        value = row.get(key)
        if value:
            return str(value)
    raise KeyError("row has no prediction bucket column: expected raw_bucket, bucket, or score_bucket_100")


def pred_score_8(row: dict[str, Any]) -> str:
    for key in ("raw_score_8", "score_8", "judge_score_8", "final_score"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def pred_score_100(row: dict[str, Any]) -> str:
    for key in ("raw_score_100", "score_100", "judge_score_100"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def set_prediction(row: dict[str, Any], bucket: str, score_8: str, score_100: str) -> None:
    # Always expose raw_* accepted columns, and preserve package gallery aliases
    # when they are present.
    row["raw_bucket"] = bucket
    row["raw_score_8"] = score_8
    row["raw_score_100"] = score_100
    if "bucket" in row:
        row["bucket"] = bucket
    if "score_bucket_100" in row:
        row["score_bucket_100"] = bucket
    if "score_8" in row:
        row["score_8"] = score_8
    if "score_100" in row:
        row["score_100"] = score_100
    if "judge_score_8" in row:
        row["judge_score_8"] = score_8
    if "judge_score_100" in row:
        row["judge_score_100"] = score_100


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def apply_policy(
    first_rows: list[dict[str, str]],
    full_rows: list[dict[str, str]],
    high_threshold_idx: int,
    low_collapse_idx: int,
) -> list[dict[str, Any]]:
    first_by_id = {row["id"]: row for row in first_rows}
    out: list[dict[str, Any]] = []
    for full in full_rows:
        sample_id = full.get("id")
        if not sample_id or sample_id not in first_by_id:
            raise ValueError(f"full-page row missing matching first-view row: {sample_id!r}")
        first = first_by_id[sample_id]
        accepted = dict(full)
        accepted["accepted_evaluation_surface"] = "first_view_plus_fullpage_surface_policy"
        full_bucket = pred_bucket(full)
        first_bucket = pred_bucket(first)
        accepted["raw_bucket"] = full_bucket
        accepted["raw_score_8"] = pred_score_8(full)
        accepted["raw_score_100"] = pred_score_100(full)
        accepted["raw_bucket_before_surface_policy"] = full_bucket
        accepted["raw_score_8_before_surface_policy"] = pred_score_8(full)
        accepted["raw_score_100_before_surface_policy"] = pred_score_100(full)
        accepted["first_view_raw_bucket"] = first_bucket
        accepted["first_view_raw_score_8"] = pred_score_8(first)
        accepted["first_view_raw_score_100"] = pred_score_100(first)
        accepted["surface_policy"] = "fullpage"

        if (
            first_bucket
            and full_bucket
            and bucket_idx(first_bucket) >= high_threshold_idx
            and bucket_idx(full_bucket) <= low_collapse_idx
        ):
            set_prediction(accepted, first_bucket, pred_score_8(first), pred_score_100(first))
            accepted["surface_policy"] = "first_view_rescue_high_over_low_fullpage"
            first_reason = first.get("rationale_raw", "")[:800]
            full_reason = full.get("rationale_raw", "")[:800]
            accepted["rationale_raw"] = (
                "surface-policy accepted: first-view high-confidence rescue over "
                f"low full-page score; first_view_rationale={first_reason} | "
                f"fullpage_rationale={full_reason}"
            )
        out.append(accepted)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exact_values = [exact(row) for row in rows]
    has_truth = all(value is not None for value in exact_values)
    metrics: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted_evaluation_surface": "first_view_plus_fullpage_surface_policy",
        "is_single_call_raw_direct_judge": False,
        "is_model_output_based": True,
        "records": len(rows),
        "policy_counts": dict(Counter(str(row.get("surface_policy", "")) for row in rows)),
    }
    if not has_truth:
        return metrics

    exact_count = sum(1 for value in exact_values if value)
    per_bucket = []
    for bucket in sorted(Counter(str(row["designer_bucket"]) for row in rows), key=bucket_idx):
        subset = [row for row in rows if str(row["designer_bucket"]) == bucket]
        ok = sum(1 for row in subset if exact(row))
        per_bucket.append(
            {
                "designer_bucket": bucket,
                "support": len(subset),
                "exact": ok,
                "accuracy": ok / len(subset),
                "bucket80_met": ok / len(subset) >= 0.80,
                "pred_distribution": dict(Counter(pred_bucket(row) for row in subset)),
            }
        )
    thresholds = []
    for threshold in (20, 30, 40):
        cutoff = threshold // 10
        tp = fp = fn = tn = 0
        for row in rows:
            truth = bucket_idx(str(row["designer_bucket"])) < cutoff
            pred = bucket_idx(pred_bucket(row)) < cutoff
            if truth and pred:
                tp += 1
            elif (not truth) and pred:
                fp += 1
            elif truth and not pred:
                fn += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        accuracy = (tp + tn) / len(rows) if rows else 0.0
        thresholds.append(
            {
                "threshold": threshold,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "precision": precision,
                "recall": recall,
                "accuracy": accuracy,
            }
        )

    metrics.update(
        {
            "exact_match": exact_count,
            "exact_accuracy": exact_count / len(rows) if rows else 0.0,
            "overall_exact_target": 0.80,
            "overall_exact_target_met": exact_count / len(rows) >= 0.80 if rows else False,
            "bucket80_met_count": sum(1 for row in per_bucket if row["bucket80_met"]),
            "bucket_count": len(per_bucket),
            "all_buckets80_met": all(row["bucket80_met"] for row in per_bucket),
            "per_bucket": per_bucket,
            "threshold_metrics": thresholds,
            "min_low_precision": min(row["precision"] for row in thresholds),
            "min_low_recall": min(row["recall"] for row in thresholds),
            "min_low_accuracy": min(row["accuracy"] for row in thresholds),
        }
    )
    return metrics


def write_report(path: Path, metrics: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    has_truth = "exact_accuracy" in metrics
    if has_truth:
        summary_rows = [
            ("Accepted surface", "first-view + full-page policy"),
            ("Overall exact", f"{metrics['exact_match']}/{metrics['records']} ({pct(metrics['exact_accuracy'])})"),
            ("Overall >=80 target", "PASS" if metrics["overall_exact_target_met"] else "FAIL"),
            ("Buckets >=80", f"{metrics['bucket80_met_count']}/{metrics['bucket_count']}"),
            ("Every bucket >=80", "PASS" if metrics["all_buckets80_met"] else "FAIL"),
            ("Min low recall", pct(metrics["min_low_recall"])),
            ("Min low precision", pct(metrics["min_low_precision"])),
            ("Min low accuracy", pct(metrics["min_low_accuracy"])),
        ]
    else:
        summary_rows = [
            ("Accepted surface", "first-view + full-page policy"),
            ("Records", str(metrics["records"])),
            ("Truth labels", "not provided"),
        ]
    summary_html = "".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>"
        for key, value in summary_rows
    )
    per_bucket_html = ""
    if has_truth:
        body = "".join(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in [
                    item["designer_bucket"],
                    item["support"],
                    item["exact"],
                    pct(item["accuracy"]),
                    "PASS" if item["bucket80_met"] else "FAIL",
                    json.dumps(item["pred_distribution"], ensure_ascii=False, sort_keys=True),
                ]
            )
            + "</tr>"
            for item in metrics["per_bucket"]
        )
        per_bucket_html = (
            "<h2>Per Designer Bucket</h2><table><thead><tr><th>Bucket</th><th>Support</th>"
            "<th>Exact</th><th>Accuracy</th><th>>=80</th><th>Prediction distribution</th>"
            f"</tr></thead><tbody>{body}</tbody></table>"
        )

    rescued = [row for row in rows if row.get("surface_policy") == "first_view_rescue_high_over_low_fullpage"]
    rescued_rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(value or ''))}</td>"
            for value in [
                row.get("id"),
                row.get("sample_relpath"),
                row.get("designer_bucket"),
                row.get("raw_bucket_before_surface_policy"),
                row.get("first_view_raw_bucket"),
                row.get("raw_bucket"),
            ]
        )
        + "</tr>"
        for row in rescued
    )
    path.write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>aesthetic-v4 accepted surface policy</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;background:#f7f7f5;color:#111;line-height:1.45}}table{{border-collapse:collapse;width:100%;background:#fff;margin:14px 0 28px}}th,td{{border:1px solid #ddd;padding:8px;font-size:13px;text-align:left;vertical-align:top}}th{{background:#eee}}.warn{{background:#fff7d6;border:1px solid #dfc45a;border-radius:8px;padding:12px;margin:16px 0}}code{{background:#eee;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>aesthetic-v4 accepted surface policy</h1>
<div class="warn"><b>Scope:</b> this is not a single-call one-image raw judge. It combines first-view and full-page raw/direct model outputs with an accepted screenshot-surface policy. Single-call raw outputs remain preserved in the CSV.</div>
<h2>Summary</h2><table><tbody>{summary_html}</tbody></table>
<h2>Policy</h2><p>Default to full-page. If first-view is high confidence ([70,80) or above) and full-page collapses to [40,50) or below, use the first-view prediction as a high-signal rescue.</p>
{per_bucket_html}
<h2>Surface Rescues</h2><table><thead><tr><th>ID</th><th>Sample</th><th>Designer</th><th>Full-page raw</th><th>First-view raw</th><th>Accepted</th></tr></thead><tbody>{rescued_rows}</tbody></table>
</body></html>""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-view-csv", required=True)
    parser.add_argument("--full-page-csv", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--metrics-json", required=True)
    parser.add_argument("--report-html", required=True)
    parser.add_argument("--high-threshold-bucket-idx", type=int, default=7)
    parser.add_argument("--low-collapse-bucket-idx", type=int, default=4)
    args = parser.parse_args()

    rows = apply_policy(
        read_csv(Path(args.first_view_csv)),
        read_csv(Path(args.full_page_csv)),
        args.high_threshold_bucket_idx,
        args.low_collapse_bucket_idx,
    )
    metrics = summarize(rows)
    metrics["first_view_csv"] = args.first_view_csv
    metrics["full_page_csv"] = args.full_page_csv
    metrics["accepted_csv"] = args.out_csv

    write_csv(Path(args.out_csv), rows)
    Path(args.metrics_json).write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_report(Path(args.report_html), metrics, rows)
    print(
        json.dumps(
            {
                "accepted_csv": args.out_csv,
                "metrics_json": args.metrics_json,
                "report_html": args.report_html,
                "records": len(rows),
                "exact_accuracy": metrics.get("exact_accuracy"),
                "overall_exact_target_met": metrics.get("overall_exact_target_met"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
