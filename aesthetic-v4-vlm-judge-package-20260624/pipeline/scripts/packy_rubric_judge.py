#!/usr/bin/env python3
"""PackyAPI visual judge backend for score_images.py.

Reads a score_images.py request JSON on stdin, sends the screenshot and the
existing rubric prompt to PackyAPI's OpenAI-compatible chat completions
endpoint, and writes score_images.py-compatible JSON on stdout.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from codex_rubric_judge import (
    OCCLUSION_OVERLAP_CHECK,
    WEIGHTS,
    apply_occlusion_axis_penalties,
    build_occlusion_score_impact,
    build_prompt,
    axis_scores_are_uniform,
    calibrate_axis_scores_to_total,
    fallback_axis_scores_for_uniform_bucket,
    normalize_designer_review,
    normalize_occlusion_findings,
    weighted_axis_score,
)


AXIS_KEYS = list(WEIGHTS)
DEFAULT_BASE_URL = "https://www.packyapi.com/v1"
DEFAULT_MODEL = "gpt-5.5"
BOUNDARY_BUCKET_SCORES = {
    "[0,10)": 0.4,
    "[10,20)": 1.2,
    "[20,30)": 2.0,
    "[30,40)": 2.8,
    "[40,50)": 3.6,
    "[50,60)": 4.4,
    "[60,70)": 5.2,
    "[70,80)": 6.0,
    "[80,100]": 7.2,
}


def redact_secret(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-REDACTED", text)


def data_url_for_image(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError(f"model output did not contain JSON: {text[:500]}")


def clamp_score(value: Any) -> float:
    score = round(float(value), 1)
    return max(0.0, min(8.0, score))


def content_text(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(message_content)


def fixed_boundary_bucket(payload: dict[str, Any], rationale: str) -> tuple[str | None, float | None]:
    bucket = str(payload.get("bucket") or "").strip()
    if bucket not in BOUNDARY_BUCKET_SCORES:
        match = re.search(r"\[(?:0|10|20|30|40|50|60|70),(?:10|20|30|40|50|60|70|80)\)|\[80,100\]", rationale)
        bucket = match.group(0) if match else ""
    if bucket in BOUNDARY_BUCKET_SCORES:
        return bucket, BOUNDARY_BUCKET_SCORES[bucket]
    return None, None


def endpoint_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def normalize(
    payload: dict[str, Any],
    *,
    model: str,
    prompt_version: str,
    output_mode: str,
    elapsed_ms: int,
    retry_count: int,
) -> dict[str, Any]:
    if "score" not in payload:
        raise ValueError("judge response must include score")

    if output_mode == "score-only":
        score = clamp_score(payload["score"])
        axis_scores = {key: score for key in AXIS_KEYS}
        impact = build_occlusion_score_impact(axis_scores, [])
        return {
            "score": score,
            "axis_scores": axis_scores,
            "rationale": "score_only",
            "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
            "occlusion_findings": [],
            "occlusion_score_impact": impact,
            "designer_review": None,
            "backend_meta": {
                "judge": "packy_rubric_judge",
                "model": model,
                "prompt_version": prompt_version,
                "output_mode": output_mode,
                "elapsed_ms": elapsed_ms,
                "retry_count": retry_count,
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "rubric_weights": WEIGHTS,
            },
        }

    raw_axis = payload.get("axis_scores")
    if not isinstance(raw_axis, dict):
        raw_axis = {}
    score = clamp_score(payload["score"])
    rationale = str(payload.get("rationale") or "").strip()[:1000]
    boundary_bucket = None
    boundary_score = None
    axis_scores_fallback = None
    if prompt_version in {"aesthetic-v4", "aesthetic_v4"} or "blind-boundary" in prompt_version or "blind_boundary" in prompt_version:
        boundary_bucket, boundary_score = fixed_boundary_bucket(payload, rationale)
        if boundary_score is not None:
            score = boundary_score
    zero_defect = rationale.startswith("ZERO_DEFECT:")
    axis_scores = {key: clamp_score(raw_axis.get(key, score)) for key in AXIS_KEYS}
    if boundary_score is not None:
        if axis_scores_are_uniform(axis_scores):
            axis_scores = fallback_axis_scores_for_uniform_bucket(boundary_score, rationale)
            axis_scores_fallback = "uniform_model_axis_scores"
        axis_scores = calibrate_axis_scores_to_total(axis_scores, boundary_score)

    findings = normalize_occlusion_findings(
        payload,
        rationale=rationale,
        axis_scores=axis_scores,
        score=score,
    )
    if findings:
        axis_scores = apply_occlusion_axis_penalties(axis_scores, findings)
    weighted = weighted_axis_score(axis_scores)
    if boundary_score is not None:
        score = weighted
    elif zero_defect or abs(weighted - score) > 0.25:
        score = weighted
    impact = build_occlusion_score_impact(axis_scores, findings)

    backend_meta = dict(payload.get("backend_meta") or {})
    backend_meta.update(
        {
            "judge": "packy_rubric_judge",
            "model": model,
            "prompt_version": prompt_version,
            "output_mode": output_mode,
            "elapsed_ms": elapsed_ms,
            "retry_count": retry_count,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "rubric_weights": WEIGHTS,
        }
    )
    if boundary_bucket:
        backend_meta["bucket"] = boundary_bucket
    if axis_scores_fallback:
        backend_meta["axis_scores_fallback"] = axis_scores_fallback
    return {
        "score": score,
        "axis_scores": axis_scores,
        "rationale": rationale,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "occlusion_findings": findings,
        "occlusion_score_impact": impact,
        "designer_review": normalize_designer_review(payload.get("designer_review")),
        "backend_meta": backend_meta,
    }


def build_payload(
    *,
    request: dict[str, Any],
    prompt_version: str,
    model: str,
    output_mode: str,
    max_completion_tokens: int,
    include_response_format: bool,
    image_detail: str,
    temperature: float | None,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    image_path = Path(request["image"]["path"]).resolve()
    if output_mode == "score-only":
        prompt = (
            "你是严格的 UI 静态截图审美评分 judge。只看图片本身。"
            "只输出 JSON object，格式必须是 {\"score\": number}。"
            "score 是 0 到 8 的审美分，一位小数即可。"
            "不要输出理由、轴分、遮挡分析、建议或任何其他字段。"
        )
    else:
        prompt = build_prompt(request, prompt_version)
    payload: dict[str, Any] = {
        "model": model,
        "max_completion_tokens": max_completion_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url_for_image(image_path),
                            "detail": image_detail,
                        },
                    },
                ],
            }
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if include_response_format:
        payload["response_format"] = {"type": "json_object"}
    return payload


def should_retry_without_response_format(status_code: int, body: str) -> bool:
    lowered = body.lower()
    if status_code not in {400, 404, 422}:
        return False
    return "response_format" in lowered or "json_object" in lowered or "unsupported" in lowered


def post_chat_completions(
    *,
    client: httpx.Client,
    url: str,
    token: str,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    response = client.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            redact_secret(response.text[:4000]),
            request=response.request,
            response=response,
        )
    return response.json()


def call_model(args: argparse.Namespace, request: dict[str, Any], token: str) -> tuple[dict[str, Any], int]:
    url = endpoint_url(args.base_url)
    include_response_format = True
    retry_count = 0
    last_error: Exception | None = None

    with httpx.Client() as client:
        for attempt in range(args.max_retries + 1):
            payload = build_payload(
                request=request,
                prompt_version=args.prompt_version,
                model=args.model,
                output_mode=args.output_mode,
                max_completion_tokens=args.max_completion_tokens,
                include_response_format=include_response_format,
                image_detail=args.image_detail,
                temperature=args.temperature,
                reasoning_effort=args.reasoning_effort,
            )
            try:
                return post_chat_completions(
                    client=client,
                    url=url,
                    token=token,
                    payload=payload,
                    timeout=args.timeout,
                ), retry_count
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                body = exc.response.text[:4000]
                if include_response_format and should_retry_without_response_format(status_code, body):
                    include_response_format = False
                    retry_count += 1
                    continue
                if status_code not in {429, 500, 502, 503, 504} or attempt >= args.max_retries:
                    break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= args.max_retries:
                    break

            retry_count += 1
            time.sleep(min(args.retry_max_sleep, args.retry_base_sleep * (2**attempt)))

    raise RuntimeError(redact_secret(str(last_error or "unknown API error")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("PACKY_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("PACKY_JUDGE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--prompt-version", default=os.environ.get("PACKY_JUDGE_PROMPT_VERSION", "aesthetic-v4"))
    parser.add_argument(
        "--output-mode",
        choices=["full", "score-only"],
        default=os.environ.get("PACKY_JUDGE_OUTPUT_MODE", "full"),
    )
    parser.add_argument("--api-key-env", default="PACKY_API_KEY")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--reasoning-effort", default=os.environ.get("PACKY_REASONING_EFFORT"))
    parser.add_argument("--image-detail", choices=["low", "high", "auto"], default=os.environ.get("PACKY_IMAGE_DETAIL", "high"))
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=int(os.environ.get("PACKY_JUDGE_MAX_COMPLETION_TOKENS", "1200")),
    )
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PACKY_JUDGE_TIMEOUT", "240")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("PACKY_JUDGE_MAX_RETRIES", "4")))
    parser.add_argument("--retry-base-sleep", type=float, default=1.0)
    parser.add_argument("--retry-max-sleep", type=float, default=16.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.api_key_env)
    if not token:
        raise SystemExit(f"{args.api_key_env} is not set")

    request = json.loads(sys.stdin.read())
    started = time.perf_counter()
    try:
        raw, retry_count = call_model(args, request, token)
        choices = raw.get("choices") or []
        if not choices:
            raise RuntimeError(f"API response has no choices: {json.dumps(raw, ensure_ascii=False)[:1000]}")
        message = choices[0].get("message") or {}
        text = content_text(message.get("content"))
        payload = extract_json_object(text)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        normalized = normalize(
            payload,
            model=args.model,
            prompt_version=args.prompt_version,
            output_mode=args.output_mode,
            elapsed_ms=elapsed_ms,
            retry_count=retry_count,
        )
        normalized["backend_meta"]["image_detail"] = args.image_detail
    except Exception as exc:
        raise SystemExit(redact_secret(str(exc))[:10000])

    sys.stdout.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
