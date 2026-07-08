#!/usr/bin/env python3
"""Build an aesthetic-v4 manifest from HTML files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_HTML = {".html", ".htm"}
IGNORED_NAMES = {".DS_Store"}


def is_ignored(path: Path) -> bool:
    return (
        path.name in IGNORED_NAMES
        or path.name.startswith("._")
        or path.suffix.lower() == ".zip"
        or any(part.startswith("._") for part in path.parts)
    )


def stable_id(rel_path: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", Path(rel_path).stem).strip("_").lower() or "sample"
    digest = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:10]
    return f"{stem}_{digest}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sidecar_metadata(sample: Path) -> dict[str, Any]:
    candidates = [
        sample.with_suffix(".meta.json"),
        sample.parent / "metadata.json",
        sample.parent / "query_instruction.json",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and not is_ignored(candidate):
            payload = read_json(candidate)
            if payload:
                return payload
    return {}


def extract_title(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def query_text(metadata: dict[str, Any], title: str | None) -> str | None:
    for key in ("query", "query_text", "prompt", "instruction", "task", "description"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return title


def iter_html(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_HTML and not is_ignored(input_path):
            return [input_path]
        raise SystemExit(f"input file is not HTML: {input_path}")
    if not input_path.exists():
        raise SystemExit(f"input path not found: {input_path}")
    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_HTML and not is_ignored(path)
    )


def build_records(input_path: Path, viewport: str) -> list[dict[str, Any]]:
    created_at = datetime.now(timezone.utc).isoformat()
    root = input_path if input_path.is_dir() else input_path.parent
    records: list[dict[str, Any]] = []
    for sample in iter_html(input_path):
        rel = sample.relative_to(root).as_posix()
        title = extract_title(sample)
        metadata = sidecar_metadata(sample)
        source = rel.split("/", 1)[0] if "/" in rel else "input_html"
        record = {
            "schema_version": 1,
            "id": stable_id(rel),
            "source": source,
            "source_key": source,
            "input_type": "html",
            "input_path": str(sample.resolve()),
            "sample_relpath": rel,
            "target_viewport": viewport,
            "viewport_profile": viewport,
            "title": title,
            "query_text": query_text(metadata, title),
            "sample_metadata": metadata,
            "file_sha256": file_sha256(sample),
            "file_bytes": sample.stat().st_size,
            "created_at": created_at,
        }
        records.append(record)
    return records


def write_jsonl(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="../input_html", help="HTML file or directory.")
    parser.add_argument("--out", default="../runs/aesthetic-v4/manifest.jsonl")
    parser.add_argument("--summary", default="../runs/aesthetic-v4/manifest.summary.json")
    parser.add_argument("--viewport", choices=["desktop", "mobile", "all"], default="all")
    parser.add_argument("--expect-count", type=int, default=None)
    args = parser.parse_args()

    records = build_records(Path(args.input), args.viewport)
    if args.expect_count is not None and len(records) != args.expect_count:
        raise SystemExit(f"expected {args.expect_count} records, got {len(records)}")

    write_jsonl(records, Path(args.out))
    summary = {
        "profile": "aesthetic-v4",
        "input": str(Path(args.input).resolve()),
        "out": args.out,
        "records": len(records),
        "viewport": args.viewport,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
