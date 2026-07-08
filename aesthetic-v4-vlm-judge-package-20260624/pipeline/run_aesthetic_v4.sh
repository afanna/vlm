#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

BACKEND="${AESTHETIC_V4_BACKEND:-model}"
FORCE_MOCK=0
if [[ "${1:-}" == "--mock" ]]; then
  BACKEND="mock"
  FORCE_MOCK=1
  shift
fi

INPUT_DIR="${1:-$PACKAGE_ROOT/input_html}"
RUN_DIR="${AESTHETIC_V4_RUN_DIR:-$PACKAGE_ROOT/runs/aesthetic-v4}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_BIN="${NODE_BIN:-node}"

ENV_FILE="$PACKAGE_ROOT/config/aesthetic-v4.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'* && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$ENV_FILE"
fi

if [[ "$FORCE_MOCK" == "0" ]]; then
  BACKEND="${AESTHETIC_V4_BACKEND:-$BACKEND}"
fi

PANGU_BASE_URL="${PANGU_BASE_URL:-http://43.139.21.243:4000}"
PANGU_JUDGE_MODEL="${PANGU_JUDGE_MODEL:-claude-opus-4-7-thinking}"
PANGU_JUDGE_PROMPT_VERSION="${PANGU_JUDGE_PROMPT_VERSION:-aesthetic-v4}"
PANGU_JUDGE_OUTPUT_MODE="${PANGU_JUDGE_OUTPUT_MODE:-full}"
PANGU_JUDGE_TIMEOUT="${PANGU_JUDGE_TIMEOUT:-360}"
PANGU_JUDGE_MAX_TOKENS="${PANGU_JUDGE_MAX_TOKENS:-1200}"
PACKY_BASE_URL="${PACKY_BASE_URL:-https://www.packyapi.com/v1}"
PACKY_JUDGE_MODEL="${PACKY_JUDGE_MODEL:-gpt-5.5}"
PACKY_JUDGE_PROMPT_VERSION="${PACKY_JUDGE_PROMPT_VERSION:-aesthetic-v4}"
PACKY_JUDGE_OUTPUT_MODE="${PACKY_JUDGE_OUTPUT_MODE:-full}"
PACKY_JUDGE_TIMEOUT="${PACKY_JUDGE_TIMEOUT:-240}"
PACKY_JUDGE_MAX_COMPLETION_TOKENS="${PACKY_JUDGE_MAX_COMPLETION_TOKENS:-1200}"
PACKY_IMAGE_DETAIL="${PACKY_IMAGE_DETAIL:-high}"
AESTHETIC_V4_MODEL_PROVIDER="${AESTHETIC_V4_MODEL_PROVIDER:-pangu}"
AESTHETIC_V4_WORKERS="${AESTHETIC_V4_WORKERS:-1}"
AESTHETIC_V4_MANIFEST_VIEWPORT="${AESTHETIC_V4_MANIFEST_VIEWPORT:-mobile}"
AESTHETIC_V4_VIEWPORT="${AESTHETIC_V4_VIEWPORT:-mobile}"
AESTHETIC_V4_VIEWPORT_SELECTION="${AESTHETIC_V4_VIEWPORT_SELECTION:-auto}"
AESTHETIC_V4_AGGREGATE_STRATEGY="${AESTHETIC_V4_AGGREGATE_STRATEGY:-min}"
AESTHETIC_V4_SCREENSHOT_MODE="${AESTHETIC_V4_SCREENSHOT_MODE:-first_view}"
AESTHETIC_V4_SURFACE_POLICY="${AESTHETIC_V4_SURFACE_POLICY:-single}"
AESTHETIC_V4_FULLPAGE_MAX_HEIGHT="${AESTHETIC_V4_FULLPAGE_MAX_HEIGHT:-12000}"
AESTHETIC_V4_ADAPTIVE_VIEWPORTS="${AESTHETIC_V4_ADAPTIVE_VIEWPORTS:-off}"
AESTHETIC_V4_SCORE_BREAKDOWN="${AESTHETIC_V4_SCORE_BREAKDOWN:-on}"
AESTHETIC_V4_DESIGNER_REVIEW="${AESTHETIC_V4_DESIGNER_REVIEW:-off}"
AESTHETIC_V4_FORMAL_REPORT="${AESTHETIC_V4_FORMAL_REPORT:-0}"
AESTHETIC_V4_OCCLUSION_OVERLAP_CHECK="always_on"

case "$AESTHETIC_V4_SCREENSHOT_MODE" in
  fullpage|first_view) ;;
  *)
    echo "AESTHETIC_V4_SCREENSHOT_MODE must be fullpage or first_view, got: $AESTHETIC_V4_SCREENSHOT_MODE" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_MANIFEST_VIEWPORT" in
  desktop|mobile|all) ;;
  *)
    echo "AESTHETIC_V4_MANIFEST_VIEWPORT must be desktop, mobile, or all; got: $AESTHETIC_V4_MANIFEST_VIEWPORT" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_ADAPTIVE_VIEWPORTS" in
  off|on|auto) ;;
  *)
    echo "AESTHETIC_V4_ADAPTIVE_VIEWPORTS must be off, on, or auto; got: $AESTHETIC_V4_ADAPTIVE_VIEWPORTS" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_SCORE_BREAKDOWN" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_SCORE_BREAKDOWN must be off or on; got: $AESTHETIC_V4_SCORE_BREAKDOWN" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_DESIGNER_REVIEW" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_DESIGNER_REVIEW must be off or on; got: $AESTHETIC_V4_DESIGNER_REVIEW" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_MODEL_PROVIDER" in
  packy|pangu) ;;
  *)
    echo "AESTHETIC_V4_MODEL_PROVIDER must be packy or pangu; got: $AESTHETIC_V4_MODEL_PROVIDER" >&2
    exit 2
    ;;
esac

case "$PANGU_JUDGE_OUTPUT_MODE" in
  full|score-only) ;;
  *)
    echo "PANGU_JUDGE_OUTPUT_MODE must be full or score-only; got: $PANGU_JUDGE_OUTPUT_MODE" >&2
    exit 2
    ;;
esac

case "$PACKY_JUDGE_OUTPUT_MODE" in
  full|score-only) ;;
  *)
    echo "PACKY_JUDGE_OUTPUT_MODE must be full or score-only; got: $PACKY_JUDGE_OUTPUT_MODE" >&2
    exit 2
    ;;
esac

case "$PACKY_IMAGE_DETAIL" in
  low|high|auto) ;;
  *)
    echo "PACKY_IMAGE_DETAIL must be low, high, or auto; got: $PACKY_IMAGE_DETAIL" >&2
    exit 2
    ;;
esac

if [[ "$AESTHETIC_V4_SURFACE_POLICY" == "first_view_plus_fullpage" && "$AESTHETIC_V4_SCREENSHOT_MODE" != "first_view" ]]; then
  echo "AESTHETIC_V4_SURFACE_POLICY=first_view_plus_fullpage requires AESTHETIC_V4_SCREENSHOT_MODE=first_view." >&2
  echo "Default aesthetic-v4 mode is fast first-view screenshots; long screenshots are an explicit switch." >&2
  exit 2
fi

RENDER_EXTRA_ARGS=()
if [[ "$AESTHETIC_V4_SCREENSHOT_MODE" == "fullpage" ]]; then
  RENDER_EXTRA_ARGS+=(--full-page --max-screenshot-css-height "$AESTHETIC_V4_FULLPAGE_MAX_HEIGHT")
fi

SCORE_EXTRA_ARGS=(
  --adaptive-viewports "$AESTHETIC_V4_ADAPTIVE_VIEWPORTS"
  --score-breakdown "$AESTHETIC_V4_SCORE_BREAKDOWN"
  --designer-review "$AESTHETIC_V4_DESIGNER_REVIEW"
)
if [[ "$AESTHETIC_V4_FORMAL_REPORT" == "1" ]]; then
  SCORE_EXTRA_ARGS+=(--formal-report)
fi

mkdir -p "$RUN_DIR"

echo "[aesthetic-v4] build manifest"
"$PYTHON_BIN" scripts/build_html_manifest.py \
  --input "$INPUT_DIR" \
  --out "$RUN_DIR/manifest.jsonl" \
  --summary "$RUN_DIR/manifest.summary.json" \
  --viewport "$AESTHETIC_V4_MANIFEST_VIEWPORT"

echo "[aesthetic-v4] render screenshots ($AESTHETIC_V4_SCREENSHOT_MODE)"
RENDER_COMMAND=(
  "$NODE_BIN" scripts/render_screenshots.mjs
  --manifest "$RUN_DIR/manifest.jsonl" \
  --out "$RUN_DIR/screenshots" \
  --viewport "$AESTHETIC_V4_VIEWPORT" \
  --screenshot-on-timeout \
  --capture-scroll-width
)
if [[ ${#RENDER_EXTRA_ARGS[@]} -gt 0 ]]; then
  RENDER_COMMAND+=("${RENDER_EXTRA_ARGS[@]}")
fi
"${RENDER_COMMAND[@]}"

if [[ "$BACKEND" == "mock" ]]; then
  echo "[aesthetic-v4] score with mock backend"
  "$PYTHON_BIN" scripts/score_images.py \
    --input "$RUN_DIR/screenshots/render_manifest.jsonl" \
    --out "$RUN_DIR/scores.jsonl" \
    --cache "$RUN_DIR/score_cache.jsonl" \
    --backend mock \
    --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
    --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
    --workers "$AESTHETIC_V4_WORKERS" \
    "${SCORE_EXTRA_ARGS[@]}" \
    --refresh
else
  if [[ "$AESTHETIC_V4_MODEL_PROVIDER" == "packy" ]]; then
    if [[ -z "${PACKY_API_KEY:-}" ]]; then
      echo "PACKY_API_KEY is empty. Copy config/aesthetic-v4.env.example to config/aesthetic-v4.env and fill it, or run: npm run run:mock" >&2
      exit 2
    fi
    JUDGE_COMMAND="$PYTHON_BIN scripts/packy_rubric_judge.py --base-url $PACKY_BASE_URL --prompt-version $PACKY_JUDGE_PROMPT_VERSION --model $PACKY_JUDGE_MODEL --output-mode $PACKY_JUDGE_OUTPUT_MODE --timeout $PACKY_JUDGE_TIMEOUT --max-completion-tokens $PACKY_JUDGE_MAX_COMPLETION_TOKENS --image-detail $PACKY_IMAGE_DETAIL"
    JUDGE_TIMEOUT="$((PACKY_JUDGE_TIMEOUT + 40))"
    MODEL_LABEL="PackyAPI model backend ($PACKY_JUDGE_MODEL, output_mode=$PACKY_JUDGE_OUTPUT_MODE, image_detail=$PACKY_IMAGE_DETAIL)"
  else
    if [[ -z "${PANGU_API_KEY:-}" ]]; then
      echo "PANGU_API_KEY is empty. Copy config/aesthetic-v4.env.example to config/aesthetic-v4.env and fill it, or run: npm run run:mock" >&2
      exit 2
    fi
    JUDGE_COMMAND="$PYTHON_BIN scripts/pangu_rubric_judge.py --base-url $PANGU_BASE_URL --prompt-version $PANGU_JUDGE_PROMPT_VERSION --model $PANGU_JUDGE_MODEL --output-mode $PANGU_JUDGE_OUTPUT_MODE --timeout $PANGU_JUDGE_TIMEOUT --max-tokens $PANGU_JUDGE_MAX_TOKENS"
    JUDGE_TIMEOUT="$((PANGU_JUDGE_TIMEOUT + 40))"
    MODEL_LABEL="Pangu model backend ($PANGU_JUDGE_MODEL, output_mode=$PANGU_JUDGE_OUTPUT_MODE)"
  fi

  echo "[aesthetic-v4] score with $MODEL_LABEL"
  "$PYTHON_BIN" scripts/score_images.py \
    --input "$RUN_DIR/screenshots/render_manifest.jsonl" \
    --out "$RUN_DIR/scores.jsonl" \
    --cache "$RUN_DIR/score_cache.jsonl" \
    --backend command \
    --judge-command "$JUDGE_COMMAND" \
    --timeout "$JUDGE_TIMEOUT" \
    --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
    --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
    --workers "$AESTHETIC_V4_WORKERS" \
    "${SCORE_EXTRA_ARGS[@]}" \
    --refresh
fi

echo "[aesthetic-v4] build report"
"$PYTHON_BIN" scripts/build_aesthetic_v4_report.py \
  --scores "$RUN_DIR/scores.jsonl" \
  --out "$RUN_DIR/report.html" \
  --summary "$RUN_DIR/report.summary.json" \
  --csv "$RUN_DIR/scores.csv" \
  --score-breakdown "$AESTHETIC_V4_SCORE_BREAKDOWN"

if [[ "$AESTHETIC_V4_SURFACE_POLICY" == "first_view_plus_fullpage" ]]; then
  echo "[aesthetic-v4] render full-page screenshots"
  "$NODE_BIN" scripts/render_screenshots.mjs \
    --manifest "$RUN_DIR/manifest.jsonl" \
    --out "$RUN_DIR/screenshots_fullpage" \
    --viewport "$AESTHETIC_V4_VIEWPORT" \
    --screenshot-on-timeout \
    --capture-scroll-width \
    --full-page \
    --max-screenshot-css-height "$AESTHETIC_V4_FULLPAGE_MAX_HEIGHT"

  if [[ "$BACKEND" == "mock" ]]; then
    echo "[aesthetic-v4] score full-page screenshots with mock backend"
    "$PYTHON_BIN" scripts/score_images.py \
      --input "$RUN_DIR/screenshots_fullpage/render_manifest.jsonl" \
      --out "$RUN_DIR/scores.fullpage.jsonl" \
      --cache "$RUN_DIR/score_cache.fullpage.jsonl" \
      --backend mock \
      --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
      --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
      --workers "$AESTHETIC_V4_WORKERS" \
      "${SCORE_EXTRA_ARGS[@]}" \
      --refresh
  else
    echo "[aesthetic-v4] score full-page screenshots with $MODEL_LABEL"
    "$PYTHON_BIN" scripts/score_images.py \
      --input "$RUN_DIR/screenshots_fullpage/render_manifest.jsonl" \
      --out "$RUN_DIR/scores.fullpage.jsonl" \
      --cache "$RUN_DIR/score_cache.fullpage.jsonl" \
      --backend command \
      --judge-command "$JUDGE_COMMAND" \
      --timeout "$JUDGE_TIMEOUT" \
      --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
      --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
      --workers "$AESTHETIC_V4_WORKERS" \
      "${SCORE_EXTRA_ARGS[@]}" \
      --refresh
  fi

  echo "[aesthetic-v4] build full-page report"
  "$PYTHON_BIN" scripts/build_aesthetic_v4_report.py \
    --scores "$RUN_DIR/scores.fullpage.jsonl" \
    --out "$RUN_DIR/report.fullpage.html" \
    --summary "$RUN_DIR/report.fullpage.summary.json" \
    --csv "$RUN_DIR/scores.fullpage.csv" \
    --score-breakdown "$AESTHETIC_V4_SCORE_BREAKDOWN"

  echo "[aesthetic-v4] apply accepted surface policy"
  "$PYTHON_BIN" scripts/apply_aesthetic_v4_surface_policy.py \
    --first-view-csv "$RUN_DIR/scores.csv" \
    --full-page-csv "$RUN_DIR/scores.fullpage.csv" \
    --out-csv "$RUN_DIR/scores.surface-policy.csv" \
    --metrics-json "$RUN_DIR/surface-policy.metrics.json" \
    --report-html "$RUN_DIR/report.surface-policy.html"
fi

echo "[aesthetic-v4] done"
echo "report: $RUN_DIR/report.html"
echo "scores: $RUN_DIR/scores.jsonl"
if [[ "$AESTHETIC_V4_SURFACE_POLICY" == "first_view_plus_fullpage" ]]; then
  echo "surface-policy report: $RUN_DIR/report.surface-policy.html"
  echo "surface-policy scores: $RUN_DIR/scores.surface-policy.csv"
fi
