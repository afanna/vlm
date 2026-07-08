#!/usr/bin/env python3
"""Render screenshots by splitting a manifest across parallel node workers."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def chunk_rows(rows: list[dict[str, Any]], chunks: int) -> list[list[dict[str, Any]]]:
    result = [[] for _ in range(chunks)]
    for idx, row in enumerate(rows):
        result[idx % chunks].append(row)
    return result


def render_command(args: argparse.Namespace, manifest: Path, out_dir: Path) -> list[str]:
    command = [
        "node",
        "scripts/render_screenshots.mjs",
        "--manifest",
        str(manifest),
        "--out",
        str(out_dir),
        "--viewport",
        args.viewport,
        "--wait-ms",
        str(args.wait_ms),
        "--timeout-ms",
        str(args.timeout_ms),
        "--hard-timeout-ms",
        str(args.hard_timeout_ms),
    ]
    if args.screenshot_on_timeout:
        command.append("--screenshot-on-timeout")
    if args.capture_scroll_width:
        command.append("--capture-scroll-width")
    else:
        command.append("--no-capture-scroll-width")
    if args.max_screenshot_css_width:
        command.extend(["--max-screenshot-css-width", str(args.max_screenshot_css_width)])
    if args.full_page:
        command.extend(["--full-page", "--max-screenshot-css-height", str(args.max_screenshot_css_height)])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--chunks", type=int, default=8)
    parser.add_argument("--viewport", default="auto")
    parser.add_argument("--wait-ms", type=int, default=2000)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--hard-timeout-ms", type=int, default=90000)
    parser.add_argument("--screenshot-on-timeout", action="store_true")
    parser.add_argument("--capture-scroll-width", dest="capture_scroll_width", action="store_true", default=True)
    parser.add_argument("--no-capture-scroll-width", dest="capture_scroll_width", action="store_false")
    parser.add_argument("--max-screenshot-css-width", type=int, default=12000)
    parser.add_argument("--full-page", action="store_true")
    parser.add_argument("--max-screenshot-css-height", type=int, default=12000)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    manifest_path = Path(args.manifest)
    out_dir = Path(args.out)
    chunks_root = out_dir / "_chunks"
    manifests_dir = chunks_root / "manifests"
    logs_dir = chunks_root / "logs"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(manifest_path)
    chunks = chunk_rows(rows, args.chunks)
    processes: list[tuple[int, subprocess.Popen[bytes], Any, Any, Path]] = []
    for idx, part in enumerate(chunks):
        chunk_manifest = manifests_dir / f"chunk_{idx:02d}.jsonl"
        chunk_out = chunks_root / f"chunk_{idx:02d}"
        write_jsonl(chunk_manifest, part)
        stdout = (logs_dir / f"chunk_{idx:02d}.stdout.log").open("wb")
        stderr = (logs_dir / f"chunk_{idx:02d}.stderr.log").open("wb")
        proc = subprocess.Popen(
            render_command(args, chunk_manifest, chunk_out),
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
        )
        processes.append((idx, proc, stdout, stderr, chunk_out))
        print(json.dumps({"chunk": idx, "records": len(part), "status": "started"}, sort_keys=True), flush=True)

    failed: list[dict[str, Any]] = []
    for idx, proc, stdout, stderr, chunk_out in processes:
        code = proc.wait()
        stdout.close()
        stderr.close()
        status = "finished" if code == 0 else "failed"
        print(json.dumps({"chunk": idx, "status": status, "returncode": code}, sort_keys=True), flush=True)
        if code != 0:
            failed.append({"chunk": idx, "returncode": code, "out": str(chunk_out)})

    if failed:
        raise SystemExit(json.dumps({"failed_chunks": failed}, ensure_ascii=False))

    merged: list[dict[str, Any]] = []
    for idx, _, _, _, chunk_out in processes:
        chunk_manifest = chunk_out / "render_manifest.jsonl"
        if not chunk_manifest.exists():
            raise SystemExit(f"missing render manifest for chunk {idx}: {chunk_manifest}")
        merged.extend(read_jsonl(chunk_manifest))

    order = {str(row.get("id")): idx for idx, row in enumerate(rows)}
    merged.sort(key=lambda row: order.get(str(row.get("id")), 10**12))
    write_jsonl(out_dir / "render_manifest.jsonl", merged)

    by_viewport: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    for row in merged:
        by_status[str(row.get("render_status") or "unknown")] += 1
        for view in row.get("views") or []:
            if isinstance(view, dict):
                by_viewport[str(view.get("viewport") or "unknown")] += 1

    summary = {
        "schema_version": 1,
        "manifest": str(manifest_path.resolve()),
        "out": str((out_dir / "render_manifest.jsonl").resolve()),
        "records": len(merged),
        "chunks": args.chunks,
        "status_counts": dict(sorted(by_status.items())),
        "by_viewport": dict(sorted(by_viewport.items())),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "chunk_root": str(chunks_root.resolve()),
    }
    (out_dir / "render_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
