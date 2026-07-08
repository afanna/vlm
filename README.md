# aesthetic-v4 VLM Judge Package

这个文件夹把当前 aesthetic-v4 评审功能打包成一个可复跑流程：

```text
HTML input -> canonical first-view screenshot -> Pangu Claude 4.7 VLM judge -> clean JSON/CSV/HTML/manual QC report
```

## 快速运行

```bash
cd pipeline
npm install
python3 -m pip install -r requirements.txt
npm run run:mock
open ../runs/aesthetic-v4/report.html
```

`run:mock` 只验证流程，不代表真实美学评分。

## 截图策略

默认策略是直接打开 HTML，只渲染一个 canonical viewport 的首屏截图后交给 VLM judge。mobile 首屏是 `390x844 @2x`，输出图约 `780x1688`；desktop 首屏是 `1440x900`。这是日常快评路径。

长图是显式开关，默认关闭。需要验证滚动完整性、底部导航真实遮挡、长页面内容延续时，再设置 `AESTHETIC_V4_SCREENSHOT_MODE=fullpage`。full-page 截图会先把 viewport 高度扩到文档截图高度再截完整内容，避免 fixed/sticky footer 被传统 fullPage 截图冻结在首屏位置造成假遮挡。

默认参数：

```bash
AESTHETIC_V4_SCREENSHOT_MODE=first_view
AESTHETIC_V4_FULLPAGE_MAX_HEIGHT=12000
AESTHETIC_V4_MANIFEST_VIEWPORT=mobile
AESTHETIC_V4_VIEWPORT=mobile
AESTHETIC_V4_VIEWPORT_SELECTION=auto
```

## 质检开关

```bash
AESTHETIC_V4_ADAPTIVE_VIEWPORTS=off
AESTHETIC_V4_SCORE_BREAKDOWN=on
AESTHETIC_V4_DESIGNER_REVIEW=off
```

- `adaptive_viewports=off`: 只跑默认或指定 viewport。
- `adaptive_viewports=on`: 跑已渲染的 desktop+mobile，页面分取低分。
- `adaptive_viewports=auto`: 先跑 canonical viewport；响应式风险、低置信、临界分数、遮挡风险或正式报告模式下补跑另一端。
- `score_breakdown=on`: 默认打开，输出总分、六轴、固定权重、weighted contribution 和遮挡影响；`off` 只影响报告展示，不改变内部评分。
- `designer_review=on`: 额外输出 pros/cons/suggestions；`off` 不输出长评，也不改变分数。

`occlusion_overlap_check` 固定为 `always_on`，不提供关闭开关。遮挡/重叠问题不会动态改权重，而是降低对应 `axis_scores`，并输出 `occlusion_findings` 和 `occlusion_score_impact`。相关轴按 severity 设上限：minor 最高 6、moderate 最高 4、severe 最高 2、blocking 为 0。

如果需要复跑长图口径：

```bash
npm run run:model:fullpage
```

默认模型输出模式是 `PANGU_JUDGE_OUTPUT_MODE=full`，用于正式质检 JSON：输出六轴、固定权重、遮挡证据和 rationale。

`score-only` 只用于速度测试：

```bash
npm run run:model:score-only
```

这个模式只要求模型输出 `{score}`，不作为最终人工质检 JSON。

`claude-opus-4-7-thinking` 是当前默认交付模型，默认从 Pangu OpenAI-compatible 网关调用。`PANGU_JUDGE_PROMPT_VERSION=aesthetic-v4` 是公开稳定入口，内部已收敛到当前 benchmark 校准版 prompt。需要和 Pangu `gpt-5.5` 对比时，用同一输入和同一截图口径另跑一份：

```bash
AESTHETIC_V4_MODEL_PROVIDER=pangu PANGU_JUDGE_MODEL=gpt-5.5 AESTHETIC_V4_RUN_DIR=../runs/aesthetic-v4-gpt55 bash run_aesthetic_v4.sh ../input_html
python3 scripts/compare_aesthetic_v4_runs.py \
  --left ../runs/aesthetic-v4-gpt55/scores.jsonl \
  --right ../runs/aesthetic-v4/scores.jsonl \
  --left-label pangu_gpt55 \
  --right-label pangu_claude47 \
  --out-csv ../acceptance/model_comparison.csv \
  --metrics-json ../acceptance/model_comparison.metrics.json \
  --report-html ../acceptance/model_comparison.html
```

`run:surface-policy` 是显式实验入口，会先跑首屏再跑长图并合并结果；它不是 aesthetic-v4 的默认主路径。

## 配置真实模型

```bash
cp ../config/aesthetic-v4.env.example ../config/aesthetic-v4.env
```

在 `../config/aesthetic-v4.env` 填入本机私有值：

```bash
PANGU_BASE_URL=http://43.139.21.243:4000
PANGU_API_KEY=...
PANGU_JUDGE_MODEL=claude-opus-4-7-thinking
PANGU_JUDGE_PROMPT_VERSION=aesthetic-v4
PANGU_JUDGE_OUTPUT_MODE=full
AESTHETIC_V4_MODEL_PROVIDER=pangu
```

显式传入的 shell 环境变量优先于 `../config/aesthetic-v4.env`；本机 env 文件只用于补默认值和保存私有 key。比如临时速度测试可以直接设置 `PANGU_JUDGE_OUTPUT_MODE=score-only`，不会被 env 文件里的 `full` 覆盖。

然后运行：

```bash
npm run run:model
open ../runs/aesthetic-v4/report.html
```

## 输入 HTML

默认读取：

```text
input_html/
```

也可以指定其他目录：

```bash
bash pipeline/run_aesthetic_v4.sh /path/to/html_dir
```

或者单文件：

```bash
bash pipeline/run_aesthetic_v4.sh /path/to/index.html
```

## 输出文件

默认输出到：

```text
runs/aesthetic-v4/
```

关键文件：

- `manifest.jsonl`: HTML 输入清单
- `screenshots/render_manifest.jsonl`: 默认首屏截图清单；fullpage 模式下是自然长图截图清单
- `scores.jsonl`: 结构化 VLM judge 结果
- `scores.csv`: 表格版结果
- `report.html`: 可打开的本地报告
- `report.summary.json`: 统计摘要
- `outputs/json/*.json`: 每个 HTML 一个干净 JSON，给下游和人工质检使用
- `manual_qc/index.html`: HTML、截图、JSON、遮挡证据聚合质检页
- `acceptance/benchmark_*`: 基准集验收 metrics / CSV / HTML
- `acceptance/occlusion_*`: 遮挡验收报告和 JSON

正式交付的干净 JSON 由下面命令生成：

```bash
npm run export:json
npm run validate:json
npm run manual-qc
```

干净 JSON 只保留百分制对外分数：

- 必须包含 `aesthetic_rubric`
- `score.score_100` 是最终分
- `score.axis_breakdown[].axis_score_100`
- `score.axis_breakdown[].weight`
- `score.axis_breakdown[].weighted_contribution_100`
- `score.score_100 = sum(weighted_contribution_100)`
- `occlusion.detected/status/types/findings/affected_axes/score_impact`

不输出 `score_8`、重复 `rationale`、`weighted_score_from_axis_scores`、`occlusion_weighted_loss_from_max` 等内部旧字段。

## 验收命令

代码和包结构：

```bash
python3 tools/validate_package.py
python3 -m py_compile pipeline/scripts/*.py
node --check pipeline/scripts/render_screenshots.mjs
cd pipeline && npm run run:mock && npm run export:json && npm run validate:json && npm run manual-qc
```

Pangu Claude 4.7 单样本 smoke：

```bash
cd pipeline
source ../config/aesthetic-v4.env
AESTHETIC_V4_MODEL_PROVIDER=pangu AESTHETIC_V4_RUN_DIR=../runs/smoke_pangu_claude47 AESTHETIC_V4_MANIFEST_VIEWPORT=mobile AESTHETIC_V4_VIEWPORT=mobile bash run_aesthetic_v4.sh ../input_html/sample_aesthetic_v4_dashboard.html
```

基准集验收：

```bash
cd pipeline
source ../config/aesthetic-v4.env
AESTHETIC_V4_MODEL_PROVIDER=pangu \
PANGU_JUDGE_MODEL=claude-opus-4-7-thinking \
PANGU_JUDGE_PROMPT_VERSION=aesthetic-v4 \
PANGU_JUDGE_OUTPUT_MODE=full \
AESTHETIC_V4_RUN_DIR=../acceptance/benchmark_claude47_final_default \
AESTHETIC_V4_MANIFEST_VIEWPORT=all \
AESTHETIC_V4_VIEWPORT=all \
AESTHETIC_V4_VIEWPORT_SELECTION=auto \
AESTHETIC_V4_ADAPTIVE_VIEWPORTS=off \
bash run_aesthetic_v4.sh "/Volumes/TU820/aesthetic/基准集-bobo 确认版"

python3 scripts/evaluate_aesthetic_v4_benchmark.py \
  --scores ../acceptance/benchmark_claude47_final_default/scores.jsonl \
  --out-csv ../acceptance/benchmark_claude47_final_default/details.csv \
  --metrics-json ../acceptance/benchmark_claude47_final_default/metrics.json \
  --report-html ../acceptance/benchmark_claude47_final_default/benchmark_report.html \
  --target 0.82

AESTHETIC_V4_MODEL_PROVIDER=pangu \
PANGU_JUDGE_MODEL=gpt-5.5 \
AESTHETIC_V4_RUN_DIR=../acceptance/benchmark_gpt55 \
AESTHETIC_V4_MANIFEST_VIEWPORT=all \
AESTHETIC_V4_VIEWPORT=all \
AESTHETIC_V4_VIEWPORT_SELECTION=auto \
AESTHETIC_V4_ADAPTIVE_VIEWPORTS=off \
bash run_aesthetic_v4.sh "/Volumes/TU820/aesthetic/基准集-bobo 确认版"
python3 scripts/evaluate_aesthetic_v4_benchmark.py --scores ../acceptance/benchmark_gpt55/scores.jsonl --out-csv ../acceptance/benchmark_gpt55/details.csv --metrics-json ../acceptance/benchmark_gpt55/metrics.json --report-html ../acceptance/benchmark_gpt55/benchmark_report.html

python3 scripts/compare_aesthetic_v4_runs.py --left ../acceptance/benchmark_gpt55/scores.jsonl --right ../acceptance/benchmark_claude47_final_default/scores.jsonl --left-label pangu_gpt55 --right-label pangu_claude47 --out-csv ../acceptance/model_comparison.csv --metrics-json ../acceptance/model_comparison.metrics.json --report-html ../acceptance/model_comparison.html
```

验收阈值：single-call Pangu Claude 4.7 首屏结果的 exact bucket accuracy、low-score min recall、min binary accuracy 都需要 `>= 82%`。当前 `acceptance/benchmark_claude47_final_default/metrics.json` 结果为 exact bucket accuracy `83.33%`、low-score min recall `96.43%`、min binary accuracy `95.83%`。Pangu gpt-5.5 作为对照输出分数、bucket、遮挡命中和差异分析。

注意：bobo 确认版基准的人工标签混合 desktop/mobile 目标面。验收命令会渲染 desktop+mobile 首屏，但每个 HTML 只选择一个 canonical viewport 评分，`adaptive_viewports=off`，不是双端取低分。

## 包内结构

- `config/aesthetic-v4.env.example`: 模型配置模板
- `input_html/`: 示例 HTML 输入
- `pipeline/run_aesthetic_v4.sh`: 一键流程
- `pipeline/scripts/`: 渲染、打分、报告脚本
- `tools/build_handoff_zip.py`: 交付 zip 构建脚本，会排除本地私有 env、缓存和依赖目录
- `docs/AESTHETIC_V4_WORKFLOW.md`: 输入、模型、输出、聚合口径

## 打包

```bash
python3 tools/build_handoff_zip.py
```

默认输出到 `/Volumes/TU820/aesthetic/outputs/aesthetic-v4-pangu-claude47-handoff-YYYYMMDD.zip`。脚本会跳过 `config/aesthetic-v4.env`，zip 内只包含 `config/aesthetic-v4.env.example`。

## 评分口径

aesthetic-v4 是 VLM Judge：大模型看渲染截图，并按六轴 rubric、分档规则、ZERO_DEFECT 结构化硬缺陷和设计师评审口吻输出分数与解释。遮挡/重叠不会把六轴无条件全清零；相关 affected_axes 打到 0 或极低，最终分由固定权重加权得到。

遮挡类型固定归一为：

- `text_text`: 文字和文字互相重叠
- `text_graphic`: 文字被图片、图标、图形、图表遮挡
- `control_nav`: 按钮、输入框、导航、底部栏遮挡核心内容
- `layer_zindex`: 浮层、卡片、图层顺序导致核心内容遮挡
- `clipping_crop`: 裁切、溢出、截断导致核心内容不可读

它不是静态特征主 gate，也不是训练模型权重。它的目标是给 HTML 生成结果做可解释的设计质量初评。
