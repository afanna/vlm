#!/usr/bin/env python3
"""Build a local manual-QC HTML page from clean per-HTML JSON outputs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_uri(value: Any) -> str:
    if not value:
        return ""
    try:
        return Path(str(value)).resolve().as_uri()
    except Exception:
        return ""


def fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""


def axis_rows(record: dict[str, Any]) -> str:
    rows = []
    for item in ((record.get("score") or {}).get("axis_breakdown") or []):
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('axis') or ''))}</td>"
            f"<td>{fmt_score(item.get('axis_score_100'))}</td>"
            f"<td>{html.escape(str(item.get('weight') or ''))}</td>"
            f"<td>{fmt_score(item.get('weighted_contribution_100'))}</td>"
            "</tr>"
        )
    return "".join(rows)


def occlusion_rows(record: dict[str, Any]) -> str:
    rows = []
    occlusion = record.get("occlusion") if isinstance(record.get("occlusion"), dict) else {}
    for finding in occlusion.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        axes = ", ".join(str(axis) for axis in finding.get("affected_axes") or [])
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(finding.get('type') or ''))}</td>"
            f"<td>{html.escape(str(finding.get('severity') or ''))}</td>"
            f"<td>{html.escape(str(finding.get('target') or ''))}</td>"
            f"<td>{html.escape(axes)}</td>"
            f"<td>{html.escape(str(finding.get('evidence') or ''))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="5">none</td></tr>'
    return "".join(rows)


def screenshot_html(record: dict[str, Any]) -> str:
    images: list[str] = []
    links = record.get("links") if isinstance(record.get("links"), dict) else {}
    for path in links.get("screenshots") or []:
        uri = file_uri(path)
        if uri:
            images.append(f'<a href="{html.escape(uri)}"><img src="{html.escape(uri)}" loading="lazy"></a>')
    if not images:
        return '<div class="missing">no screenshot</div>'
    return "".join(images)


def card(record: dict[str, Any], json_path: Path) -> str:
    score = record.get("score") if isinstance(record.get("score"), dict) else {}
    occlusion = record.get("occlusion") if isinstance(record.get("occlusion"), dict) else {}
    html_uri = file_uri(record.get("html_path"))
    json_uri = file_uri(json_path)
    screenshot = screenshot_html(record)
    detected = "yes" if occlusion.get("detected") else "no"
    status = str(occlusion.get("status") or "none")
    types = ", ".join(str(item) for item in occlusion.get("types") or [])
    rationale = html.escape(str(record.get("rationale") or ""))
    return f"""
<article class="card" data-occlusion="{html.escape(detected)}" data-status="{html.escape(status)}">
  <header>
    <div>
      <h2>{html.escape(str(record.get('qid') or record.get('id') or 'sample'))}</h2>
      <p>{html.escape(str(record.get('html_path') or record.get('sample_relpath') or ''))}</p>
    </div>
    <div class="score"><b>{fmt_score(score.get('score_100'))}</b><span>/100</span></div>
  </header>
  <nav>
    <a href="{html.escape(html_uri)}">HTML</a>
    <a href="{html.escape(json_uri)}">JSON</a>
  </nav>
  <section class="grid">
    <div class="shot">{screenshot}</div>
    <div>
      <div class="occ {html.escape('bad' if occlusion.get('detected') else 'ok')}">occlusion: {html.escape(detected)} · {html.escape(status)} · {html.escape(types or 'none')}</div>
      <p class="rationale">{rationale}</p>
      <h3>Axis Breakdown</h3>
      <table><thead><tr><th>axis</th><th>axis_score_100</th><th>weight</th><th>weighted_contribution_100</th></tr></thead><tbody>{axis_rows(record)}</tbody></table>
      <h3>Occlusion Findings</h3>
      <table><thead><tr><th>type</th><th>severity</th><th>target</th><th>affected_axes</th><th>evidence</th></tr></thead><tbody>{occlusion_rows(record)}</tbody></table>
    </div>
  </section>
</article>
"""


def render(records: list[tuple[Path, dict[str, Any]]]) -> str:
    total = len(records)
    occluded = sum(1 for _, record in records if (record.get("occlusion") or {}).get("detected"))
    cards = "\n".join(card(record, path) for path, record in records)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>aesthetic-v4 manual QC</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f2; color: #171717; }}
    header.top {{ position: sticky; top: 0; z-index: 2; background: #fff; border-bottom: 1px solid #ddd; padding: 16px 24px; display: flex; gap: 24px; align-items: baseline; }}
    header.top h1 {{ margin: 0; font-size: 22px; }}
    main {{ padding: 20px 24px 48px; }}
    .card {{ background: #fff; border: 1px solid #d8d8d2; border-radius: 8px; margin: 0 0 18px; padding: 16px; }}
    .card > header {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid #ecece7; padding-bottom: 12px; }}
    h2 {{ margin: 0 0 6px; font-size: 18px; }}
    h3 {{ margin: 16px 0 8px; font-size: 14px; }}
    p {{ margin: 0; color: #555; }}
    nav {{ display: flex; gap: 10px; margin: 12px 0; }}
    a {{ color: #0f5f99; text-decoration: none; }}
    .score {{ text-align: right; min-width: 110px; }}
    .score b {{ font-size: 28px; display: block; }}
    .score span {{ color: #666; }}
    .grid {{ display: grid; grid-template-columns: minmax(260px, 380px) 1fr; gap: 16px; align-items: start; }}
    .shot img {{ width: 100%; max-height: 760px; object-fit: contain; border: 1px solid #ddd; background: #eee; }}
    .missing {{ border: 1px dashed #aaa; padding: 24px; color: #777; }}
    .occ {{ display: inline-block; padding: 6px 9px; border-radius: 6px; font-size: 13px; }}
    .occ.ok {{ background: #edf7ee; color: #176426; }}
    .occ.bad {{ background: #fff1e5; color: #9a3412; }}
    .rationale {{ margin: 12px 0; color: #222; line-height: 1.5; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 7px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f0eb; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} header.top {{ flex-wrap: wrap; }} }}
  </style>
</head>
<body>
  <header class="top"><h1>aesthetic-v4 manual QC</h1><span>Total {total}</span><span>Occlusion {occluded}</span></header>
  <main>{cards}</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, help="Index written by export_clean_html_score_json.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    index_path = Path(args.index)
    index = read_json(index_path)
    records: list[tuple[Path, dict[str, Any]]] = []
    for row in index.get("records") or []:
        if not isinstance(row, dict) or not row.get("json_path"):
            continue
        json_path = Path(str(row["json_path"]))
        if json_path.exists():
            records.append((json_path, read_json(json_path)))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(records), encoding="utf-8")
    print(json.dumps({"out": str(out.resolve()), "records": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
