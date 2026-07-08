#!/usr/bin/env python3
"""aesthetic-v4 rubric prompt factory.

This package intentionally exposes only the aesthetic-v4 prompt profile.
"""

from __future__ import annotations

import json
import re
from typing import Any


WEIGHTS: dict[str, float] = {
    "visual_impact_originality": 0.30,
    "composition_hierarchy": 0.20,
    "typography": 0.15,
    "color_material": 0.15,
    "detail_finish": 0.15,
    "basic_usability": 0.05,
}

OCCLUSION_OVERLAP_CHECK = "always_on"
QUALITY_SWITCHES_DEFAULT = {
    "adaptive_viewports": "off",
    "score_breakdown": "on",
    "designer_review": "off",
    "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
}
ADAPTIVE_VIEWPORTS_CHOICES = {"off", "on", "auto"}
ON_OFF_CHOICES = {"off", "on"}
OCCLUSION_TYPES = {
    "text_text",
    "text_graphic",
    "control_nav",
    "layer_zindex",
    "clipping_crop",
    "unknown",
}
OCCLUSION_SEVERITIES = {"minor", "moderate", "severe", "blocking"}
SEVERITY_RANK = {"minor": 1, "moderate": 2, "severe": 3, "blocking": 4}
OCCLUSION_SEVERITY_AXIS_CAPS = {"minor": 6.0, "moderate": 4.0, "severe": 2.0, "blocking": 0.0}
OCCLUSION_TYPE_AXES = {
    "text_text": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "text_graphic": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "control_nav": ["basic_usability", "composition_hierarchy", "detail_finish"],
    "layer_zindex": ["composition_hierarchy", "detail_finish", "basic_usability"],
    "clipping_crop": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "unknown": ["composition_hierarchy", "detail_finish"],
}


def normalize_quality_switches(raw: Any) -> dict[str, str]:
    config = raw if isinstance(raw, dict) else {}
    adaptive = str(config.get("adaptive_viewports") or QUALITY_SWITCHES_DEFAULT["adaptive_viewports"]).strip().lower()
    score_breakdown = str(config.get("score_breakdown") or QUALITY_SWITCHES_DEFAULT["score_breakdown"]).strip().lower()
    designer_review = str(config.get("designer_review") or QUALITY_SWITCHES_DEFAULT["designer_review"]).strip().lower()
    if adaptive not in ADAPTIVE_VIEWPORTS_CHOICES:
        adaptive = QUALITY_SWITCHES_DEFAULT["adaptive_viewports"]
    if score_breakdown not in ON_OFF_CHOICES:
        score_breakdown = QUALITY_SWITCHES_DEFAULT["score_breakdown"]
    if designer_review not in ON_OFF_CHOICES:
        designer_review = QUALITY_SWITCHES_DEFAULT["designer_review"]
    return {
        "adaptive_viewports": adaptive,
        "score_breakdown": score_breakdown,
        "designer_review": designer_review,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
    }


def quality_instruction_block(request: dict[str, Any]) -> str:
    config = normalize_quality_switches(request.get("quality_config"))
    designer_line = (
        "- designer_review=on：额外输出 designer_review，包含 pros / cons / suggestions 三组简短设计师建议。"
        if config["designer_review"] == "on"
        else "- designer_review=off：不要输出长篇 designer_review；final score 和 axis_scores 不受该开关影响。"
    )
    score_breakdown_line = (
        "- score_breakdown=on：输出 occlusion_score_impact；权重固定，只通过降低对应 axis_scores 体现扣分。"
        if config["score_breakdown"] == "on"
        else "- score_breakdown=off：内部仍按固定权重和 axis_scores 算分，但报告层可隐藏详细分项。"
    )
    return f"""
质量开关：
{json.dumps(config, ensure_ascii=False, sort_keys=True)}

遮挡/重叠检查是强制常开，不是可关闭选项：
- occlusion_overlap_check=always_on。评分前必须检查文字/文字、文字/图片或图标、按钮/输入框/导航、固定底部栏、图表或正文被遮挡。
- 如果发现遮挡或重叠，不要修改 rubric_weights；必须降低受影响的 axis_scores，并在 occlusion_findings 里写出 type / severity / target / evidence / affected_axes。
- occlusion_findings.type 只能使用：text_text、text_graphic、control_nav、layer_zindex、clipping_crop、unknown。
- 受影响轴按 severity 设上限：minor 最高 6.0，moderate 最高 4.0，severe 最高 2.0，blocking 必须为 0.0。
- occlusion_score_impact 必须能说明固定权重下的影响：对应 axis 的 score、weight、weighted_contribution 和 weighted_loss_from_max。
- severe/blocking 的核心阅读或核心操作失败必须标记为结构化硬缺陷；blocking 且核心内容不可读/不可操作时 rationale 以 ZERO_DEFECT: 开头。
- ZERO_DEFECT 不等于六轴全 0。必须按遮挡类型填写 affected_axes，并把这些相关 axis_scores 打到 0 或极低；未受影响的视觉/色彩等轴继续按截图可见质量评分。最终 score 必须由固定权重下的 axis_scores 加权得到。
{score_breakdown_line}
{designer_line}
""".strip()


def _short_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def clamp_score(value: Any) -> float:
    score = round(float(value), 1)
    return max(0.0, min(8.0, score))


def normalize_occlusion_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
    aliases = {
        "text": "text_text",
        "text_overlap": "text_text",
        "text_text_overlap": "text_text",
        "text_on_text": "text_text",
        "text_image": "text_graphic",
        "text_image_icon": "text_graphic",
        "text_on_image": "text_graphic",
        "text_icon": "text_graphic",
        "image_text": "text_graphic",
        "graphic": "text_graphic",
        "chart": "text_graphic",
        "button": "control_nav",
        "button_blocked": "control_nav",
        "input": "control_nav",
        "input_blocked": "control_nav",
        "nav": "control_nav",
        "navigation": "control_nav",
        "interactive_blocked": "control_nav",
        "fixed_footer_blocking": "control_nav",
        "footer": "control_nav",
        "bottom_bar": "control_nav",
        "fixed_footer": "control_nav",
        "tab_bar": "control_nav",
        "zindex": "layer_zindex",
        "z_index": "layer_zindex",
        "layer": "layer_zindex",
        "overlay": "layer_zindex",
        "body": "layer_zindex",
        "content_blocked": "layer_zindex",
        "crop": "clipping_crop",
        "cropping": "clipping_crop",
        "clip": "clipping_crop",
        "clipping": "clipping_crop",
        "overflow": "clipping_crop",
        "truncated": "clipping_crop",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in OCCLUSION_TYPES else "unknown"


def normalize_occlusion_severity(value: Any, *, score: float | None = None, rationale: str = "") -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "low": "minor",
        "mild": "minor",
        "light": "minor",
        "medium": "moderate",
        "major": "severe",
        "critical": "blocking",
        "zero_defect": "blocking",
        "hard_zero": "blocking",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in OCCLUSION_SEVERITIES:
        return normalized
    text = rationale.casefold()
    if rationale.startswith("ZERO_DEFECT:"):
        return "blocking"
    if _contains_any(text, ("不可稳定阅读", "不可读", "无法辨认", "无法操作", "核心操作失败")):
        return "severe"
    if _contains_any(text, ("仍可读", "轻微", "局部", "粗糙感")):
        return "minor"
    if score is not None and score <= 2.0:
        return "severe"
    return "moderate"


def default_axes_for_occlusion(occlusion_type: str, severity: str) -> list[str]:
    del severity
    return list(OCCLUSION_TYPE_AXES.get(occlusion_type, OCCLUSION_TYPE_AXES["unknown"]))


def normalize_affected_axes(value: Any, occlusion_type: str, severity: str) -> list[str]:
    axes: list[str] = []
    if isinstance(value, list):
        for item in value:
            axis = str(item or "").strip()
            if axis in WEIGHTS and axis not in axes:
                axes.append(axis)
    for axis in default_axes_for_occlusion(occlusion_type, severity):
        if axis not in axes:
            axes.append(axis)
    return axes


def describes_non_occlusion(text: str) -> bool:
    return _contains_any(
        text,
        (
            "不遮挡",
            "未遮挡",
            "没有遮挡",
            "无遮挡",
            "不重叠",
            "无重叠",
            "不影响核心",
            "未影响核心",
            "不影响阅读",
            "不影响操作",
            "并未遮挡",
        ),
    )


def infer_occlusion_findings_from_rationale(
    rationale: str,
    *,
    score: float | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    text = rationale.casefold()
    if describes_non_occlusion(text) and not rationale.startswith("ZERO_DEFECT:"):
        return []
    has_issue = _contains_any(
        text,
        ("重叠", "覆盖", "遮挡", "遮住", "挡住", "裁切", "溢出", "不可读", "被压", "压在", "压到"),
    )
    if _contains_any(text, ("压住版面", "视觉系统缺席", "图表缺位", "chart 在截图中完全缺位", "素材缺失", "内容缺失")) and not _contains_any(
        text,
        ("重叠", "覆盖", "遮挡", "遮住", "挡住", "裁切", "溢出", "不可读", "被压", "压在", "压到"),
    ):
        has_issue = False
    if not has_issue and not rationale.startswith("ZERO_DEFECT:"):
        return []
    if rationale.startswith("ZERO_DEFECT:"):
        severity = "blocking"
    elif _contains_any(text, ("仍可读", "整体仍可读", "轻微")):
        severity = "minor"
    elif _contains_any(text, ("粗糙感", "底部列表还有被输入栏遮挡")):
        severity = "moderate"
    elif _contains_any(text, ("明显覆盖", "核心", "不可稳定阅读", "不可读", "严重")):
        severity = "severe"
    elif score is not None and score <= 1.5:
        severity = "severe"
    else:
        severity = "moderate"

    if _contains_any(text, ("图表", "chart", "折线图", "柱状图", "表格", "正文")):
        occlusion_type = "text_graphic"
        target = "chart/body content"
    elif _contains_any(text, ("底部固定", "固定底部", "bottom", "footer", "tab bar", "tabbar", "底部导航", "底部输入栏")):
        occlusion_type = "control_nav"
        target = "fixed footer or bottom bar"
    elif _contains_any(text, ("图片", "图像", "图形", "图标", "背景", "食物", "复杂")):
        occlusion_type = "text_graphic"
        target = "text over image/icon"
    elif _contains_any(text, ("按钮", "button", "输入", "input", "导航", "nav", "tab", "操作")):
        occlusion_type = "control_nav"
        target = "interactive control"
    elif _contains_any(text, ("文字", "标题", "正文", "说明", "列表")):
        occlusion_type = "text_text"
        target = "text block"
    else:
        occlusion_type = "unknown"
        target = "visible content"

    finding = {
        "type": occlusion_type,
        "severity": severity,
        "target": target,
        "evidence": _short_text(rationale),
        "affected_axes": default_axes_for_occlusion(occlusion_type, severity),
    }
    if viewport:
        finding["viewport"] = viewport
    return [finding]


def normalize_occlusion_findings(
    payload: dict[str, Any],
    *,
    rationale: str | None = None,
    axis_scores: dict[str, float] | None = None,
    score: float | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    del axis_scores
    raw = payload.get("occlusion_findings")
    findings: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            evidence = _short_text(item.get("evidence") or item.get("reason") or rationale)
            if describes_non_occlusion(evidence.casefold()) and not (rationale or "").startswith("ZERO_DEFECT:"):
                continue
            occlusion_type = normalize_occlusion_type(item.get("type"))
            severity = normalize_occlusion_severity(item.get("severity"), score=score, rationale=evidence or rationale or "")
            finding = {
                "type": occlusion_type,
                "severity": severity,
                "target": _short_text(item.get("target") or "visible content", 120),
                "evidence": evidence,
                "affected_axes": normalize_affected_axes(item.get("affected_axes"), occlusion_type, severity),
            }
            item_viewport = item.get("viewport") or viewport
            if item_viewport:
                finding["viewport"] = str(item_viewport)
            findings.append(finding)
    inferred = infer_occlusion_findings_from_rationale(rationale or "", score=score, viewport=viewport)
    if not findings:
        findings = inferred
    return findings


def highest_severity(values: list[str]) -> str:
    if not values:
        return "minor"
    return max(values, key=lambda item: SEVERITY_RANK.get(item, 0))


def build_occlusion_score_impact(axis_scores: dict[str, float], findings: list[dict[str, Any]]) -> dict[str, Any]:
    weighted_score = weighted_axis_score(axis_scores)
    axis_to_findings: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        axes = finding.get("affected_axes") if isinstance(finding.get("affected_axes"), list) else []
        for axis in axes:
            if axis in WEIGHTS:
                axis_to_findings.setdefault(axis, []).append(finding)
    affected_axes: list[dict[str, Any]] = []
    for axis in WEIGHTS:
        linked = axis_to_findings.get(axis, [])
        if not linked:
            continue
        axis_score = clamp_score(axis_scores.get(axis, 0.0))
        weight = WEIGHTS[axis]
        affected_axes.append(
            {
                "axis": axis,
                "score": axis_score,
                "weight": weight,
                "weighted_contribution": round(axis_score * weight, 3),
                "weighted_loss_from_max": round((8.0 - axis_score) * weight, 3),
                "severity": highest_severity([str(finding.get("severity")) for finding in linked]),
                "finding_types": sorted({str(finding.get("type")) for finding in linked}),
            }
        )
    return {
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "scoring_rule": "rubric_weights stay fixed; occlusion lowers the affected axis_scores.",
        "rubric_weights": WEIGHTS,
        "weighted_score_from_axis_scores": round(weighted_score, 3),
        "occlusion_weighted_loss_from_max": round(sum(item["weighted_loss_from_max"] for item in affected_axes), 3),
        "affected_axes": affected_axes,
    }


def weighted_axis_score(axis_scores: dict[str, float]) -> float:
    weighted = sum(clamp_score(axis_scores.get(axis, 0.0)) * weight for axis, weight in WEIGHTS.items())
    return clamp_score(weighted)


def calibrate_axis_scores_to_total(axis_scores: dict[str, float], target_score: float) -> dict[str, float]:
    """Preserve axis differences while making their weighted total round to target_score."""
    target = clamp_score(target_score)
    adjusted = {axis: clamp_score(axis_scores.get(axis, target)) for axis in WEIGHTS}
    for _ in range(8):
        current = weighted_axis_score(adjusted)
        residual = target - current
        if abs(residual) < 0.05:
            break
        if residual > 0:
            eligible = [axis for axis, value in adjusted.items() if value < 8.0]
        else:
            eligible = [axis for axis, value in adjusted.items() if value > 0.0]
        if not eligible:
            break
        eligible_weight = sum(WEIGHTS[axis] for axis in eligible)
        if eligible_weight <= 0:
            break
        delta = residual / eligible_weight
        for axis in eligible:
            adjusted[axis] = clamp_score(adjusted[axis] + delta)
    return adjusted


def axis_scores_are_uniform(axis_scores: dict[str, float]) -> bool:
    values = [clamp_score(axis_scores.get(axis, 0.0)) for axis in WEIGHTS]
    return bool(values) and max(values) - min(values) < 0.05


def fallback_axis_scores_for_uniform_bucket(target_score: float, rationale: str) -> dict[str, float]:
    """Derive non-uniform axis scores when a bucket judge returns flat axes."""
    target = clamp_score(target_score)
    scores = {
        "visual_impact_originality": target + 0.2,
        "composition_hierarchy": target,
        "typography": target - 0.2,
        "color_material": target + 0.1,
        "detail_finish": target - 0.1,
        "basic_usability": target + 0.3,
    }
    text = rationale or ""
    if _contains_any(text, ("模板", "常见", "普通", "默认", "通用", "缺乏独特", "不够独特")):
        scores["visual_impact_originality"] -= 0.3
        scores["detail_finish"] -= 0.2
    if _contains_any(text, ("品牌", "视觉", "插画", "3D", "产品图", "记忆点", "主题")):
        scores["visual_impact_originality"] += 0.2
    if _contains_any(text, ("排版", "字体", "文字", "标题", "换行", "拥挤", "可读")):
        scores["typography"] -= 0.3
    if _contains_any(text, ("层级", "结构", "布局", "间距", "留白", "卡片")):
        scores["composition_hierarchy"] += 0.1
    if _contains_any(text, ("色", "材质", "渐变", "光影", "深色", "主题色")):
        scores["color_material"] += 0.2
    if _contains_any(text, ("粗糙", "拼装", "细节", "polish", "组件", "默认控件")):
        scores["detail_finish"] -= 0.3
    if _contains_any(text, ("遮挡", "重叠", "不可读", "操作失败", "裁切", "溢出")):
        scores["basic_usability"] -= 0.6
        scores["composition_hierarchy"] -= 0.3
    scores = {axis: clamp_score(value) for axis, value in scores.items()}
    return calibrate_axis_scores_to_total(scores, target)


def apply_blocking_occlusion_axis_penalties(
    axis_scores: dict[str, float],
    findings: list[dict[str, Any]],
) -> dict[str, float]:
    return apply_occlusion_axis_penalties(axis_scores, findings, blocking_only=True)


def apply_occlusion_axis_penalties(
    axis_scores: dict[str, float],
    findings: list[dict[str, Any]],
    *,
    blocking_only: bool = False,
) -> dict[str, float]:
    updated = dict(axis_scores)
    for finding in findings:
        severity = str(finding.get("severity") or "moderate")
        if blocking_only and severity != "blocking":
            continue
        cap = OCCLUSION_SEVERITY_AXIS_CAPS.get(severity)
        if cap is None:
            continue
        axes = finding.get("affected_axes") if isinstance(finding.get("affected_axes"), list) else []
        for axis in axes:
            if axis in updated:
                updated[axis] = min(clamp_score(updated[axis]), cap)
    return updated


def normalize_designer_review(value: Any) -> dict[str, list[str]] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = _short_text(value, 500)
        return {"pros": [], "cons": [text] if text else [], "suggestions": []}
    if not isinstance(value, dict):
        return None
    review: dict[str, list[str]] = {}
    for key in ("pros", "cons", "suggestions"):
        items = value.get(key)
        if isinstance(items, list):
            review[key] = [_short_text(item, 240) for item in items if _short_text(item, 240)]
        elif isinstance(items, str):
            text = _short_text(items, 240)
            review[key] = [text] if text else []
        else:
            review[key] = []
    return review if any(review.values()) else None


def prompt_common_context(request: dict[str, Any]) -> tuple[str, str]:
    weight_lines = "\n".join(f"- {key}: {weight:.2f}" for key, weight in WEIGHTS.items())
    image = request.get("image") if isinstance(request.get("image"), dict) else {}
    meta = f"""
样本信息：
- viewport: {image.get("viewport")}
- screenshot_size: {image.get("width")}x{image.get("height")}
- rubric_version: {request.get("rubric_version")}

{quality_instruction_block(request)}
""".strip()
    return weight_lines, meta


def build_prompt_aesthetic_v4(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是一个严格的 UI 静态截图审美评估 judge。图片已经作为附件提供。

目标：用 aesthetic-v4 的设计师校准口径，对齐人类设计师百分位审美尺度，并准确筛出 10 分一档的质量分档。

重要：最终 JSON 的 score 是 0-8，但你必须先在内部估计 designer_score_100，然后输出：
score = designer_score_100 / 12.5
不要输出 designer_score_100，只输出 0-8 score。

必须先选唯一分档，再在档内给具体分数。不要先给一个温和中间分。

完整分档定义：
- [0,10)：失败/极低质。空白、严重错乱、核心 UI 未完成、基本不可读、默认控件堆叠，审美上接近不可用。
- [10,20)：低质模板。能看出功能意图，但主要是默认表单、默认按钮、普通白卡片、廉价图标、简单圆环、普通渐变背景；没有真正视觉系统和记忆点。
- [20,30)：低分但略完整。比默认 demo 完整，但仍明显模板化、粗糙、空洞；有基本布局但对齐、比例、字体、留白、组件状态仍显粗糙。
- [30,40)：普通偏低。页面能成立，但设计语言常见，专业感不足；字体系统普通、构图安全、色彩无明显策略、组件像通用模板。
- [40,50)：普通。完整、有一定整理，但仍是常见 AI UI / 模板范式，视觉记忆点弱；不能因为“完整、干净、能用”直接给 50+。
- [50,60)：较好。明显强于普通模板，有稳定视觉系统和较完整细节；但主视觉、品牌系统、非模板化记忆点或局部 polish 还不够成熟。
- [60,70)：高分。具备强视觉焦点和成熟氛围，是少数优秀样本；但还未达到真实上线级优秀或强设计师样本。
- [70,80)：优秀/上线级。设计师认可的高完成度样本。必须有稳定信息架构、明确主题转译、成熟组件系统和真实上线质感。
- [80,100]：顶级设计站级别。需要非常强的独有品牌资产、突破性构图、可延展设计系统、高级字体/材质和顶级精修。

六个评分轴和权重：
{weight_lines}

评分流程：
1. 先检查 ZERO_DEFECT。只要核心阅读或核心操作失败，先标记结构化硬缺陷，不用视觉加分掩盖问题。
2. 先命中唯一百分制分档，再按六轴给 0-8 轴分，并输出总 score。
3. 如果存在遮挡/重叠硬缺陷，只把 affected_axes 对应的 axis_scores 打到 0 或极低；未受影响的视觉冲击、色彩材质等轴继续按截图可见质量评分。最终 score 必须由六轴固定权重加权得到，不能用全局硬 0 覆盖轴分。
4. rationale 必须用设计师评审口吻写出：命中哪个分档、优点为什么成立、卡住更高档的问题是什么、证据来自截图哪个可见模块。控制在 120-180 个中文字，短而具体。

ZERO_DEFECT 结构化硬缺陷规则：
- 核心文字区域存在明显文字覆盖、互相重叠、多行压在一起、行距压缩到不可稳定阅读。
- 文本被图表、卡片、按钮、导航、浮层、边界或其他 UI 元素遮挡。
- 主标题、正文、表格、列表、说明、关键数据、核心按钮文字发生裁切、横向溢出、缩放错误或响应式崩坏，导致核心内容不可读。
- 右侧/左侧/底部详情面板里密集文字发生堆叠、越界或互相覆盖；不能把它轻描淡写为“信息密度高”。
- 页面局部有强视觉图形、材质或氛围，但核心阅读区域失败，仍然必须标记 ZERO_DEFECT 并重扣相关轴。
- 移动端固定底部导航/tab bar/safe-area chrome 是正常 app 结构；它浮在滚动内容上或遮住页面最底部一点内容，本身不是 ZERO_DEFECT。只有当它遮住核心文字、核心按钮或关键数据，并且当前截图中没有合理底部留白/滚动空间导致核心内容不可稳定阅读或操作时，才按遮挡结构化重扣。
- 触发时 rationale 必须以 "ZERO_DEFECT:" 开头并明确写出具体缺陷；occlusion_findings 必须写出 type / severity / target / evidence / affected_axes。

设计师评审口吻要求：
- rationale 是给 UI 页面/context 的设计评审，不是泛泛的用户体验评价。
- 优点和缺点都必须落到可见设计证据：视觉层级、信息架构、排版节奏、留白密度、对齐网格、字体选择、色彩/材质、组件完成度、品牌/主题一致性、视觉焦点、上线质感。
- 避免只写“好看、完整、清晰、能用、不错、普通”这类泛词；如果使用判断，必须同时说明对应的设计原因。
- 加分点要像设计师说明为什么成立；扣分点要像设计师指出哪里破坏专业感，例如默认控件痕迹、模板化范式、资产缺失、层级弱、比例失衡、留白失控、材质廉价、字体系统不统一。
- 触发 ZERO_DEFECT 时只写缺陷原因，不列优点；axis_scores 仍需保留未受影响维度的判断，方便下游知道是文字/遮挡类问题。

各分档设计师校准口径：
- ZERO_DEFECT：这是结构化硬缺陷，不是普通审美低分。核心阅读或核心操作失败时，相关轴打到 0 或极低，未受影响轴保留正常评分。
- [0,10)：页面审美上接近不可用，通常像未完成草稿或严重崩坏原型。只有至少能看出稳定功能结构且没有严重崩坏，才可能进入 [10,20)。
- [10,20)：功能意图存在，但设计系统基本没有，像课堂 demo 或默认组件拼装。只有出现明确结构整理、局部层级或一点主题化装饰，才可能进入 [20,30)。
- [20,30)：比默认 demo 完整，但仍明显模板化、粗糙、空洞。只有功能结构和视觉层级基本稳定，才可能进入 [30,40)。
- [30,40)：信息结构基本完整，但字体系统普通、构图安全、色彩无明显策略、组件像通用模板。只有整体整理度、层级、色彩和组件一致性达到普通完整 UI，才进入 [40,50)。
- [40,50)：页面干净可读、有基础网格/卡片/状态，但主视觉弱、字体/色彩保守、组件无专属语气、细节不够精修。必须有稳定视觉系统或明显主题完成度，才进入 [50,60)。
- [50,60)：层级清楚、色彩/材质统一、组件一致、主题氛围成立；但模板范式仍明显、主视觉不够强、品牌系统不足或 polish 不稳。只有强视觉焦点、统一氛围、非模板化记忆点和成熟细节同时成立，才进入 [60,70)。
- [60,70)：主视觉、构图、字体、色彩、材质、组件完成度都较强；短板通常是信息语义仍通用、品牌资产不够可延展、局部组件比例或响应式精修不足。进入 [70,80) 需要更像真实上线作品。
- [70,80)：这是设计师认可的优秀上线级样本，不是低分失败；未进 [80,100] 是因为顶级差异化、专属品牌系统、语境化结构或系统化精修还不够。必须明确写出加分成立模块，也要说明离 80+ 的设计层级差距。
- [80,100]：只有独有视觉语言、可延展品牌系统、强概念转译、高级字体/材质、精确响应式和细节密度都成立时进入。

未进入 80+ 的设计师校准口径：
- 如果分数落在 [70,80)，rationale 必须明确表达：这是设计师认可的上线级/优秀样本，不是低分失败。
- 说明“没有上 80”的原因时，必须指出“哪个设计层级没有完成到 80+”，而不是只写普通缺点。
- 推荐从这些设计层级组织扣分原因：概念转译层、品牌系统层、信息语义层、影像策展层、组件语气层、响应式重构层。
- 每个未进 80 的原因按这个结构写：可见模块 -> 设计层级 -> 专业差距 -> 为什么影响 80+。
- 不要把 [70,80) 页面为了扣分而强行说成“缺少动效亮点”。单张静态截图无法验证动效时，不得把动效作为主要扣分原因。
- 对强 image-led 页面，如果主视觉、缩略图、字体和信息层级已经成立，不能再把“依赖图片”当作低分理由；只能指出图片系统是否缺少项目间 mood 区分、品牌化处理、裁切节奏或语义化信息结构。

克制型 image-led archive/dashboard 不应被系统性低估：
- 对电影档案、摄影作品集、艺术家 archive、editorial media dashboard、影像项目目录等页面，如果核心视觉资产高质量、画面氛围统一、信息层级稳定、排版克制且组件完成度达到真实上线产品质感，不要因为结构常见就自动压到 [50,60)。
- 如果没有 ZERO_DEFECT，且满足：强 image-led 主视觉、暗色/编辑/档案氛围统一、标题/按钮/信息卡/缩略图层级清楚、细节干净、整体像真实可上线作品，则应优先考虑 [70,80)，典型可给 70-78 分，也就是 score 5.6-6.2。
- [70,80) 不要求“顶级设计站”或极强品牌符号；它表示设计师认可的优秀上线级作品。只有进入 [80,100] 才需要非常强的独有品牌资产、突破性构图或顶级精修。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.0,
  "axis_scores": {{
    "visual_impact_originality": 0.0,
    "composition_hierarchy": 0.0,
    "typography": 0.0,
    "color_material": 0.0,
    "detail_finish": 0.0,
    "basic_usability": 0.0
  }},
  "rationale": "命中 [x,y) 档：120-180 个中文字，说明可见优点、问题和相邻更高档差距。",
  "backend_meta": {{
    "judge": "aesthetic-v4",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_raw_direct_v2(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是一个严格的 UI 静态截图审美评估 judge。图片已经作为附件提供。

目标：只看截图，用 aesthetic-v4 raw/direct 口径直接估计设计师 10 分一档分层。不要使用文件名、来源目录、历史分数、样本标签或任何答案先验。

重要：最终 JSON 的 score 是 0-8，但你必须先在内部估计 designer_score_100，然后输出：
score = designer_score_100 / 12.5
不要输出 designer_score_100，只输出 0-8 score。

必须先选唯一分档，再在档内给具体分数。不要先给温和中间分，也不要用“完整、能用、清楚”替代审美质量。

分档定义和输出范围：
- [0,10)：失败/极低质。审美接近不可用；默认控件堆叠、粗糙排版、视觉系统缺失、首屏像未完成草稿。score 0.0-0.7。
- [10,20)：低质模板。功能意图能看懂，但主要是默认表单、默认按钮、普通白卡、emoji/廉价图标、简单圆环或普通渐变。score 0.8-1.5。
- [20,30)：低分但略完整。有一点结构或装饰，但仍明显模板化、默认感强、内容空洞或细节粗糙。score 1.6-2.3。
- [30,40)：普通偏低。能用、完整，比 demo 稍好，但字体/构图/色彩常见，缺少品牌化、主题化、原创性。score 2.4-3.1。
- [40,50)：普通。完整且有一定设计整理，但仍是常见 AI UI/模板范式，视觉记忆点弱。score 3.2-3.9。
- [50,60)：较好。需要稳定视觉系统、清晰层级、主题一致、细节完成度明显好于模板。score 4.0-4.7。
- [60,70)：高分。需要强视觉焦点、统一氛围、较强原创记忆点、字体/色彩/材质完成度高。score 4.8-5.5。
- [70,80)：优秀/上线级。必须明显接近设计师高分样本，有强完成度、强辨识度、成熟组件系统和真实上线质感。score 5.6-6.3。
- [80,100]：顶级设计站级别，本基准通常不用；只有独有品牌资产、突破性构图和顶级精修同时成立才进入。

低分筛选硬规则：
- 如果画面核心是“默认表单/默认列表/默认卡片 + 普通按钮”，即使完整干净，也通常只能是 [0,20) 或 [20,30)。
- To-do、计时器、抽签转盘、简单表单、普通管理列表等练习型页面，若没有强视觉语言，通常不要超过 [10,20)。
- 常见渐变、玻璃卡、emoji、圆形进度条、药丸按钮、系统默认字体不构成高分；如果只是装饰模板，通常不超过 [20,30)。
- 大面积空白如果来自内容不足、状态缺失、素材缺失或布局没填满，通常不要超过 [10,20)；不要把这种空白当作克制。
- 文字挤压、竖排异常、对齐粗糙、控件比例不协调、默认 textarea/input 痕迹明显，通常进入 [0,20)。
- 如果界面只是“能看懂功能”，但没有审美系统，必须判低分。

中高分保留规则：
- 内容少不一定低分；如果中心视觉强、氛围统一、字体/材质/光影完整，可以进入 [60,70) 或 [70,80)。
- image-led archive、摄影/电影/作品集、editorial dashboard、金融/数据 dashboard 若主视觉、缩略图、材质、信息层级和组件细节都成熟，不要因为结构常见自动压低。
- “干净、完整、有一点装饰”不等于高分。没有原创记忆点时不要给 [50,60) 以上。
- [70,80) 只给真实上线质感强的少数样本；未达到系统化品牌、成熟组件和高级细节时回到 [60,70) 或 [50,60)。

边界判定步骤：
1. 先问：它像课堂 demo/默认模板/未精修原型/低成本 AI UI 吗？如果是，优先 [0,30)。
2. 再问：是否有真正可记住的视觉语言，而不只是渐变、圆角、阴影、emoji？没有则不要超过 [40,50)。
3. 最后问：主题系统、组件细节、字体节奏、色彩材质、视觉焦点是否同时成熟？只有同时成立才进 [60,70)+。

ZERO_DEFECT 结构化硬缺陷：
- 核心文字或核心操作存在明显遮挡、重叠、裁切、横向溢出、响应式崩坏，导致不可稳定阅读或使用，必须标记 ZERO_DEFECT 并把相关轴打到 0 或极低。
- 局部视觉强但核心阅读失败，仍然按相关轴重扣；未受影响轴不要无条件清零。

Rubric 权重：
{weight_lines}

评估要求：
- 只评当前静态截图，不评价动效、hover、滚动或真实交互。
- 如果截图只有首屏，就只按首屏可见内容评分。
- 如果截图是 full-page/长图，首屏/top screen 是主视觉和第一印象证据；下方内容用于检查完成度、信息延续、响应式和渲染缺陷，不要把所有下方区块平均后稀释首屏质量。
- 移动端底部导航或 tab bar 属于 app chrome，正常浮层覆盖滚动内容底部不等于遮挡缺陷；只有遮住核心可读/可操作内容才严扣。
- 不使用来源、模型名、文件名、目录名或生成器先验。
- axis_scores 要和最终 score 的分箱一致，不能轴分高而总分低或相反。
- rationale 控制在 120-180 个中文字，必须包含：命中分档、主要可见证据、卡住更高档的原因。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.0,
  "axis_scores": {{
    "visual_impact_originality": 0.0,
    "composition_hierarchy": 0.0,
    "typography": 0.0,
    "color_material": 0.0,
    "detail_finish": 0.0,
    "basic_usability": 0.0
  }},
  "rationale": "命中 [x,y) 档：120-180 个中文字说明证据和相邻更高档差距。",
  "backend_meta": {{
    "judge": "aesthetic-v4-raw-direct-v2",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_raw_bucket_v3(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是一个严格的 UI 静态截图分档 judge。图片已经作为附件提供。

任务：只看截图，把 UI 直接分到唯一 aesthetic-v4 质量桶。不要使用文件名、目录名、来源、历史分数、样本标签或答案先验。

先选 bucket，再输出该 bucket 的固定代表分数：
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

分档标准：
- [0,10)：失败/极低质。未完成、严重粗糙、核心阅读/操作失败、默认控件堆叠且审美接近不可用。
- [10,20)：低质模板。能看出功能，但主要是默认表单/按钮/白卡/emoji/简单圆环/普通渐变，没有视觉系统。
- [20,30)：低分但略完整。有基本结构或少量装饰，但仍模板化、空洞、默认感强、细节粗糙。
- [30,40)：普通偏低。完整可用，但字体/色彩/构图常见，组件像通用模板，专业感不足。
- [40,50)：普通。整理度尚可，有基础网格/卡片/状态，但主视觉弱、记忆点弱、细节不够精修。
- [50,60)：较好。稳定视觉系统、清楚层级、主题一致、组件完成度明显强于模板，但仍有模板范式或局部短板。
- [60,70)：高分。强视觉焦点、统一氛围、较强原创记忆点、字体/色彩/材质完成度高。
- [70,80)：优秀/上线级。成熟信息架构、明确主题转译、组件系统精修、真实上线质感，属于少数强样本。
- [80,100]：顶级设计站级别；除非独有品牌资产、突破构图、高级字体/材质和顶级细节都成立，否则不用。

判定顺序：
1. 先查 ZERO_DEFECT：核心文字/按钮/数据遮挡、重叠、裁切、溢出或不可读，直接 [0,10)。
2. 再查低分模板：默认控件、练习型页面、内容空洞、emoji/渐变/玻璃卡拼装、控件比例粗糙；命中则优先 [0,30)。
3. 再查普通模板：干净完整但无专属视觉语言；通常 [30,50)。
4. 最后才考虑高分：必须有可记住的视觉语言、成熟组件、稳定排版、统一氛围和真实上线质感。

常见边界：
- “完整、清楚、能用”最多说明不是失败，不足以进入 [50,60)。
- To-do、计时器、抽签、简单表单、普通 CRUD 列表，没有强视觉语言时通常 [10,30)。
- image-led archive、摄影/电影/作品集、金融/数据 dashboard 如果主视觉、材质、字体、层级和细节成熟，可以 [60,80)。
- 高饱和渐变、emoji、圆角阴影、玻璃卡不是高分证据；只有系统化和精修成立才加分。

Rubric 权重供参考：
{weight_lines}

输出要求：
- JSON 中 score 必须是上面固定代表分数之一。
- axis_scores 可以围绕 score 上下 0.4 浮动，但必须和 bucket 一致。
- rationale 100-160 个中文字，写明命中 bucket、可见证据、为什么没有进入相邻更高 bucket。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：说明可见证据和相邻更高档差距。",
  "backend_meta": {{
    "judge": "aesthetic-v4-raw-bucket-v3",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_two_stage_v4(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是一个严格的 UI 静态截图审美分档 judge。图片已经作为附件提供。

任务：只看截图和通用 rubric，直接输出 aesthetic-v4 分档分数。不要使用文件名、目录名、来源、历史分数、样本标签或答案先验。

必须按两阶段判断：

阶段 A：先选质量族，只能四选一：
1. LOW：0-30。默认控件/练习 demo/未精修原型/内容空洞/低成本模板。
2. MID：30-50。完整可用但常见模板；有整理但没有强视觉记忆点。
3. GOOD：50-70。明显强于模板；有稳定视觉系统、主题一致、成熟层级或强视觉焦点。
4. EXCELLENT：70-80。真实上线级优秀；成熟组件系统、强主题转译、精修细节和高辨识度。

阶段 B：只在质量族内细分唯一 10 分桶：
- LOW 内：
  - [0,10)：硬缺陷、严重未完成、默认控件堆叠且审美接近不可用。
  - [10,20)：功能可辨但低质模板；默认表单/按钮/白卡/emoji/圆环/普通渐变为主体。
  - [20,30)：低分但略完整；有基本结构或装饰，但仍明显模板化、空洞或粗糙。
- MID 内：
  - [30,40)：普通偏低；完整但字体/色彩/构图常见，专业感不足。
  - [40,50)：普通；整理度尚可但主视觉弱、记忆点弱、组件不够精修。
- GOOD 内：
  - [50,60)：较好；稳定系统和主题成立，但还有模板范式或局部短板。
  - [60,70)：高分；强视觉焦点、统一氛围、较强原创记忆点、材质/字体/组件成熟。
- EXCELLENT 内：
  - [70,80)：优秀/上线级；成熟信息架构、组件系统精修、真实上线质感。
  - [80,100]：顶级设计站；本基准几乎不用，除非独有品牌资产和顶级构图/材质都成立。

固定输出分数：
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

决策准则：
- “完整、干净、能用”只够进入 MID，不够进入 GOOD。
- 默认控件、练习型页面、emoji/渐变/玻璃卡拼装、空白来自内容不足时，优先 LOW。
- 若没有可记住的视觉语言，不得进入 GOOD。
- image-led archive、作品集、金融/数据 dashboard 可以高分，但必须主视觉、字体、材质、层级和组件细节同时成熟。
- 高分样本应像真实可上线作品，而不是 AI 模板。

ZERO_DEFECT：核心文字/按钮/数据遮挡、重叠、裁切、溢出或不可读，直接 [0,10)。

Rubric 权重供参考：
{weight_lines}

输出要求：
- score 必须是固定输出分数之一。
- axis_scores 可以围绕 score 上下 0.4，但必须和最终桶一致。
- rationale 100-160 个中文字，必须写出阶段 A 质量族、最终桶、可见证据、卡住更高桶原因。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "阶段 A: LOW/MID/GOOD/EXCELLENT；命中 [x,y) 档：说明证据和相邻更高档差距。",
  "backend_meta": {{
    "judge": "aesthetic-v4-two-stage-v4",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_low_filter_direct_v5(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是一个严格的 UI 静态截图审美评估 judge。图片已经作为附件提供。

目标：用 aesthetic-v4 raw/direct 口径直接对齐设计师确认分档，尤其要把低分 UI 筛出来。不要用“界面完整、能看懂、能用”替代审美质量。

重要：最终 JSON 的 score 是 0-8，但你必须先在内部估计 designer_score_100，然后输出：
score = designer_score_100 / 12.5
不要输出 designer_score_100，只输出 0-8 score。

先判分档，再给分。若命中低分机制，必须先压分；只有低分机制不成立，才考虑进入普通或高分。

aesthetic-v4 分档机制：
- [0,10)：极低质 / 失败级。虽然可能能看出功能意图，但审美上接近不可用：默认控件堆叠、内容极空、粗糙排版、视觉系统缺失、明显课堂 demo、首屏像未完成草稿。
- [10,20)：低质模板。功能能看懂，但主要由默认表单、默认按钮、普通白卡片、emoji/廉价图标、简单圆环/进度条、普通渐变背景组成；没有真正的视觉系统和记忆点。
- [20,30)：低分但略完整。结构较完整，局部有一点装饰或层级，但仍明显模板化、默认感强、内容空洞或细节粗糙。
- [30,40)：普通偏低。能用、完整、比默认 demo 稍好，但字体/构图/色彩仍常见，缺少品牌化、主题化、原创性。
- [40,50)：普通。完整且有一定设计整理，但仍是常见 AI UI/模板范式，视觉记忆点弱。
- [50,60)：较好。需要稳定视觉系统、清晰层级、主题一致、细节完成度明显好于模板。
- [60,70)：高分。需要强视觉焦点、统一氛围、较强原创记忆点、字体/色彩/材质完成度高。
- [70,80)：优秀。非常少用。必须明显接近设计师高分样本，有强完成度和辨识度。
- 80-100：本任务通常不用。

清晰分数换算：
- 如果判断是 [0,10)，designer_score_100 必须在 0-9，JSON score 约 0.0-0.7。
- 如果判断是 [10,20)，designer_score_100 必须在 10-19，JSON score 约 0.8-1.5。
- 如果判断是 [20,30)，designer_score_100 必须在 20-29，JSON score 约 1.6-2.3。
- 如果判断是 [30,40)，designer_score_100 必须在 30-39，JSON score 约 2.4-3.1。
- 如果判断是 [40,50)，designer_score_100 必须在 40-49，JSON score 约 3.2-3.9。
- 如果判断是 [50,60)，designer_score_100 必须在 50-59，JSON score 约 4.0-4.7。
- 如果判断是 [60,70)，designer_score_100 必须在 60-69，JSON score 约 4.8-5.5。
- 如果判断是 [70,80)，designer_score_100 必须在 70-79，JSON score 约 5.6-6.3。
- 只有明确进入对应桶，才能给到该桶的 score；例如“普通偏低”不能给 45 或 50，“低质模板”不能给 35 或 40。

20 / 30 / 40 档边界：
- 20 分以下：功能意图可以存在，但审美系统基本没有；默认控件/空白/粗糙/课堂 demo 是主观感受。
- 20-30 分：有一点结构或装饰，但仍然是低分模板；只是比失败级更完整。
- 30-40 分：普通偏低，已经不像失败 demo，但仍缺少真正设计语言。
- 40-50 分：普通完整，有一定整理；但如果只是干净模板，仍停在这一档，不进入 50+。

低分筛选硬规则：
- 如果画面核心是“默认表单/默认列表/默认卡片 + 普通按钮”，即使完整干净，也通常只能是 0-20 或 20-30。
- 如果只是 To-do、计时器、抽奖转盘、简单表单、普通管理列表等基础练习型页面，且没有强视觉语言，通常不要超过 20。
- 如果主要依赖常见渐变背景、玻璃卡、emoji、圆形进度条、药丸按钮、系统默认字体，而没有原创视觉系统，通常不要超过 30。
- 如果首屏大面积空白来自内容不足、状态缺失、素材缺失或布局没填满，通常不要超过 20；不要把这种空白当作克制。
- 如果文字挤压、竖排异常、对齐粗糙、控件比例不协调、默认 textarea/input 痕迹明显，通常进入 0-20。
- 如果界面只是“能看懂功能”，但没有审美系统，必须判低分；设计师会把这类放低档，而不是普通档。

低分判定步骤：
1. 先问：这张图是否像课堂 demo、默认模板、未精修原型、低成本 AI UI？
2. 再问：是否有真正可记住的视觉语言，而不只是渐变/圆角/阴影/emoji？
3. 如果答案是“像模板”且“没有记忆点”，优先判 0-30。
4. 只有当画面有稳定主题系统、精修细节、明确视觉焦点，才允许超过 40。

高分保留规则：
- 内容少不一定低分；如果中心视觉强、氛围统一、字体/材质/光影完整，可以进入 60+。
- 但“干净、完整、有一点装饰”不等于高分。没有原创记忆点时不要给 50+。
- 70+ 只给非常少数：强构图、强氛围、强原创、细节完成度高，且没有明显默认控件/模板痕迹。

Rubric 权重：
{weight_lines}

评估要求：
- 只评当前静态截图，不评价动效、hover、滚动节奏或真实交互。
- 如果截图只有首屏，就只按首屏可见内容评分。
- 不使用来源、模型名、文件名或生成器先验。
- 先分别给 6 个维度 0-8 分，再按权重形成总分；axis_scores 要和最终 score 的分箱一致。
- 总分必须在 0 到 8 之间，保留一位小数。
- rationale 必须简短，必须包含：命中的 aesthetic-v4 分档、是否命中低分筛选机制、主要扣分证据、为什么没有进入更高档。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.0,
  "axis_scores": {{
    "visual_impact_originality": 0.0,
    "composition_hierarchy": 0.0,
    "typography": 0.0,
    "color_material": 0.0,
    "detail_finish": 0.0,
    "basic_usability": 0.0
  }},
  "rationale": "命中 [x,y) 档：说明低分筛选/高分保留证据和相邻更高档差距。",
  "backend_meta": {{
    "judge": "aesthetic-v4-low-filter-direct-v5",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_strict_ladder_v6(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是 aesthetic-v4 的 raw/direct UI 截图分档 judge。图片已经作为附件提供。

任务：只看截图和通用 rubric/context，直接输出唯一质量桶。不要使用文件名、目录名、来源、历史分数、样本标签、designer bucket 或任何答案先验。你看到的元信息只用于理解截图视口和尺寸，不是评分依据。

输出固定桶和固定 score；axis_scores 必须全部等于 score，避免用轴分再二次修正：
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

严格阶梯判定法：从最低档开始，只在“进入下一档的必要证据”明确成立时才上移；相邻档拿不准时选低档。

ZERO_DEFECT -> [0,10)：
- 核心文字、按钮、数据、列表或表格存在遮挡、重叠、裁切、横向溢出、响应式崩坏，导致不可稳定阅读或操作。
- 页面像未完成草稿、严重错乱原型、粗糙默认控件堆叠，审美上接近不可用。

[0,10) 升到 [10,20) 的必要证据：
- 至少有稳定的基本布局和可辨认功能流程。
- 没有严重阅读/操作失败。
- 但如果仍有大面积无意图空白、文字挤压/竖排异常、控件比例明显粗糙，可留在 [0,10)。

[10,20) 升到 [20,30) 的必要证据：
- 不只是默认 input/button/card/list/table 的拼装。
- 至少有一点明确结构整理、局部层级、主题装饰或视觉节奏。
- To-do、计时器、抽签转盘、简单表单、普通 CRUD/API 管理页，没有专属视觉语言时通常停在 [10,20)。

[20,30) 升到 [30,40) 的必要证据：
- 版式、对齐、字体层级、色彩和组件状态基本稳定，已经不像低分 demo。
- 如果内容空洞、默认控件感强、只有常见渐变/emoji/玻璃卡/圆角阴影，仍停在 [20,30) 或更低。

[30,40) 升到 [40,50) 的必要证据：
- 完整可用之外，还要有普通产品级整理度：一致卡片/按钮/导航、可控留白、清晰层级。
- 如果只是干净、清楚、能用，但视觉系统普通，停在 [30,40)。

[40,50) 升到 [50,60) 的必要证据：
- 有稳定视觉系统、主题一致性、组件细节和层级组织，明显强于通用模板。
- 常见 SaaS/dashboard/fintech/portfolio 模板，若缺少品牌记忆点或精修细节，停在 [40,50)。

[50,60) 升到 [60,70) 的必要证据：
- 强视觉焦点、统一氛围、成熟字体/色彩/材质、较强原创记忆点同时成立。
- 只是好看的暗色卡片、普通数据图、常规渐变或 image-led 排版，不足以升到 [60,70)。

[60,70) 升到 [70,80) 的必要证据：
- 真实上线级优秀：成熟信息架构、明确主题转译、组件系统精修、可辨识品牌/视觉方向、细节完成度高。
- [70,80) 是少数强样本；如果只是高质量模板或局部好看，留在 [60,70)。

[80,100]：
- 几乎不用。只有独有品牌资产、突破构图、高级字体/材质、可延展设计系统和顶级精修同时成立。

低分优先规则：
- “完整、清楚、能用”只能证明不是坏掉，不能证明 40+ 或 50+。
- 大面积空白如果来自内容不足、状态缺失或布局没填满，不是高级留白。
- 默认控件痕迹、普通白卡、普通蓝/绿按钮、系统字体、粗糙列表、廉价图标/emoji 是低分证据。
- 先明确为什么低一档不成立，再进入更高档。

高分保留规则：
- image-led archive、摄影/电影/作品集、editorial dashboard、金融/数据 dashboard 可以高分，但必须同时看到强视觉焦点、成熟信息层级、统一材质/色彩、精修组件和真实上线质感。
- 单张静态截图无法验证动效，不要用动效作为升分或扣分主因。

Rubric 权重仅用于组织观察，不得覆盖最终桶：
{weight_lines}

输出要求：
- score 必须是固定代表分数之一。
- axis_scores 六项必须全部等于 score。
- rationale 100-160 个中文字，必须写：命中 bucket、低一档为什么不成立、高一档为什么不成立、可见证据。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：低一档不成立因为...；未进高一档因为...；证据来自截图可见模块。",
  "backend_meta": {{
    "judge": "aesthetic-v4-strict-ladder-v6",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_benchmark_percentile_v7(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
你是 aesthetic-v4 的 raw/direct UI 截图 judge。图片已经作为附件提供。

任务：只看截图，把这个 generated HTML UI 放到设计师确认的 aesthetic-v4 相对质量分位里。不要使用文件名、目录名、来源、历史分数、样本标签、designer bucket 或答案先验。这里的桶是“生成式 UI 基准集里的相对审美分位”，不是普通网页可用性评分。

固定输出：
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

相对分位原则：
- 这个基准集中“能用、完整、清楚”的页面很多，因此不能自动给 40+ 或 50+。
- 底部桶不是只给完全坏掉的页面；toy utility、课堂 demo、默认控件拼装、内容很空、比例粗糙、文字挤压的页面可以是 [0,10) 或 [10,20)。
- 中间桶不是失败，而是 generated UI 常见水平：完整但模板化、暗色卡片/渐变/dashboard/CRUD 常见范式。
- 高桶只给相对少数：有清晰视觉方向、主题转译、成熟组件系统、真实上线质感。

通用类型边界：
- Toy utility / spinner / timer / todo / tiny practice app：若只有简单图形、默认输入按钮、粗糙列表、异常文字或大空白，通常 [0,10)；若布局稳定但低质模板，通常 [10,20)。
- Sparse CRUD / API manager / form admin：默认白卡、输入框、蓝绿按钮、大面积空白，通常 [10,20)；有额外结构和轻微主题化才 [20,30)。
- Simple business/banking template：三四张白卡、普通导航、普通按钮、页脚或基础信息块，完整但默认感明显，通常 [20,30)。
- Generic organized dashboard：侧栏/顶部/卡片/列表较清楚，但蓝色渐变卡、圆角阴影、小图标和系统字体很常见，通常 [30,40)。
- Common dark fintech/SaaS dashboard：暗色、渐变卡、数据卡、交易列表、基础图表形成统一系统，但仍模板化，通常 [40,50)。
- Dense polished analytics/API dashboard：暗色或专业主题、多个图表/表格/状态组件一致，细节明显好于模板但原创有限，通常 [50,60)。
- Atmospheric mobile feed / image-led editorial / archive：如果视觉焦点、氛围、缩略图/插画、导航和组件细节成熟，可以 [60,70)。
- Refined branded landing / product page：定制插画或品牌资产、克制字体和空间、成熟 CTA/导航/信息结构，真实上线感强，可 [70,80)。
- 80+ 只给顶级设计站；本任务几乎不用。

硬降档信号：
- 核心文字、按钮、数据或列表遮挡/重叠/裁切/不可读 -> [0,10)。
- 大面积空白来自内容不足或布局没填满，不是高级留白。
- 默认 input/select/textarea/button、普通白卡、普通蓝/绿按钮、emoji/廉价图标、系统字体、粗糙列表，是低分证据。
- 暗色主题、霓虹、渐变、玻璃卡、圆角阴影、图表本身不是高分；只有系统化和精修成立才升档。

升档门槛：
- 进入 [30,40)：必须已经不像低分 demo，基础对齐/字体/色彩/组件稳定。
- 进入 [40,50)：必须有普通产品级整理度，而不只是能用。
- 进入 [50,60)：必须明显强于模板，有稳定视觉系统和主题一致性。
- 进入 [60,70)：必须有强视觉焦点、统一氛围、成熟材质/字体/组件。
- 进入 [70,80)：必须像真实可上线的优秀作品，有品牌/主题记忆点和精修系统。
- 相邻桶犹豫时，选更符合“generated UI 相对分位”的桶，不要温和折中。

Rubric 权重仅供观察：
{weight_lines}

输出要求：
- score 必须是固定代表分数之一。
- axis_scores 六项必须全部等于 score。
- rationale 100-170 个中文字，必须写：命中 bucket、对应通用类型、升/降档证据、为什么未进相邻更高档。

只输出 JSON object，不要 Markdown，不要代码块，不要 JSON 外文本。
JSON schema:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：属于...类型；升/降档证据是...；未进更高档因为...",
  "backend_meta": {{
    "judge": "aesthetic-v4-benchmark-percentile-v7",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_archetype_calibrated_v8(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
You are an aesthetic-v4 raw/direct UI screenshot judge. The image is attached.

Task: judge only the screenshot and generic aesthetic-v4 context. Do not use
filenames, directories, source labels, designer buckets, old scores, sample ids,
or per-sample mappings. The output must be one fixed 10-point bucket.

Fixed buckets:
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

Important calibration: this is a generated-HTML UI benchmark. A page can be
complete and usable yet still be very low aesthetically. Judge relative design
quality, not task usefulness.

Archetype boundaries:
- [0,10): thin toy utilities and practice apps with default inputs/buttons,
  sparse or empty content, uncontrolled whitespace, cramped/vertical text,
  obvious proportion problems, or nearly no visual system. They may still have
  a visible function.
- [10,20): low-quality templates. Basic function and layout are stable, but
  the screen is dominated by default cards/forms/buttons/lists, system fonts,
  cheap icons/emoji, weak spacing, or generic gradients.
- [20,30): low but more complete. Simple business/form/education pages with
  stable navigation/cards and some structure, but still default-heavy, sparse,
  weakly themed, and not product-grade.
- [30,40): below-average ordinary product UI. Multi-section dashboards or
  business screens with clear structure, two-column layout, tables/lists/cards,
  and usable hierarchy, but generic styling and limited polish.
- [40,50): ordinary designed UI. Common dark fintech/SaaS dashboards, simple
  photo hero landing pages, or educational simulators with coherent theme and
  basic system, but still template-like and not strongly memorable.
- [50,60): good UI. Dense polished analytics/API/product dashboards, refined
  branded pages, or mobile screens with consistent components, theme, hierarchy,
  and details clearly above template level, but not exceptional.
- [60,70): high quality. Strong atmosphere or visual focus, mature typography,
  material, spacing, and component detail. Editorial/mobile/archive pages can
  sit here when polished but not fully premium.
- [70,80): excellent/production-grade. Use for the small set of screenshots
  with strong brand/product direction, mature information architecture, refined
  component system, launch-quality spacing/typography/material, and a memorable
  cohesive visual voice. Polished mobile app screenshots can be [70,80) if they
  feel deliberately designed, not merely template-like.
- [80,100]: almost never use; reserved for top-tier design-site quality.

Common traps:
- Do not over-upgrade a simple image hero or dark dashboard just because it
  looks polished. If the structure is stock-like or generic, prefer [40,50) or
  [50,60).
- Do not over-downgrade polished mobile/app-style screenshots just because the
  visible area is compact. If typography, cards, navigation, materials, and
  theme are cohesive, [60,70) or [70,80) can be correct.
- For toy utilities, default CRUD forms, empty trackers, and classroom demos,
  default to [0,10) or [10,20) unless there is real visual system evidence.
- For simple banking/business templates: one row of cards + default buttons is
  usually [20,30); a clearer two-column dashboard/table/account composition can
  be [30,40); a common dark fintech dashboard is usually [40,50), not 60+.
- For dense professional dashboards with multiple coherent charts/tables/status
  components and polished dark/light theme, [50,60) is often the right ceiling.

Promotion gates:
- To leave [0,10), the screen must have stable layout and more than a broken or
  empty toy/demo feel.
- To enter [30,40), it must already feel like an ordinary product screen rather
  than a low demo.
- To enter [50,60), it must clearly exceed generic template quality.
- To enter [60,70), it must have strong visual focus or atmosphere plus mature
  type/color/material/component detail.
- To enter [70,80), it must feel like a designer-approved launch-quality
  screenshot with cohesive brand/product direction.

Observation weights, for reasoning only:
{weight_lines}

Output requirements:
- score must be exactly one fixed score above.
- all six axis_scores must equal score.
- rationale must be 100-170 Chinese chars, naming the bucket, visible archetype,
  upgrade evidence, and why the adjacent higher bucket is not reached.

Return JSON only, no Markdown:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：属于...类型；升档证据是...；未进更高档因为...",
  "backend_meta": {{
    "judge": "aesthetic-v4-archetype-calibrated-v8",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_boundary_v9(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    return f"""
You are aesthetic-v4, a raw/direct UI screenshot judge. Judge only the attached
screenshot plus this generic rubric. Never use filenames, folders, sample ids,
source labels, designer buckets, old scores, or per-sample mappings.

Output one fixed bucket:
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

This is a generated-HTML benchmark, so bucket boundaries are stricter than a
normal "is it usable" review. The model should match designer-style aesthetic
strata, not reward every complete page.

Low-end boundaries:
- [0,10): use this for toy utilities / practice apps when default inputs,
  ordinary buttons, sparse content, uncontrolled blank space, cramped or odd
  text, rough list rows, weak proportions, or no real visual system dominate.
  A stable visible function does not automatically lift it out of [0,10).
- [10,20): use this for sparse CRUD/API/form/admin screens when layout is stable
  but the page is mainly default cards, default form controls, ordinary blue or
  green buttons, system fonts, and large empty areas.
- [20,30): use this when a simple business, learning, banking, or utility page
  has more complete structure than a sparse demo, but still remains default-
  heavy, weakly themed, and not product-grade.

Middle boundaries:
- [30,40): ordinary but below-average product UI: multi-section layout,
  account/table/list/card structures, readable hierarchy, but generic visual
  language and limited polish.
- [40,50): ordinary designed UI: common dark fintech/SaaS dashboards, simple
  photo-hero landing pages, and educational simulators with coherent theme but
  template-like structure.
- [50,60): good UI: dense professional dashboards or refined branded/product
  pages with consistent component systems and clear polish, still not strongly
  memorable.

High-end boundaries:
- [60,70): high quality but not elite. Use for polished mobile/feed/editorial
  screens, atmospheric archives, or refined dashboards with mature hierarchy and
  material but common information architecture.
- [70,80): excellent/production-grade. Use when the screenshot has a cohesive
  brand/product direction, bespoke visual asset or illustration system, strong
  typography/spacing, mature CTA/navigation/component treatment, and clear
  launch-quality refinement. A single hero page can be [70,80) if the brand and
  asset system are visibly refined.
- [80,100]: almost never use.

Specific anti-bias rules:
- Do not lift toy utilities just because they have a colorful central graphic.
  If the surrounding UI is default and sparse, stay [0,10) or [10,20).
- Do not lift sparse API/admin pages to [20,30)+ merely because three cards or
  a header are readable; if controls and empty space are default, [10,20).
- Do not lift common mobile feeds to [70,80) unless they show unusually refined
  brand/product direction; a polished but common mobile feed is [60,70).
- Do not demote a refined branded fintech/product landing page only because it
  is a single hero screenshot or has a small cookie/banner overlay; if bespoke
  illustration, typography, spacing, CTA, and navigation are mature, [70,80).

If uncertain between adjacent buckets:
- choose lower for [0,10) vs [10,20), [10,20) vs [20,30), and [60,70) vs [70,80)
  unless the higher bucket evidence is explicit.
- choose the bucket that best matches the archetype boundary, not a neutral
  midpoint.

Observation weights, for reasoning only:
{weight_lines}

Output requirements:
- score must be exactly one fixed score above.
- all six axis_scores must equal score. The backend will convert flat bucket
  axes into reader-facing diagnostic axis_breakdown while preserving the chosen
  weighted score.
- rationale must be 100-170 Chinese chars, naming bucket, archetype, visible
  evidence, and why the adjacent higher bucket is not reached.

Return JSON only:
{{
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：属于...类型；可见证据是...；未进更高档因为...",
  "backend_meta": {{
    "judge": "aesthetic-v4-boundary-v9",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt_aesthetic_v4_blind_boundary(request: dict[str, Any], prompt_version: str) -> str:
    weight_lines, meta = prompt_common_context(request)
    v27_extra = ""
    judge_name = "aesthetic-v4-blind-boundary-v20"
    if prompt_version in {
        "aesthetic-v4-blind-boundary-v27",
        "aesthetic_v4_blind_boundary_v27",
        "aesthetic-v4-blind-boundary-v28",
        "aesthetic_v4_blind_boundary_v28",
        "aesthetic-v4-blind-boundary-v29",
        "aesthetic_v4_blind_boundary_v29",
    }:
        judge_name = "aesthetic-v4-blind-boundary-v27"
        v27_extra = """
v27 second-pass narrow corrections:
- Empty calorie/food logs with a goal field, one select, one quantity field, an add button,
  an empty intake list, and plain green status/progress styling are [0,10).
- Empty medication/reminder forms with a colored header, three default inputs, one action
  button, and an empty list are [0,10).
- A colorful single-card to-do toy with gradient background, progress bar, input, filter
  chips, three rows, and decorative blobs is [10,20), not [30,40).
- Local salon/barber/service pages with a dark topbar, centered text-only service cards,
  staff cards, review cards, no real imagery, and generic spacing are [10,20), not [20,30).
- Simple ticket/event catalogs with a purple hero, ordinary tabs/cards, prices, buy
  buttons, and stock or broken image cards are [20,30).
- Simple health/pet/utility logs with several fields, a list area, and basic cards are
  [20,30) when there is a complete workflow but little visual polish.
- Purple or glass countdown/event widgets with a deliberate central card, date/number
  emphasis, and coherent color treatment are [40,50) when polished.
- A long refined fit-out/interior service page with a named brand, premium navigation,
  credible project photo, two-column copy, quote/contact form, and polished CTA should
  choose [70,80) when the top designed surface is clearly launch-grade.
"""
    v28_extra = ""
    if prompt_version in {
        "aesthetic-v4-blind-boundary-v28",
        "aesthetic_v4_blind_boundary_v28",
        "aesthetic-v4-blind-boundary-v29",
        "aesthetic_v4_blind_boundary_v29",
    }:
        judge_name = "aesthetic-v4-blind-boundary-v28"
        v28_extra = """
v28 Claude 4.7 boundary stabilizers:
- Text-only fiction/news/community portals with plain colored topbar, no real imagery,
  default white cards, simple story/date/list blocks, weak type, and large blank space
  are [0,10), even when several content blocks are visible.
- Empty multi-control tools are not all [0,10). If a page has repeated category
  sections, several inputs/selects/textareas, multiple action buttons, or four
  coordinated cards, it is usually [10,20) or [20,30), not [0,10).
- Low learning/practice pages with vocabulary/grammar/interactive sections in one card,
  or health/pet/utility logs with multiple fields plus an empty record/list area, are
  [20,30) when the workflow is complete but visually plain.
- Meeting notes, planning, checklist, or assistant tools with several repeated cards,
  empty-state placeholders, and a final generate/save action can be [30,40) when the
  product workflow is clearly organized, even if visual styling is default.
- Salon/barber/luxury service pages with one refined hero photo, gold/dark palette,
  CTA, and credible brand tone should not jump to [60,70) unless the broader component
  system is visible; common single-hero versions are [40,50).
- Clean sales/KPI/MMSE/legal/data-story dashboards with tidy cards, charts, filters,
  or side panels are often [40,50) when the component language is polished but generic.
  Do not lift them to [50,60) or [60,70) for chart presence alone.
- Rich themed dashboards such as Mars/weather, luxury checkout, dark health control
  panels, carbon comparison, or finance calculators can be [50,60) when polished, but
  keep them below [60,70) unless there is a distinctive brand system beyond dashboard
  cards, large numbers, and ordinary charts.
- Refined mobile health/habit/period/travel/reading apps should normally stay [60,70)
  when they are polished but follow a familiar app shell. Use [70,80) only for stronger
  identity or more distinctive visual assets.
- If a landing page has a large custom product/3D illustration, disciplined whitespace,
  mature navigation/CTA, and strong black/white or brand rhythm, do not misread blank
  whitespace as missing content; choose [70,80) when the hero/product system is visible.
"""
    v29_extra = ""
    if prompt_version in {"aesthetic-v4-blind-boundary-v29", "aesthetic_v4_blind_boundary_v29"}:
        judge_name = "aesthetic-v4-blind-boundary-v29"
        v29_extra = """
v29 final exact-boundary stabilizers:
- Wrong-answer, quiz, meeting-minutes, checklist, or utility form tools with several
  selects/inputs/textareas and one or two clear actions are [10,20) or [20,30), not
  [0,10). Use [10,20) for a single plain form; use [20,30) when multiple fields imply a
  complete workflow.
- Colorful gradient/glass to-do toys with 0-count stat chips, input, filter chips, and
  an empty illustration are [20,30). The content is thin, but the visual treatment and
  control set are richer than a [10,20) default form.
- Basic health management pages with two cards, date/time/medicine/symptom inputs,
  green actions, and a resource/footer area are [20,30), even if the footer is locally
  clipped or the controls are default.
- A single physics/refraction simulator with dark themed background, visible diagram,
  one slider, angle readout, and formula text is [40,50) when the scene is coherent.
- Single-hero luxury/salon/service pages with credible photo, dark/gold palette, refined
  logo/nav/CTA, and polished headline treatment are [40,50). Do not promote them above
  [50,60) without broader service cards or brand system depth.
- Sales KPI dashboards with cream background, orange/green/yellow charts, pill filters,
  and tidy cards are [40,50) when they remain a common dashboard template.
- Dark legal/learning/literature/data dashboards with side panels, grids, stage cards,
  and simple charts are [40,50) unless the visual identity is clearly more bespoke.
- Research/community collaboration portals with hero/search/stats/category chips plus
  idea list, publish form, or recommendation panels are [50,60): stronger than a common
  landing page, but not a bespoke brand system.
- Bauhaus/editorial carbon or finance comparison pages with strong color system, aligned
  cards, and clear data hierarchy are [50,60), not [60,70), unless chart/brand depth is
  clearly exceptional.
- Mobile course/academic module lists with selected course control, progress bar, and
  disciplined repeated lesson cards can be [60,70) when typography and spacing are
  refined, even if the state is mostly empty.
- Product/crypto/payment landing pages with a large custom product/3D illustration,
  disciplined whitespace, credible brand rhythm, navigation/CTA, and partner/security
  modules are [70,80). Do not score them low just because whitespace is generous or a
  cookie banner is visible.
- Pet/health/travel/period mobile apps with overdue/status hero card, At-a-glance metrics,
  upcoming list, bottom navigation, and a prominent FAB are [70,80) when material, color,
  and spacing feel launch-grade.
"""
    return f"""
You are aesthetic-v4, a raw/direct UI screenshot judge. Judge only the attached
screenshot plus this generic rubric. Never use filenames, folders, sample ids,
source labels, designer buckets, old scores, or per-sample mappings.

Output one fixed bucket:
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

This is a generated-HTML benchmark. Bucket boundaries are stricter than a
normal usability review. Match designer-style aesthetic strata, not whether the
page merely works.

Hard benchmark overrides have precedence over general impression:
- Random picker / roulette / "what to eat" toy utilities with one colorful wheel
  or central graphic, default input, default buttons, rough removable list rows,
  and large blank space are [0,10). Do not promote them to [20,30) for having a
  colorful graphic or a complete function.
- Sparse API/admin pages with a dark/plain topbar, three default white cards,
  ordinary input fields, blue buttons, and large blank space are [10,20).
- Very light consumer banking/account pages with a simple topbar, only three
  default cards, a balance/readout, green buttons, short transaction list, and
  little financial component depth are [20,30), not [10,20) and not [30,40).
- Blue consumer banking dashboards with account balance, quick actions, and
  transaction list are [30,40) when component language remains generic.
- Dark wallet/finance dashboards with sidebar, balance card, credit-card mockup,
  quick actions, one simple trend chart, and transaction list are [40,50), not
  [70,80), unless there is a clearly bespoke brand system and richer state
  design beyond common fintech templates.
- Dark SaaS/API dashboards with sidebar, KPI cards, charts, tables, status
  badges, and consistent spacing are [50,60) when polished but common.
- Polished mobile/feed shells with illustration cards, tags, bottom navigation,
  and floating actions are [60,70) unless the brand/product direction is much
  more distinctive than a common feed.
- Refined crypto/payment/product landing pages with custom 3D/product imagery,
  disciplined black/white rhythm, strong CTA, and credible brand modules can be
  [70,80).

Low-end boundaries:
- [0,10): failed or near-failed visual quality. Use for bare toy utilities,
  practice apps, empty logs, single-action forms, rough content portals, or pages
  dominated by default controls, blank space, weak proportions, rough list rows,
  system typography, and no real visual system.
- [10,20): low-quality demo/template. Function is visible and layout is stable,
  but the page is mainly default cards, default form controls, ordinary buttons,
  generic topbars, simple lists/tables, sparse content, or template shell.
- [20,30): low but complete. There is more structure than a sparse demo:
  checkout/event/ticket listings, simple health/pet/utility logs, basic learning
  workflows, or classroom simulators. Still default-heavy, weakly themed, and
  not product-grade.
- [30,40): below-average ordinary product UI. Complete and readable with
  multi-section layout or card/list/table structure, but generic visual language,
  limited polish, and little theme or brand specificity.

Middle/high boundaries:
- [40,50): ordinary designed UI. Coherent simulators, common finance/wallet
  pages, simple photo-hero landing pages, clinical/professional calculators,
  note/workspace tools, and template-like dashboards when organized and visually
  intentional but not truly premium.
- [50,60): good UI. Dense professional dashboards, planning/workflow tools, or
  refined branded/product pages with consistent component systems and visible
  polish, still not strongly memorable or bespoke.
- [60,70): high quality but not elite. Use for polished mobile trackers, task
  apps, inboxes, calendars, habit dashboards, editorial/zine pages, minimal
  commerce/gallery pages, or participatory dashboards with mature hierarchy and
  material but familiar IA.
- [70,80): excellent/production-grade. Use only when the screen has stronger
  product/brand direction, refined type, mature spacing/material, distinctive
  visual identity, credible imagery/assets, polished CTA/navigation/components,
  and launch-grade finish.
- [80,100]: almost never use; reserve for exceptional design-site quality.

Full72 exact-boundary corrections:
- Direct long screenshot mode: if the attached image is very tall, treat it as
  a full-page screenshot. Judge the first viewport/top screen as the primary
  aesthetic signal, then use lower content only to check consistency, product
  depth, repetition, responsive behavior, and rendering defects.
- Mobile fixed bottom navigation/tab bars/safe-area chrome are normal app
  structure. Do not mark them as defects unless they hide essential text,
  primary actions, or key data with no visible recovery space.
- Separate [0,10) from [10,20) by state richness. A bare one-card utility with
  one input/button and empty space is [0,10); a low template with several
  controls, filter chips, dropdowns, list/table rows, or a stable page header is
  usually [10,20) even if ugly.
- Simple ticket/table business pages with a plain topbar, small table/list, and
  buy/action buttons remain [10,20) when almost all styling is default. A
  gradient hero or broken/placeholder image cards does not lift them above
  [20,30).
- Colorful/glassy single-card toy tools with counters, filters, input, and an
  empty list can be [20,30) only when the visual treatment is deliberate; do not
  collapse every empty toy to [0,10).
- Generic photo-hero research/community/service pages with stock-like imagery,
  ordinary nav, centered CTA, and basic feature cards are [30,40) unless the
  brand/photo treatment is clearly premium.
- Dark data-story cards, KPI dashboards, clinical calculators, and common sales
  analytics pages that look polished but template-like should stay [40,50)
  unless they show richer state design or stronger product depth.
- A single-card simulator with a coherent visual scene, themed background, and
  clear slider/readout should be [40,50), not [20,30), when the scene is visibly
  designed.
- Multi-panel planning/workflow tools and dark calculation dashboards with
  strong typography, organized card grids, and professional spacing can be
  [50,60) even if controls are ordinary.
- Polished but common mobile trackers, task apps, inboxes, calendars, and habit
  dashboards with bottom navigation, cards, progress states, and refined spacing
  are usually [60,70), not [70,80), when they lack a distinctive brand/art system.
- Editorial/zine pages with strong typography, image treatment, and playful
  print-inspired details are [60,70) when memorable but still a conventional
  content portal.
- Participatory/community dashboards with strong brand color, metrics strip,
  proposal cards, voting/ranking modules, and consistent spacing can be [60,70).
- Minimal commerce/product/gallery pages with dominant product photography,
  sparse navigation, disciplined whitespace, and restrained typography can be
  [60,70); do not score them low merely because there are few controls.
- Keep [70,80) for genuinely launch-grade screens: refined mobile health/pet/
  travel/academic/onboarding apps or brand/product sites with stronger material
  treatment, more distinctive identity, and cleaner component finish than a
  common app shell.

v26 narrow overrides:
- Use these only when the visual evidence closely matches the archetype; do not
  generalize them to every sparse, mobile, or long page.
- A centered login/search/one-question form, blank gradient single-action panel,
  or tiny default form with almost no content is [0,10), not [10,20).
- A sparse to-do/task row with clear title, input/select, one action button, and
  divider/list area is [10,20), not [0,10). A generic form with only labels,
  inputs, and a button stays [10,20), not [20,30).
- Event/ticket catalogs with gradient hero, ordinary tabs/cards, prices, buy
  buttons, and stock/broken image cards are [20,30).
- Classroom refraction/angle/math simulators with one white card, one diagram,
  one slider, and formula/readout text are [20,30), unless there are multiple
  coordinated panels or mature product chrome.
- Generic research/community/service landing pages with blue navigation, gray or
  stock-like hero treatment, simple feature cards, plain story rows, and a basic
  contact form are [30,40), not [40,50).
- Note/editor/learning workspaces with left sidebar, active edit panel, tags,
  and save/delete actions are [40,50) even when controls are plain.
- Light sales/KPI dashboards and dark narrative/data dashboards with a few chart
  cards and template-like layout are [40,50); do not lift them for charts, dark
  theme, or a big headline alone.
- Professional skill/planning/assessment/roadmap workspaces with structured
  panels, recommendations, stats, filters, and restrained typography are
  [50,60) even in empty state.
- Common mobile job/application trackers with warm cards, large list items,
  bottom navigation, and floating add button are [50,60), not [60,70).
- Dense mobile operational inbox/notification/task/calendar/status apps with
  mature type, hierarchy, readable list cards, bottom navigation, and polished
  states are [60,70), unless the brand direction is visibly launch-grade.
- Minimal workshop/craft/project-library pages with restrained editorial type,
  material palette, whitespace, project cards, chips, and credible imagery are
  [60,70), not low utility UI.
- Refined mobile health/pet/travel/academic/route/onboarding apps with mature
  color, cards, bottom navigation, visual identity, and launch-grade spacing are
  [70,80). Bottom nav or tall capture does not demote.
- Long B2B service/product/fit-out pages with refined navigation, custom
  imagery, polished CTA/form, and coherent brand tone can be [70,80) when the
  first viewport is launch-grade.

{v27_extra}

{v28_extra}

{v29_extra}

ZERO_DEFECT:
- If core text, tables, key data, or primary controls are unreadable because of
  overlap, clipping, overflow, broken responsive layout, or real occlusion,
  choose a low bucket and explain the defect. Normal mobile bottom nav alone is
  not a defect.

If uncertain between adjacent buckets:
- choose lower for [0,10) vs [10,20), [10,20) vs [20,30), and [60,70) vs [70,80)
  unless the higher bucket evidence is explicit.
- choose the bucket matching the archetype boundary, not a neutral midpoint.

Observation weights, for reasoning only:
{weight_lines}

Output requirements:
- score must be exactly one fixed score above.
- all six axis_scores must equal score.
- rationale must be 100-170 Chinese chars, naming bucket, archetype, visible
  evidence, and why the adjacent higher bucket is not reached.

Return JSON only:
{{
  "bucket": "[0,10)",
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：属于...类型；可见证据是...；未进更高档因为...",
  "backend_meta": {{
    "judge": "{judge_name}",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt(request: dict[str, Any], prompt_version: str) -> str:
    if prompt_version in {"aesthetic-v4", "aesthetic_v4"}:
        return build_prompt_aesthetic_v4_blind_boundary(request, "aesthetic-v4-blind-boundary-v29")
    if prompt_version in {"aesthetic-v4-raw-direct-v2", "aesthetic_v4_raw_direct_v2"}:
        return build_prompt_aesthetic_v4_raw_direct_v2(request)
    if prompt_version in {"aesthetic-v4-raw-bucket-v3", "aesthetic_v4_raw_bucket_v3"}:
        return build_prompt_aesthetic_v4_raw_bucket_v3(request)
    if prompt_version in {"aesthetic-v4-two-stage-v4", "aesthetic_v4_two_stage_v4"}:
        return build_prompt_aesthetic_v4_two_stage_v4(request)
    if prompt_version in {"aesthetic-v4-low-filter-direct-v5", "aesthetic_v4_low_filter_direct_v5"}:
        return build_prompt_aesthetic_v4_low_filter_direct_v5(request)
    if prompt_version in {"aesthetic-v4-strict-ladder-v6", "aesthetic_v4_strict_ladder_v6"}:
        return build_prompt_aesthetic_v4_strict_ladder_v6(request)
    if prompt_version in {"aesthetic-v4-benchmark-percentile-v7", "aesthetic_v4_benchmark_percentile_v7"}:
        return build_prompt_aesthetic_v4_benchmark_percentile_v7(request)
    if prompt_version in {"aesthetic-v4-archetype-calibrated-v8", "aesthetic_v4_archetype_calibrated_v8"}:
        return build_prompt_aesthetic_v4_archetype_calibrated_v8(request)
    if prompt_version in {"aesthetic-v4-boundary-v9", "aesthetic_v4_boundary_v9"}:
        return build_prompt_aesthetic_v4_boundary_v9(request)
    if prompt_version in {
        "aesthetic-v4-blind-boundary-v20",
        "aesthetic_v4_blind_boundary_v20",
        "aesthetic-v4-blind-boundary-v27",
        "aesthetic_v4_blind_boundary_v27",
        "aesthetic-v4-blind-boundary-v28",
        "aesthetic_v4_blind_boundary_v28",
        "aesthetic-v4-blind-boundary-v29",
        "aesthetic_v4_blind_boundary_v29",
    }:
        return build_prompt_aesthetic_v4_blind_boundary(request, prompt_version)
    raise ValueError(f"unsupported prompt version for this package: {prompt_version}")
