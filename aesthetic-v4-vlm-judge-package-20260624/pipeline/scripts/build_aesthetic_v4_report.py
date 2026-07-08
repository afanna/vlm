#!/usr/bin/env python3
"""Build an aesthetic-v4 HTML report from score_images output."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


AXES = [
    ("visual_impact_originality", "视觉冲击 / 原创性"),
    ("composition_hierarchy", "构图层级"),
    ("typography", "字体表现"),
    ("color_material", "色彩与材质"),
    ("detail_finish", "细节完成度"),
    ("basic_usability", "基础可用性"),
]
BUCKETS = [
    ("[0,10)", 0, 10),
    ("[10,20)", 10, 20),
    ("[20,30)", 20, 30),
    ("[30,40)", 30, 40),
    ("[40,50)", 40, 50),
    ("[50,60)", 50, 60),
    ("[60,70)", 60, 70),
    ("[70,80)", 70, 80),
    ("[80,100]", 80, 100),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_100(raw_score: Any) -> float | None:
    try:
        value = float(raw_score)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return max(0.0, min(100.0, value * 12.5))


def bucket_for(value: float | None) -> str:
    if value is None:
        return "failed"
    if value >= 80:
        return "[80,100]"
    for label, lower, upper in BUCKETS[:-1]:
        if lower <= value < upper:
            return label
    return "[0,10)" if value < 0 else "[80,100]"


def file_uri(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().as_uri()
    except Exception:
        return ""


def aggregate_view(record: dict[str, Any]) -> dict[str, Any]:
    views = record.get("views")
    if not isinstance(views, dict):
        return {}
    name = record.get("aggregate_view")
    if isinstance(name, str) and isinstance(views.get(name), dict):
        return views[name]
    for key in ("desktop", "mobile", "image"):
        if isinstance(views.get(key), dict):
            return views[key]
    for value in views.values():
        if isinstance(value, dict):
            return value
    return {}


def csv_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        score = score_100(record.get("final_score"))
        view = aggregate_view(record)
        meta = view.get("backend_meta") if isinstance(view.get("backend_meta"), dict) else {}
        impact = view.get("occlusion_score_impact") if isinstance(view.get("occlusion_score_impact"), dict) else {}
        rows.append(
            {
                "id": record.get("id"),
                "status": record.get("status"),
                "score_100": "" if score is None else round(score, 2),
                "bucket": bucket_for(score),
                "aggregate_view": record.get("aggregate_view"),
                "prompt_version": meta.get("prompt_version") or "aesthetic-v4",
                "model": meta.get("model"),
                "occlusion_overlap_check": record.get("occlusion_overlap_check") or "always_on",
                "occlusion_findings": json.dumps(view.get("occlusion_findings") or [], ensure_ascii=False),
                "occlusion_affected_axes": json.dumps(impact.get("affected_axes") or [], ensure_ascii=False),
                "input_path": record.get("input_path"),
                "rationale": record.get("rationale"),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "id",
        "status",
        "score_100",
        "bucket",
        "aggregate_view",
        "prompt_version",
        "model",
        "occlusion_overlap_check",
        "occlusion_findings",
        "occlusion_affected_axes",
        "input_path",
        "rationale",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def axis_table(view: dict[str, Any], show_breakdown: bool) -> str:
    if not show_breakdown:
        return ""
    scores = view.get("axis_scores") if isinstance(view.get("axis_scores"), dict) else {}
    rows = []
    for key, label in AXES:
        value = scores.get(key)
        text = "" if value is None else f"{float(value):.1f}"
        rows.append(f"<tr><th>{html.escape(label)}</th><td>{html.escape(text)}</td></tr>")
    return "<table class=\"axis\"><tbody>" + "".join(rows) + "</tbody></table>"


def occlusion_block(view: dict[str, Any], show_breakdown: bool) -> str:
    if not show_breakdown:
        return ""
    findings = view.get("occlusion_findings") if isinstance(view.get("occlusion_findings"), list) else []
    impact = view.get("occlusion_score_impact") if isinstance(view.get("occlusion_score_impact"), dict) else {}
    if not findings:
        return '<div class="occ ok">occlusion_overlap_check: always_on · no finding</div>'
    rows = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        rows.append(
            "<tr>"
            f"<th>{html.escape(str(finding.get('type') or 'unknown'))}</th>"
            f"<td>{html.escape(str(finding.get('severity') or ''))}</td>"
            f"<td>{html.escape(str(finding.get('target') or ''))}</td>"
            f"<td>{html.escape(str(finding.get('evidence') or ''))}</td>"
            "</tr>"
        )
    affected = impact.get("affected_axes") if isinstance(impact.get("affected_axes"), list) else []
    loss_text = "" if not affected else f" · affected axes {len(affected)}"
    return (
        f'<div class="occ warn">occlusion_overlap_check: always_on{html.escape(loss_text)}</div>'
        '<table class="occ-table"><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def designer_review_block(view: dict[str, Any]) -> str:
    review = view.get("designer_review")
    if not isinstance(review, dict):
        return ""
    parts = []
    for label, key in (("优点", "pros"), ("缺点", "cons"), ("建议", "suggestions")):
        items = review.get(key)
        if isinstance(items, list) and items:
            parts.append(
                f"<h4>{html.escape(label)}</h4><ul>"
                + "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
                + "</ul>"
            )
    return f'<div class="designer-review">{"".join(parts)}</div>' if parts else ""


def view_block(name: str, view: dict[str, Any], show_breakdown: bool) -> str:
    image = view.get("image") if isinstance(view.get("image"), dict) else {}
    image_uri = file_uri(image.get("path"))
    screenshot = (
        f'<img src="{html.escape(image_uri)}" alt="{html.escape(name)} screenshot" loading="lazy">'
        if image_uri
        else '<div class="missing">no screenshot</div>'
    )
    rationale = html.escape(str(view.get("rationale") or ""))
    score = view.get("score")
    score_text = "" if score is None else f"{score_100(score):.2f}/100"
    return f"""
<section class="view">
  <div class="shot">{screenshot}</div>
  <div class="view-body">
    <h3>{html.escape(name)} <span>{html.escape(score_text)}</span></h3>
    {axis_table(view, show_breakdown)}
    {occlusion_block(view, show_breakdown)}
    <p>{rationale}</p>
    {designer_review_block(view)}
  </div>
</section>
"""


def render_html(records: list[dict[str, Any]], *, score_breakdown: str) -> str:
    status_counts = Counter(str(record.get("status")) for record in records)
    bucket_counts = Counter(bucket_for(score_100(record.get("final_score"))) for record in records)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cards = []
    for record in records:
        final_100 = score_100(record.get("final_score"))
        bucket = bucket_for(final_100)
        views = record.get("views") if isinstance(record.get("views"), dict) else {}
        record_config = record.get("quality_config") if isinstance(record.get("quality_config"), dict) else {}
        show_breakdown = score_breakdown == "on" and record_config.get("score_breakdown", "on") != "off"
        view_html = "".join(view_block(name, view, show_breakdown) for name, view in views.items() if isinstance(view, dict))
        score_text = "N/A" if final_100 is None else f"{final_100:.2f}"
        cards.append(
            f"""
<article class="card" data-bucket="{html.escape(bucket)}" data-status="{html.escape(str(record.get('status')))}">
  <header>
    <div>
      <h2>{html.escape(str(record.get("id") or ""))}</h2>
      <p>{html.escape(str(record.get("sample_relpath") or record.get("input_path") or ""))}</p>
    </div>
    <div class="score"><b>{html.escape(score_text)}</b><span>/100</span><em>{html.escape(bucket)}</em></div>
  </header>
  <div class="rationale">{html.escape(str(record.get("rationale") or ""))}</div>
  {view_html}
</article>
"""
        )

    bucket_summary = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{bucket_counts.get(label, 0)}</td></tr>"
        for label, _, _ in BUCKETS
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>aesthetic-v4 report</title>
  <style>
    :root {{ color-scheme: light; --bg: #f7f7f5; --panel: #fff; --text: #171717; --muted: #666b73; --line: #d9ddd6; --accent: #1f6f61; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    body > header {{ padding: 24px; border-bottom: 1px solid var(--line); background: #fff; position: sticky; top: 0; z-index: 2; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    .meta {{ color: var(--muted); font-size: 13px; display: flex; gap: 14px; flex-wrap: wrap; }}
    main {{ display: grid; grid-template-columns: minmax(210px, 260px) 1fr; gap: 18px; padding: 18px; }}
    aside {{ align-self: start; position: sticky; top: 98px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 7px 0; font-size: 13px; text-align: left; }}
    td {{ text-align: right; color: var(--muted); }}
    .cards {{ display: grid; gap: 14px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .card > header {{ display: flex; justify-content: space-between; gap: 16px; padding: 14px; border-bottom: 1px solid var(--line); }}
    h2 {{ margin: 0; font-size: 17px; }}
    h2 + p {{ margin: 5px 0 0; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }}
    .score {{ text-align: right; min-width: 110px; }}
    .score b {{ font-size: 28px; line-height: 1; }}
    .score span {{ color: var(--muted); font-size: 12px; }}
    .score em {{ display: block; margin-top: 4px; color: var(--accent); font-style: normal; font-weight: 650; }}
    .rationale {{ padding: 14px; border-bottom: 1px solid var(--line); color: #2c3035; line-height: 1.55; font-size: 14px; }}
    .view {{ display: grid; grid-template-columns: minmax(280px, 42%) 1fr; gap: 14px; padding: 14px; border-top: 1px solid var(--line); }}
    .shot {{ background: #ebeee9; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; min-height: 180px; display: grid; place-items: center; }}
    .shot img {{ width: 100%; height: auto; display: block; }}
    .view h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .view h3 span {{ color: var(--muted); font-weight: 500; margin-left: 8px; }}
    .axis {{ margin-bottom: 10px; }}
    .occ {{ margin: 8px 0; font-size: 12px; color: var(--muted); }}
    .occ.warn {{ color: #8a4b13; font-weight: 650; }}
    .occ.ok {{ color: #4d655d; }}
    .occ-table {{ margin: 8px 0 10px; }}
    .occ-table th, .occ-table td {{ text-align: left; vertical-align: top; padding: 6px 8px 6px 0; }}
    .designer-review {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 13px; }}
    .designer-review h4 {{ margin: 8px 0 4px; font-size: 13px; }}
    .designer-review ul {{ margin: 0 0 8px 18px; padding: 0; color: #2c3035; }}
    .view p {{ margin: 0; color: #2c3035; line-height: 1.55; font-size: 13px; }}
    .missing {{ color: var(--muted); font-size: 13px; }}
    @media (max-width: 860px) {{ main {{ grid-template-columns: 1fr; }} aside {{ position: static; }} .view {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>aesthetic-v4 VLM Judge Report</h1>
    <div class="meta">
      <span>generated {html.escape(now)}</span>
      <span>records {len(records)}</span>
      <span>scored {status_counts.get("scored", 0)}</span>
      <span>partial/failed {sum(v for k, v in status_counts.items() if k != "scored")}</span>
    </div>
  </header>
  <main>
    <aside>
      <h2>分档统计</h2>
      <table><tbody>{bucket_summary}</tbody></table>
    </aside>
    <section class="cards">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", default="../runs/aesthetic-v4/scores.jsonl")
    parser.add_argument("--out", default="../runs/aesthetic-v4/report.html")
    parser.add_argument("--summary", default="../runs/aesthetic-v4/report.summary.json")
    parser.add_argument("--csv", default="../runs/aesthetic-v4/scores.csv")
    parser.add_argument("--score-breakdown", choices=["off", "on"], default=os.environ.get("AESTHETIC_V4_SCORE_BREAKDOWN", "on"))
    args = parser.parse_args()

    records = read_jsonl(Path(args.scores))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(records, score_breakdown=args.score_breakdown), encoding="utf-8")

    rows = csv_rows(records)
    write_csv(Path(args.csv), rows)

    summary = {
        "profile": "aesthetic-v4",
        "records": len(records),
        "status_counts": dict(Counter(str(record.get("status")) for record in records)),
        "bucket_counts": dict(Counter(row["bucket"] for row in rows)),
        "score_breakdown": args.score_breakdown,
        "out": str(out_path),
        "csv": args.csv,
    }
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
