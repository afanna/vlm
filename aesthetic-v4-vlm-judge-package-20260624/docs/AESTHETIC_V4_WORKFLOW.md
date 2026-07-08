# aesthetic-v4 VLM Judge 工作流

## 输入

- 输入对象：一个 HTML 文件，或一个包含多个 `.html` / `.htm` 的目录。
- 可选 sidecar：同名 `.meta.json`、`metadata.json` 或 `query_instruction.json`。
- sidecar 只用于记录样本说明、query、产品标题和目标视口；当前评分证据仍以截图为准。

## 截图

`render_screenshots.mjs` 会把 HTML 渲染为截图：

- 默认截图模式：`AESTHETIC_V4_SCREENSHOT_MODE=first_view`
- desktop 首屏：`1440x900`，deviceScaleFactor `1`。
- 默认视口：mobile。mobile 首屏：`390x844`，deviceScaleFactor `2`，输出图约 `780x1688`。
- 长图是显式开关：`AESTHETIC_V4_SCREENSHOT_MODE=fullpage`。full-page 使用 `resize_viewport_then_clip`：先把 viewport 高度扩到文档截图高度，再截长图，避免 fixed/sticky footer 被传统 fullPage 截图冻结在首屏位置造成假遮挡。
- 默认 `--capture-scroll-width`，用真实页面 scrollWidth 暴露横向溢出、裁切和响应式失败。
- 日常快评默认只跑一个 canonical viewport；需要桌面/移动或长图完整验收时再打开对应开关。

## 模型输入

模型实际收到：

- screenshot image
- `sample_id`
- viewport
- screenshot width / height
- rubric version
- aesthetic-v4 prompt：六轴评分、分档规则、ZERO_DEFECT 结构化硬缺陷、设计师评审口吻要求
- quality config：`adaptive_viewports`、`score_breakdown`、`designer_review`，以及固定的 `occlusion_overlap_check=always_on`

默认模型入口是 Pangu OpenAI-compatible 网关里的 `claude-opus-4-7-thinking`。验收时可以额外用同一 Pangu 网关的 `gpt-5.5` 跑对照，比较 `score_100`、bucket、遮挡命中和 rationale 差异；对照结果不改变交付默认入口。

模型不应该使用文件名、来源模型、人工标签、后验指标或人工修正结果作为评分证据。

长图评分时，模型仍只按截图可见内容判断。首屏/top screen 是主视觉和第一印象证据，下方内容用于检查完成度、信息延续、响应式和渲染缺陷，不按“把所有下方区块平均”来稀释首屏质量。

移动端固定底部导航、tab bar、safe-area chrome 属于正常 app 结构。它可能浮在滚动内容上方或遮住页面底部一点内容；这本身不触发 ZERO_DEFECT。只有当底部导航遮住核心文字、核心按钮或关键数据，且当前截图没有合理底部留白导致核心内容不可稳定阅读或操作时，才按遮挡问题结构化扣分。

## 质检开关

- `adaptive_viewports=off`: 评分阶段只跑默认或指定 viewport。
- `adaptive_viewports=on`: 评分阶段跑已渲染的 desktop+mobile，页面最终分取低分。
- `adaptive_viewports=auto`: 先跑 canonical viewport；响应式风险、低置信、临界分数、遮挡风险或正式报告模式下补跑另一端，补跑后取低分。
- `score_breakdown=on`: 在 JSON/report 中展示总分、六轴、固定权重、weighted contribution 和遮挡影响。
- `score_breakdown=off`: 允许报告层隐藏细分项；内部 scoring、axis_scores 和 final_score 不变。
- `designer_review=on`: 额外输出设计师口吻 pros/cons/suggestions。
- `designer_review=off`: 不输出长评；final_score 不受影响。

`occlusion_overlap_check=always_on` 是固定策略，不暴露关闭入口。命中遮挡/重叠时不修改 rubric 权重，只降低对应 `axis_scores`，再通过固定权重加权进入总分。

遮挡类型统一为：

- `text_text`: 文字和文字互相重叠。
- `text_graphic`: 文字被图片、图标、图形、图表遮挡。
- `control_nav`: 按钮、输入框、导航、底部栏遮挡核心内容。
- `layer_zindex`: 浮层、卡片、图层顺序导致核心内容遮挡。
- `clipping_crop`: 裁切、溢出、截断导致核心内容不可读。

## 输出

`scores.jsonl` 是内部 raw scoring 记录，保留 0-8 score 以便调试和兼容报告。对外交付使用 `outputs/json/*.json`，由 `export_clean_html_score_json.py` 从 raw records 导出。

每条正式 clean JSON 输出：

- `aesthetic_rubric`: 完整六轴 rubric
- `score.score_100`: 百分制最终分
- `score.axis_breakdown[].axis_score_100`
- `score.axis_breakdown[].weight`
- `score.axis_breakdown[].weighted_contribution_100`
- `score.score_100 = sum(weighted_contribution_100)`
- 设计师口吻 `rationale`
- `quality_config`
- `occlusion.detected/status/types/findings/affected_axes/score_impact`
- `views[].score_100` 和截图路径

正式 clean JSON 不输出 `score_8`、重复 `rationale`、`weighted_score_from_axis_scores`、`occlusion_weighted_loss_from_max` 等内部旧字段。

## 聚合

默认 package 配置为 `adaptive_viewports=off`，只打一个 canonical mobile 首屏。页面最终分就是该截图分数：

```text
aggregate_strategy = single_canonical_screenshot_score
```

如果显式打开 `adaptive_viewports=on`，desktop/mobile 都打分，页面最终分取两端最低分；这用于正式响应式复核，不是日常默认。
