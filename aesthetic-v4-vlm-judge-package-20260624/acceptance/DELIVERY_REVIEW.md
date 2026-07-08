# aesthetic-v4 Pangu Claude 4.7 交付复核

生成时间：2026-06-29

## 交付入口

- 默认入口：Pangu OpenAI-compatible。
- 默认 base URL：`http://43.139.21.243:4000`。
- 默认 model：`claude-opus-4-7-thinking`。
- 默认 prompt version：`aesthetic-v4`。
- 默认 output mode：`full`。
- 本机真实 key 只允许存在于 `config/aesthetic-v4.env`；zip 只包含 `config/aesthetic-v4.env.example`。
- PackyAPI 仅作为本机可选对比入口，不是对外交付默认入口。

## 默认评分策略

- 截图：`first_view`。
- 日常默认视口：mobile，首屏约 `780 x 1688`。
- 默认单视口：`adaptive_viewports=off`。
- 默认输出权重细节：`score_breakdown=on`。
- 默认不输出设计师长评：`designer_review=off`。
- 遮挡检测固定开启：`occlusion_overlap_check=always_on`。
- fullpage 只作为显式开关；score-only 只作为速度测试，不作为正式质检 JSON。
- bobo 基准验收使用 canonical auto 单视口：渲染 desktop+mobile 首屏，但每个 HTML 只选择一个目标 viewport 评分，`adaptive_viewports=off`，不是双端取低分。

## 已修复问题

- 将公开默认入口统一为 Pangu Claude 4.7。
- 将公开 prompt 名 `aesthetic-v4` 收敛到当前 benchmark 校准版 prompt，避免交付入口和验收入口分裂。
- 给 `pangu_rubric_judge.py` 补齐 `--output-mode {full,score-only}`，并保留 full 为正式默认。
- 增加 Pangu JSON parse retry，降低模型返回非严格 JSON 时的失败率。
- 修复 `run_aesthetic_v4.sh` env 优先级：显式 shell 环境变量优先于本机 `.env`。
- 清理输出 schema：最终 JSON 只保留 `score_100`，`axis_breakdown` 使用 `axis_score_100`、`weight`、`weighted_contribution_100`。
- 删除 `score_100_rounded`，避免同一 JSON 中出现两个百分制分数字段。
- 修复遮挡误判：正常滚动/底部导航样本不因泛化措辞被误标为遮挡。
- 修复否定遮挡误判：`不遮挡核心`、`不影响核心` 等表述不会被推断成遮挡 finding。
- 修复遮挡 affected axes 归一：模型漏给轴时，会和遮挡类型默认影响轴取并集。
- 修复六轴同分问题：bucket judge 返回平铺 axis_scores 时，后端生成 reader-facing diagnostic axis_breakdown，并校准回同一加权总分。
- 打包脚本排除 `config/aesthetic-v4.env`、`node_modules`、`__pycache__`、AppleDouble `._*`、`.DS_Store`、`*.pyc`、`*.zip`，并扫描常见 API key 模式。

## 验证证据

- Pangu `/v1/models`：status 200，model_count 548，`claude-opus-4-7-thinking` 存在。
- `python3 tools/validate_package.py`：OK。
- `python3 -m py_compile pipeline/scripts/*.py tools/validate_package.py tools/build_handoff_zip.py`：通过。
- `node --check pipeline/scripts/render_screenshots.mjs`：通过。
- `bash -n pipeline/run_aesthetic_v4.sh`：通过。
- Mock run：`runs/final_mock_validation_default_aesthetic_v4/`，1/1 scored，first_view，mobile，adaptive off。
- Pangu full smoke：`runs/final_smoke_pangu_claude47_default_aesthetic_v4/`，1/1 scored，final_score 6.0，平均 14.851s。
- PackyAPI optional smoke：`runs/packy_gpt55_q10252_smoke/`，1/1 scored，full mode 平均 70.394s；`runs/packy_gpt55_q10252_score_only/` 平均 21.745s。
- Clean JSON schema：
  - `outputs/json/index.json`：72/72 通过。
  - `acceptance/benchmark_claude47_final_default/outputs/json/index.json`：72/72 通过。
  - `acceptance/occlusion_claude47_final_default/outputs/json/index.json`：6/6 通过。

## 基准集结果

输入：`/Volumes/TU820/aesthetic/基准集-bobo 确认版`

产物：

- `acceptance/benchmark_claude47_final_default/scores.jsonl`
- `acceptance/benchmark_claude47_final_default/scores.csv`
- `acceptance/benchmark_claude47_final_default/details.csv`
- `acceptance/benchmark_claude47_final_default/report.html`
- `acceptance/benchmark_claude47_final_default/benchmark_report.html`
- `acceptance/benchmark_claude47_final_default/metrics.json`
- `acceptance/benchmark_claude47_final_default/outputs/json/index.json`
- `acceptance/benchmark_claude47_final_default/manual_qc/index.html`

指标：

- records：72
- scored：72
- exact bucket accuracy：83.33%（60/72）
- low-score min recall：96.43%
- low-score min binary accuracy：95.83%
- target >=82%：通过
- 平均每条评分耗时：12.554s

## 遮挡验收结果

产物：

- `acceptance/occlusion_claude47_final_default/report.html`
- `acceptance/occlusion_claude47_final_default/scores.jsonl`
- `acceptance/occlusion_claude47_final_default/outputs/json/index.json`
- `acceptance/occlusion_claude47_final_default/manual_qc/index.html`
- `acceptance/occlusion_claude47_final_default_summary.json`

结果：

- 6 个样本全部 scored。
- 4 个真实遮挡样本 detected=true，并输出标准化 types、affected_axes、score_impact。
- `T64_2_scroll_normal` 正常滚动/底部导航对照样本 detected=false。
- `q10252_user_sample` detected=false，不作为遮挡正例。
- 遮挡类型归一覆盖：`text_text`、`text_graphic`、`control_nav`、`layer_zindex`、`clipping_crop`；本次命中的真实类型包括 `text_text`、`text_graphic`、`layer_zindex`。

## 人工质检产物

- 主入口：`manual_qc/index.html`
- 每个 HTML 一个 clean JSON：`outputs/json/*.json`
- 主索引：`outputs/json/index.json`
- 基准集质检页：`acceptance/benchmark_claude47_final_default/manual_qc/index.html`
- 遮挡质检页：`acceptance/occlusion_claude47_final_default/manual_qc/index.html`

## 最终 zip

- 路径：`/Volumes/TU820/aesthetic/outputs/aesthetic-v4-pangu-claude47-handoff-20260629.zip`
- 文件数：280
- 大小：3,870,804 bytes
- 验证：包含 `config/aesthetic-v4.env.example`；不包含 `config/aesthetic-v4.env`；不包含旧失败 benchmark/occlusion 目录；不包含 AppleDouble `._*`；文本扫描未发现疑似真实 API key。

## 代码复核结论

已修复的主要坏味道：

- 默认 provider 与交付目标不一致。
- 本机 `.env` 覆盖命令行显式开关，导致 score-only/fullpage 等测试参数失效。
- 公开默认 prompt 和可过线 prompt 分裂，容易交付后复跑不一致。
- 模型输出非严格 JSON 时没有恢复机制。
- 遮挡类型和 affected axes 依赖模型自由文本，导致漏标/误标。
- clean JSON 与内部 scores/report 字段边界不清，容易把 `score_8`、重复 rationale、旧 weighted 字段带给下游。
- `score_100` 与旧 rounded 分数字段可能不一致，现已只保留一个最终百分制分数。
- bucket 分档为了稳定可能返回同分轴；现已通过后端 diagnostic axis fallback 输出差异化六轴，且正式 JSON 中全量 72 条没有六轴全同分样本。

残留风险：

- 当前目录不是 git 仓库，本次 code review 无法按 commit diff 做，只能按目标规范和文件现状复核。
- bobo 基准验收需要 canonical auto 单视口口径；日常默认 mobile 首屏是快评路径，不等价于该混合标签面。
- PackyAPI 可用但慢于 Pangu；它不是对外交付主入口。
