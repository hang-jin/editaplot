"""Shared read-only preparation for non-XPS scientific plotting templates.

The module owns column-role inference, numeric auditing, display-only transforms,
axis planning, and the digest shared by preview and Origin rendering.  It never
writes to the user's source table.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from .circular_network_layout import (
    MAX_NODE_GROUP_COUNT,
    CircularNetworkEdgeRecord,
    CircularNetworkLayoutPlan,
    resolve_circular_network_layout,
)
from .data_loader import DataLoadError, LoadedTable, load_table
from .heatmap_layout import heatmap_cell_labels_enabled
from .palette_catalog import get_palette
from .scientific_visual import AdaptiveOriginStyle, resolve_adaptive_style
from .shap_composite import (
    SHAP_COMPOSITE_PROFILES,
    ShapCompositeError,
    ShapCompositePlan,
    build_shap_composite_plan,
)
from .xrd_semantics import (
    GSAS_II_PUBLICATION_CSV,
    XrdSemanticError,
    detect_xrd_source_profile,
    propose_xrd_semantics,
)

ScientificTemplateId = Literal[
    "eis",
    "cv",
    "lsv",
    "xas",
    "xrd",
    "bar",
    "horizontal_bar",
    "stacked_bar",
    "percent_stacked_bar",
    "pie",
    "sankey",
    "circular_network",
    "scatter",
    "line_error",
    "trend",
    "radar",
    "heatmap",
    "raw_summary",
    "violin",
    "histogram",
    "forest",
    "bubble",
    "diagnostic_curve",
    "confusion_matrix",
    "bland_altman",
    "paired_trajectory",
    "calibration_curve",
    "decision_curve",
    "raincloud",
    "shap_summary",
    "grouped_box",
    "dsc",
    "nmr",
    "ftir",
    "xps_compare",
    "pl",
    "uv_vis",
    "trajectory3d",
    "density_ridgeline3d",
]
AxisScale = Literal["linear", "log10"]
SeriesAxis = Literal["left", "right"]
SeriesTransform = Literal["identity", "negate"]

SUPPORTED_SCIENTIFIC_TEMPLATE_IDS = frozenset(
    {
        "eis",
        "cv",
        "lsv",
        "xas",
        "xrd",
        "bar",
        "horizontal_bar",
        "stacked_bar",
        "percent_stacked_bar",
        "pie",
        "sankey",
        "circular_network",
        "scatter",
        "line_error",
        "trend",
        "radar",
        "heatmap",
        "raw_summary",
        "violin",
        "histogram",
        "forest",
        "bubble",
        "diagnostic_curve",
        "confusion_matrix",
        "bland_altman",
        "paired_trajectory",
        "calibration_curve",
        "decision_curve",
        "raincloud",
        "shap_summary",
        "grouped_box",
        "dsc",
        "nmr",
        "ftir",
        "xps_compare",
        "pl",
        "uv_vis",
        "trajectory3d",
        "density_ridgeline3d",
    }
)

_CATEGORY_TABLE_TEMPLATE_IDS = frozenset(
    {
        "bar",
        "horizontal_bar",
        "stacked_bar",
        "percent_stacked_bar",
        "pie",
        "radar",
        "heatmap",
        "confusion_matrix",
    }
)


class ScientificWorkflowError(ValueError):
    """Stable user-presentable preparation error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        column: str | None = None,
        row: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.column = column
        self.row = row


@dataclass(frozen=True)
class ScientificColumnMapping:
    """A user-confirmed assignment for every source column."""

    assignments: tuple[tuple[str, str], ...]
    plot_mode: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"assignments": dict(self.assignments), "plot_mode": self.plot_mode}


@dataclass(frozen=True)
class ScientificSeries:
    source_column: str
    label: str
    axis: SeriesAxis = "left"
    transform: SeriesTransform = "identity"
    error_column: str | None = None
    error_kind: str | None = None
    size_column: str | None = None
    lower_column: str | None = None
    upper_column: str | None = None
    color_column: str | None = None
    category: str | None = None
    group: str | None = None
    series_role: str = "data"
    paired_with: str | None = None
    display_offset: float = 0.0


@dataclass(frozen=True)
class ScientificAxisPlan:
    x_from: float | None
    x_to: float | None
    x_step: float | None
    y_from: float
    y_to: float
    y_step: float | None
    y2_from: float | None = None
    y2_to: float | None = None
    y2_step: float | None = None
    z_from: float | None = None
    z_to: float | None = None
    z_step: float | None = None


@dataclass(frozen=True)
class ScientificDisplayPlan:
    """Frozen density/layout values shared by preview and Origin output."""

    marker_size_pt: float
    bar_group_span: float
    bar_inner_width: float
    category_label_rotation_deg: float = 0.0
    figure_style: AdaptiveOriginStyle | None = None


@dataclass(frozen=True)
class ScientificPlotSpec:
    plot_kind: str
    plot_mode: str
    x_column: str | None
    category_column: str | None
    series: tuple[ScientificSeries, ...]
    x_title: str
    y_title: str
    y2_title: str | None
    x_scale: AxisScale
    y_scale: AxisScale
    display_transform: str
    display_plan: ScientificDisplayPlan
    axis_plan: ScientificAxisPlan
    y_column: str | None = None
    z_title: str | None = None
    source_column: str | None = None
    target_column: str | None = None
    panel_column: str | None = None
    weight_column: str | None = None
    sign_column: str | None = None
    source_group_column: str | None = None
    target_group_column: str | None = None
    edge_label_column: str | None = None
    node_groups: tuple[tuple[str, str], ...] = ()
    network_layout: CircularNetworkLayoutPlan | None = None
    aggregate_error_column: str | None = None
    reference_value: float | None = None
    reference_values: tuple[float, ...] = ()
    reference_labels: tuple[str, ...] = ()
    reference_geometry: str | None = None
    bin_rule: str | None = None
    bin_begin: float | None = None
    bin_end: float | None = None
    bin_size: float | None = None
    jitter_rule: str | None = None
    color_rule: str | None = None
    category_order: tuple[str, ...] = ()
    group_order: tuple[str, ...] = ()
    inset_x_column: str | None = None
    inset_series: tuple[ScientificSeries, ...] = ()
    inset_x_title: str | None = None
    inset_y_title: str | None = None
    inset_axis_plan: ScientificAxisPlan | None = None
    inset_annotation: str | None = None
    phase_tick_columns: tuple[str, ...] = ()
    source_profile: str | None = None
    focal_x_column: str | None = None
    condition_positions: tuple[tuple[str, float], ...] = ()
    shap_plan: ShapCompositePlan | None = None


@dataclass(frozen=True)
class ScientificPreparation:
    template_id: str
    source_path: str
    source_sha256: str
    source_size_bytes: int
    source_format: str
    source_sheet: str | None
    source_columns: tuple[str, ...]
    row_count: int
    ignored_empty_rows: int
    assignments: tuple[tuple[str, str], ...]
    plot_spec: ScientificPlotSpec
    confidence: float
    requires_confirmation: bool
    confirmation_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    mapping_confirmed: bool
    plan_digest: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _scientific_plan_digest(
    preparation: ScientificPreparation,
    plot_spec: ScientificPlotSpec,
) -> str:
    digest_payload = {
        "template_id": preparation.template_id,
        "source_sha256": preparation.source_sha256,
        "source_columns": preparation.source_columns,
        "assignments": preparation.assignments,
        "plot_spec": asdict(plot_spec),
        "mapping_confirmed": preparation.mapping_confirmed,
    }
    return hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def apply_scientific_text_overrides(
    preparation: ScientificPreparation,
    *,
    x_title: str | None = None,
    y_title: str | None = None,
) -> ScientificPreparation:
    """Freeze user-confirmed axis wording without changing the source table.

    Category and subgroup labels remain source-bound.  Only explicit X/Y title
    overrides are accepted, and the resulting text is included in the shared
    preview/Origin plan digest.
    """

    def normalized(value: str | None, field: str, fallback: str) -> str:
        if value is None:
            return fallback
        text = str(value).strip()
        if not text or any(character in text for character in "\r\n\x00"):
            raise ScientificWorkflowError(
                "axis_title_invalid",
                f"{field} must be one non-empty line of text.",
            )
        if len(text) > 120:
            raise ScientificWorkflowError(
                "axis_title_too_long",
                f"{field} must not exceed 120 characters.",
            )
        return text

    spec = preparation.plot_spec
    resolved_x_title = normalized(x_title, "X axis title", spec.x_title)
    resolved_y_title = normalized(y_title, "Y axis title", spec.y_title)
    if preparation.template_id == "trajectory3d":
        if _alias_score(resolved_x_title, _TRAJECTORY3D_X_ALIASES) == 0:
            raise ScientificWorkflowError(
                "trajectory3d_x_title_semantics_missing",
                "The trajectory3d X-axis title must still identify Zreal/real impedance.",
            )
        if _trajectory3d_semantic_axis(resolved_y_title) is None:
            raise ScientificWorkflowError(
                "trajectory3d_third_axis_unit_missing",
                "The trajectory3d Y-axis title must retain its scientific meaning and unit.",
            )
    elif preparation.template_id == "density_ridgeline3d":
        if _density_ridgeline3d_semantic_axis(resolved_x_title, condition_axis=False) is None:
            raise ScientificWorkflowError(
                "density_ridgeline3d_x_axis_semantics_missing",
                "The Density X title must retain its scientific meaning and unit or "
                "explicit dimensionless status.",
            )
        if _density_ridgeline3d_semantic_axis(resolved_y_title, condition_axis=True) is None:
            raise ScientificWorkflowError(
                "density_ridgeline3d_condition_axis_semantics_missing",
                "The condition-axis title must retain a scientific meaning and unit or "
                "explicit Year semantics.",
            )
    overridden = replace(
        spec,
        x_title=resolved_x_title,
        y_title=resolved_y_title,
    )
    if overridden == spec:
        return preparation
    return replace(
        preparation,
        plot_spec=overridden,
        plan_digest=_scientific_plan_digest(preparation, overridden),
    )


_PALETTE_OVERRIDE_MODE_BY_TEMPLATE: dict[str, str] = {
    "eis": "qualitative",
    "cv": "qualitative",
    "lsv": "qualitative",
    "xas": "qualitative",
    "xrd": "qualitative",
    "bar": "qualitative",
    "horizontal_bar": "qualitative",
    "stacked_bar": "qualitative",
    "percent_stacked_bar": "qualitative",
    "pie": "qualitative",
    "sankey": "qualitative",
    "circular_network": "qualitative",
    "scatter": "accent",
    "line_error": "qualitative",
    "trend": "sequential",
    "radar": "qualitative",
    "raw_summary": "qualitative",
    "violin": "qualitative",
    "histogram": "accent",
    "bubble": "qualitative",
    "paired_trajectory": "qualitative",
    "raincloud": "qualitative",
    "grouped_box": "qualitative",
    "pl": "qualitative",
    "uv_vis": "qualitative",
    "trajectory3d": "qualitative",
    "density_ridgeline3d": "qualitative",
}


def apply_scientific_palette_override(
    preparation: ScientificPreparation,
    *,
    palette_id: str,
) -> ScientificPreparation:
    """Freeze a compatible user palette into the shared preview/Origin plan.

    Semantic routes such as signed effects, heatmaps, diagnostic curves, and
    confusion matrices deliberately keep their verified colour contracts.
    """

    requested = str(palette_id).strip()
    palette = get_palette(requested)
    required_mode = _PALETTE_OVERRIDE_MODE_BY_TEMPLATE.get(preparation.template_id)
    if required_mode is None:
        raise ScientificWorkflowError(
            "palette_override_unsupported",
            f"Template {preparation.template_id} keeps a semantic colour contract.",
        )
    if required_mode not in palette.allowed_modes:
        raise ScientificWorkflowError(
            "palette_mode_incompatible",
            f"Palette {requested} does not support {required_mode} use.",
        )
    spec = preparation.plot_spec
    style = spec.display_plan.figure_style
    if style is None:
        raise ScientificWorkflowError(
            "palette_override_unsupported",
            "The selected template has no adaptive Origin style to override.",
        )
    if preparation.template_id == "pie":
        category_count = len(spec.category_order)
    elif preparation.template_id == "grouped_box":
        category_count = len(spec.group_order)
    elif preparation.template_id == "circular_network":
        category_count = max(1, len(spec.group_order))
    elif preparation.template_id == "density_ridgeline3d":
        category_count = max(1, len(spec.group_order))
    else:
        category_count = len(spec.series)
    if required_mode == "qualitative" and category_count > palette.max_qualitative_categories:
        raise ScientificWorkflowError(
            "palette_category_limit_exceeded",
            (
                f"Palette {requested} supports at most "
                f"{palette.max_qualitative_categories} qualitative groups; "
                f"this plan has {category_count}."
            ),
        )
    overridden_style = replace(style, palette_name=requested)
    overridden_display = replace(spec.display_plan, figure_style=overridden_style)
    overridden_spec = replace(spec, display_plan=overridden_display)
    return replace(
        preparation,
        plot_spec=overridden_spec,
        plan_digest=_scientific_plan_digest(preparation, overridden_spec),
    )


@dataclass(frozen=True)
class _AutoMapping:
    assignments: dict[str, str]
    plot_mode: str
    confidence: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


_X_ALIASES: dict[str, tuple[str, ...]] = {
    "cv": (
        "potential",
        "voltage",
        "ewe",
        "e/v",
        "电位",
        "电压",
        "扫描电位",
    ),
    "lsv": (
        "potential",
        "voltage",
        "ewe",
        "e/v",
        "电位",
        "电压",
        "扫描电位",
    ),
    "xas": ("photonenergy", "energy", "能量", "光子能量"),
    "xrd": ("twotheta", "2theta", "diffractionangle", "衍射角", "两倍衍射角"),
    "scatter": ("x", "xvalue", "independent", "自变量", "横坐标"),
    "line_error": (
        "x",
        "xvalue",
        "time",
        "wavelength",
        "temperature",
        "concentration",
        "dose",
        "independent",
        "时间",
        "波长",
        "温度",
        "浓度",
        "自变量",
    ),
    "trend": (
        "x",
        "xvalue",
        "time",
        "step",
        "epoch",
        "dose",
        "independent",
        "时间",
        "步数",
        "剂量",
        "自变量",
    ),
    "bubble": (
        "x",
        "xvalue",
        "independent",
        "exposure",
        "time",
        "dose",
        "自变量",
        "暴露",
        "时间",
        "剂量",
    ),
    "diagnostic_curve": (
        "fpr",
        "falsepositiverate",
        "recall",
        "sensitivity",
        "假阳性率",
        "召回率",
        "敏感度",
    ),
    "paired_trajectory": (
        "time",
        "visit",
        "conditionindex",
        "condition",
        "时间",
        "访视",
        "条件序号",
        "条件",
    ),
    "calibration_curve": (
        "predictedprobability",
        "meanpredictedprobability",
        "predictedrisk",
        "预测概率",
        "平均预测概率",
        "预测风险",
    ),
    "decision_curve": (
        "threshold",
        "thresholdprobability",
        "probabilitythreshold",
        "阈值",
        "阈值概率",
    ),
    "dsc": (
        "temperature",
        "temp",
        "temperaturec",
        "温度",
    ),
    "nmr": (
        "chemicalshift",
        "shiftppm",
        "ppm",
        "化学位移",
        "位移",
        "核磁位移",
    ),
    "ftir": (
        "wavenumber",
        "wave number",
        "cm-1",
        "cm^-1",
        "波数",
        "红外波数",
    ),
    "xps_compare": (
        "bindingenergy",
        "binding energy",
        "bindingenergyev",
        "beev",
        "结合能",
        "结合能ev",
    ),
    "pl": (
        "wavelength",
        "emissionwavelength",
        "time",
        "decaytime",
        "波长",
        "发射波长",
        "时间",
        "寿命时间",
    ),
    "uv_vis": (
        "wavelength",
        "wavelengthnm",
        "lambda",
        "波长",
        "波长nm",
    ),
}

_FIT_ALIASES = ("fit", "fitted", "fitting", "拟合", "拟合曲线")
_PHOTON_ENERGY_ALIASES = (
    "photonenergy",
    "hv",
    "hnu",
    "光子能量",
)
_TAUC_VALUE_ALIASES = (
    "taucvalue",
    "tauc",
    "alphahv",
    "tauc纵轴",
    "tauc值",
)
_TAUC_FIT_ALIASES = ("taucfit", "taucfitting", "tauc拟合", "带隙拟合")
_BANDGAP_ALIASES = ("bandgap", "eg", "energygap", "带隙", "禁带宽度")
_MATERIAL_SIGNAL_ALIASES: dict[str, tuple[str, ...]] = {
    "dsc": ("heatflow", "heat flow", "dsc", "热流", "热流率"),
    "nmr": ("intensity", "signal", "spectrum", "nmr", "强度", "信号", "谱"),
    "ftir": (
        "transmittance",
        "transmission",
        "absorbance",
        "absorption",
        "intensity",
        "ftir",
        "infrared",
        "透过率",
        "透射",
        "吸光度",
        "吸收",
        "强度",
        "红外",
    ),
    "pl": ("pl", "intensity", "emission", "fluorescence", "强度", "发光", "荧光"),
    "uv_vis": (
        "absorbance",
        "absorption",
        "transmittance",
        "transmission",
        "uv",
        "optical",
        "吸光度",
        "吸收",
        "透过率",
        "透射",
        "光学",
    ),
    "xps_compare": (
        "intensity",
        "counts",
        "count",
        "experimental",
        "measured",
        "raw",
        "signal",
        "强度",
        "计数",
        "实测",
        "原始",
        "信号",
    ),
}
_XPS_FIT_COLUMN_ALIASES = (
    "background",
    "baseline",
    "envelope",
    "fit",
    "fitted",
    "residual",
    "difference",
    "component",
    "peak",
    "背景",
    "基线",
    "包络",
    "拟合",
    "残差",
    "差值",
    "分峰",
    "峰组分",
)
_MATERIAL_NUMERIC_METADATA_ALIASES = (
    "time",
    "cycle",
    "scan",
    "segment",
    "program",
    "step",
    "index",
    "mass",
    "weight",
    "rate",
    "duration",
    "timestamp",
    "时间",
    "循环",
    "扫描",
    "程序",
    "步骤",
    "序号",
    "质量",
    "速率",
    "时长",
)

_TRAJECTORY3D_X_ALIASES = (
    "zreal",
    "z real",
    "z'",
    "rez",
    "realimpedance",
    "real impedance",
    "阻抗实部",
)
_TRAJECTORY3D_Y_ALIASES = (
    "conditionposition",
    "condition position",
    "position",
    "temperature",
    "concentration",
    "pressure",
    "distance",
    "time",
    "scanrate",
    "magneticfield",
    "条件位置",
    "位置",
    "温度",
    "浓度",
    "压力",
    "距离",
    "时间",
    "扫描速率",
    "磁场",
)
_TRAJECTORY3D_Z_ALIASES = (
    "-zimag",
    "negativezimag",
    "negative imaginary impedance",
    "-z''",
    "minuszimag",
    "负阻抗虚部",
    "负虚部",
)
_TRAJECTORY3D_SERIES_ALIASES = (
    "series",
    "seriesid",
    "sample",
    "sampleid",
    "group",
    "conditionname",
    "系列",
    "样品",
    "样品编号",
    "组别",
)

_DENSITY3D_CONDITION_ID_ALIASES = (
    "condition",
    "conditionid",
    "condition id",
    "conditionlabel",
    "condition label",
    "groupid",
    "group",
    "sample",
    "条件编号",
    "条件名称",
    "条件标签",
    "组别",
    "样品",
)
_DENSITY3D_CONDITION_POSITION_ALIASES = (
    "conditionposition",
    "condition position",
    "position",
    "year",
    "followuptime",
    "follow-up time",
    "timepoint",
    "time point",
    "temperature",
    "concentration",
    "条件位置",
    "位置",
    "年份",
    "时间点",
    "温度",
    "浓度",
)
_DENSITY3D_X_ALIASES = (
    "densityx",
    "density x",
    "score",
    "responsescore",
    "response score",
    "hscore",
    "metric",
    "measurement",
    "密度横坐标",
    "得分",
    "评分",
    "指标值",
    "测量值",
)
_DENSITY3D_SOLID_ALIASES = (
    "densitysolid",
    "solid density",
    "solidprofile",
    "solid profile",
    "primarydensity",
    "实线密度",
    "实线曲线",
    "主密度",
)
_DENSITY3D_DASHED_ALIASES = (
    "densitydashed",
    "dashed density",
    "dashedprofile",
    "dashed profile",
    "secondarydensity",
    "虚线密度",
    "虚线曲线",
    "次密度",
)
_DENSITY3D_FOCAL_X_ALIASES = (
    "focalx",
    "focal x",
    "focusx",
    "focus x",
    "焦点横坐标",
    "焦点",
)

_CATEGORY_ALIASES = (
    "category",
    "actualclass",
    "trueclass",
    "group",
    "sample",
    "condition",
    "dataset",
    "metric",
    "indicator",
    "dimension",
    "label",
    "类别",
    "实际类别",
    "真实类别",
    "组别",
    "样品",
    "条件",
    "数据集",
    "指标",
    "维度",
    "标签",
)

_SOURCE_ALIASES = ("source", "from", "origin", "起点", "来源", "源节点")
_TARGET_ALIASES = ("target", "to", "destination", "终点", "目标", "目标节点")
_VALUE_ALIASES = ("value", "weight", "flow", "amount", "数值", "权重", "流量")
_PANEL_ALIASES = (
    "panel",
    "period",
    "timeperiod",
    "time window",
    "window",
    "stage",
    "面板",
    "子图",
    "时期",
    "时段",
    "时间段",
    "阶段",
    "窗口",
)
_SIGN_ALIASES = (
    "sign",
    "direction",
    "polarity",
    "association",
    "edge sign",
    "符号",
    "方向",
    "正负",
    "关系方向",
)
_SOURCE_GROUP_ALIASES = (
    "sourcegroup",
    "source group",
    "fromgroup",
    "起点组",
    "来源组",
    "源节点组",
)
_TARGET_GROUP_ALIASES = (
    "targetgroup",
    "target group",
    "togroup",
    "终点组",
    "目标组",
    "目标节点组",
)
_EDGE_LABEL_ALIASES = (
    "edgelabel",
    "edge label",
    "linklabel",
    "relationlabel",
    "边标签",
    "连线标签",
    "关系标签",
)
_SIZE_ALIASES = (
    "size",
    "magnitude",
    "abundance",
    "count",
    "samplesize",
    "bubble",
    "大小",
    "规模",
    "丰度",
    "数量",
    "样本量",
)
_ESTIMATE_ALIASES = (
    "estimate",
    "effect",
    "difference",
    "coefficient",
    "mean difference",
    "估计值",
    "效应量",
    "差值",
    "系数",
)
_LOWER_ALIASES = (
    "cilow",
    "lowerci",
    "lowerbound",
    "lower",
    "ci lower",
    "置信区间下限",
    "下限",
)
_UPPER_ALIASES = (
    "cihigh",
    "upperci",
    "upperbound",
    "upper",
    "ci upper",
    "置信区间上限",
    "上限",
)
_REFERENCE_ALIASES = (
    "reference",
    "null",
    "baseline",
    "referencevalue",
    "参考值",
    "零效应",
    "基线值",
)
_MEAN_ALIASES = ("mean", "pairmean", "average", "均值", "配对均值", "平均值")
_DIFFERENCE_ALIASES = ("difference", "diff", "methoddifference", "差值", "方法差")
_BIAS_ALIASES = ("bias", "meandifference", "偏倚", "平均差")
_LOA_LOWER_ALIASES = (
    "lowerloa",
    "loalower",
    "lowerlimitofagreement",
    "一致性下限",
    "下限loa",
)
_LOA_UPPER_ALIASES = (
    "upperloa",
    "loaupper",
    "upperlimitofagreement",
    "一致性上限",
    "上限loa",
)
_PREVALENCE_ALIASES = ("prevalence", "baseline", "患病率", "阳性率基线")
_COUNT_ALIASES = ("bincount", "count", "samplesize", "frequency", "样本数", "频数", "计数")
_OBSERVED_FRACTION_ALIASES = (
    "observedfraction",
    "observedprobability",
    "eventrate",
    "observedrisk",
    "观察比例",
    "实际发生率",
    "观察风险",
)
_TREAT_ALL_ALIASES = (
    "treatall",
    "treat all",
    "all",
    "全部干预",
    "全部治疗",
    "全阳性",
)
_TREAT_NONE_ALIASES = (
    "treatnone",
    "treat none",
    "none",
    "不干预",
    "不治疗",
    "全阴性",
)
_FEATURE_ALIASES = (
    "feature",
    "feature name",
    "variable",
    "predictor",
    "特征",
    "特征名",
    "变量",
    "预测因子",
)
_SHAP_VALUE_ALIASES = (
    "shapvalue",
    "shap value",
    "shap",
    "shap值",
    "特征贡献",
    "贡献值",
)
_FEATURE_VALUE_ALIASES = (
    "featurevalue",
    "feature value",
    "rawfeaturevalue",
    "raw feature value",
    "特征值",
    "原始特征值",
)
_SAMPLE_ID_ALIASES = (
    "sampleid",
    "sample id",
    "caseid",
    "case id",
    "patientid",
    "patient id",
    "样本编号",
    "样本id",
    "病例编号",
)
_FEATURE_ORDER_ALIASES = (
    "featureorder",
    "feature order",
    "displayorder",
    "display order",
    "特征顺序",
    "显示顺序",
    "特征排序",
)
_MEAN_ABS_SHAP_ALIASES = (
    "meanabsoluteshap",
    "mean absolute shap",
    "meanabsshap",
    "mean abs shap",
    "mean|shap|",
    "平均绝对shap",
    "平均绝对shap值",
    "平均绝对贡献",
)
_FEATURE_GROUP_ALIASES = (
    "featuregroup",
    "feature group",
    "domain",
    "featuredomain",
    "特征组",
    "指标类别",
    "特征领域",
)
_GROUP_CONTRIBUTION_ALIASES = (
    "groupcontribution",
    "group contribution",
    "groupcontributionpercent",
    "group contribution percent",
    "grouppercent",
    "组贡献百分比",
    "分组贡献",
    "组占比",
)

_ROLE_LABELS: dict[str, str] = {
    "x": "X / 自变量",
    "series": "Series / 数据系列",
    "observed": "Observed / 实测强度",
    "calculated": "Calculated / 计算强度",
    "background": "Background / 背景",
    "phase_tick": "Phase tick / 物相刻线",
    "support": "Support / 辅助或控制数据",
    "error": "Error / 误差",
    "category": "Category / 类别",
    "z_real": "Z real / 阻抗实部",
    "z_imag": "Z imaginary / 阻抗虚部",
    "frequency": "Frequency / 频率",
    "magnitude": "|Z| / 阻抗模",
    "phase": "Phase / 相位",
    "source": "Source / 起点",
    "target": "Target / 终点",
    "value": "Value / 权重",
    "panel": "Panel / 面板或时期",
    "sign": "Sign / 边的正负方向",
    "source_group": "Source group / 起点类别",
    "target_group": "Target group / 终点类别",
    "edge_label": "Edge label / 原始边标签",
    "size": "Size / 大小",
    "estimate": "Estimate / 估计值",
    "lower": "CI lower / 区间下限",
    "upper": "CI upper / 区间上限",
    "reference": "Reference / 参考值",
    "mean": "Pair mean / 配对均值",
    "difference": "Difference / 差值",
    "bias": "Bias / 偏倚",
    "loa_lower": "Lower LoA / 一致性下限",
    "loa_upper": "Upper LoA / 一致性上限",
    "count": "Bin count / 分箱样本数",
    "treat_all": "Treat all / 全部干预",
    "treat_none": "Treat none / 不干预",
    "feature": "Feature / 特征",
    "shap": "SHAP value / SHAP 值",
    "feature_value": "Feature value / 特征值",
    "sample_id": "Sample ID / 样本编号",
    "feature_order": "Feature order / 特征顺序",
    "mean_abs_shap": "Mean |SHAP| / 平均绝对 SHAP",
    "feature_group": "Feature group / 特征组",
    "group_contribution": "Group contribution (%) / 组贡献百分比",
    "fit": "Fit / 用户提供拟合",
    "photon_energy": "Photon energy / 光子能量",
    "tauc": "Tauc value / 用户提供 Tauc 值",
    "tauc_fit": "Tauc fit / 用户提供 Tauc 拟合",
    "bandgap": "Band gap / 用户提供带隙",
    "x3d": "X = Zreal / 阻抗实部",
    "y3d": "Y = real condition / 真实第三变量（带单位）",
    "z3d": "Z = -Zimag / 负阻抗虚部",
    "series_id": "Series / 轨迹组名",
    "condition_id": "Condition / 条件组名",
    "condition_position": "Condition position / 条件位置",
    "density_x": "Density X / 密度横坐标",
    "density_solid": "Solid density / 实线密度",
    "density_dashed": "Dashed density / 虚线密度",
    "focal_x": "Focal X / 焦点横坐标",
    "ignored": "忽略",
}


def role_label(role: str) -> str:
    return _ROLE_LABELS.get(role, role)


def role_options(template_id: str) -> tuple[tuple[str, str, bool], ...]:
    """Return role key, bilingual label, and uniqueness for the mapping UI."""
    if template_id == "xrd":
        keys = (
            "x",
            "observed",
            "calculated",
            "background",
            "difference",
            "phase_tick",
            "support",
            "series",
            "ignored",
        )
        unique = {"x", "observed", "calculated", "background", "difference"}
    elif template_id == "trajectory3d":
        keys = ("x3d", "y3d", "z3d", "series_id", "ignored")
        unique = {"x3d", "y3d", "z3d", "series_id"}
    elif template_id == "density_ridgeline3d":
        keys = (
            "condition_id",
            "condition_position",
            "density_x",
            "density_solid",
            "density_dashed",
            "focal_x",
            "ignored",
        )
        unique = set(keys) - {"ignored"}
    elif template_id == "eis":
        keys = ("z_real", "z_imag", "frequency", "magnitude", "phase", "ignored")
        unique = set(keys) - {"ignored"}
    elif template_id == "sankey":
        keys = ("source", "target", "value", "ignored")
        unique = {"source", "target", "value"}
    elif template_id == "circular_network":
        keys = (
            "panel",
            "source",
            "target",
            "value",
            "sign",
            "source_group",
            "target_group",
            "edge_label",
            "ignored",
        )
        unique = set(keys) - {"ignored"}
    elif template_id in {"raw_summary", "violin", "histogram", "raincloud", "grouped_box"}:
        keys = ("series", "ignored")
        unique = set()
    elif template_id == "pl":
        keys = ("x", "series", "fit", "ignored")
        unique = {"x"}
    elif template_id == "uv_vis":
        keys = (
            "x",
            "series",
            "photon_energy",
            "tauc",
            "tauc_fit",
            "bandgap",
            "ignored",
        )
        unique = {"x", "photon_energy", "tauc", "tauc_fit", "bandgap"}
    elif template_id == "shap_summary":
        keys = (
            "feature",
            "shap",
            "feature_value",
            "sample_id",
            "feature_order",
            "mean_abs_shap",
            "feature_group",
            "group_contribution",
            "ignored",
        )
        unique = set(keys) - {"ignored"}
    elif template_id == "bubble":
        keys = ("x", "series", "size", "ignored")
        unique = {"x", "size"}
    elif template_id == "forest":
        keys = ("category", "estimate", "lower", "upper", "reference", "ignored")
        unique = {"category", "estimate", "lower", "upper", "reference"}
    elif template_id == "bland_altman":
        keys = ("mean", "difference", "bias", "loa_lower", "loa_upper", "ignored")
        unique = {"mean", "difference", "bias", "loa_lower", "loa_upper"}
    elif template_id == "diagnostic_curve":
        keys = ("x", "series", "reference", "ignored")
        unique = {"x", "reference"}
    elif template_id == "calibration_curve":
        keys = ("x", "series", "count", "ignored")
        unique = {"x", "series", "count"}
    elif template_id == "decision_curve":
        keys = ("x", "series", "treat_all", "treat_none", "ignored")
        unique = {"x", "treat_all", "treat_none"}
    elif template_id in {"bar", "horizontal_bar", "stacked_bar"}:
        keys = ("category", "series", "error", "ignored")
        unique = {"category"}
    elif template_id in _CATEGORY_TABLE_TEMPLATE_IDS:
        keys = ("category", "series", "ignored")
        unique = {"category"}
    else:
        keys = (
            ("x", "series", "error", "ignored")
            if template_id == "line_error"
            else (
                "x",
                "series",
                "ignored",
            )
        )
        unique = {"x"}
    return tuple((key, role_label(key), key in unique) for key in keys)


def mapping_context_options(template_id: str) -> tuple[tuple[str, str], ...]:
    if template_id == "xrd":
        return (
            ("ordinary_scan", "普通 XRD 图谱"),
            ("rietveld_refinement", "Rietveld 精修图"),
        )
    if template_id == "eis":
        return (("nyquist", "Nyquist"), ("bode", "Bode"))
    if template_id == "shap_summary":
        return (
            ("beeswarm_only", "仅 SHAP 蜂群图"),
            ("beeswarm_mean_abs", "蜂群图 + Mean |SHAP|"),
            ("beeswarm_mean_abs_grouped", "蜂群图 + Mean |SHAP| + 分组贡献"),
        )
    if template_id == "diagnostic_curve":
        return (("roc", "ROC"), ("pr", "Precision–Recall"))
    if template_id == "pl":
        return (("steady_state", "Steady-state PL"), ("trpl", "TRPL decay"))
    if template_id in {"dsc", "nmr", "ftir", "xps_compare"}:
        return (
            ("overlay", "原始数值直接叠加"),
            ("stacked_offset", "仅显示用纵向错位（原始列不变）"),
        )
    return ()


def _canonical(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("θ", "theta").replace("μ", "mu").replace("ω", "ohm")
    text = text.replace("′", "'").replace("″", "''").replace("−", "-")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff'|+\-/]", "", text)


def _alias_score(header: str, aliases: tuple[str, ...]) -> int:
    canonical = _canonical(header)
    best = 0
    for alias in aliases:
        target = _canonical(alias)
        if not target:
            continue
        if canonical == target:
            best = max(best, 3)
        elif canonical.startswith(target) or canonical.endswith(target):
            best = max(best, 2)
        elif target in canonical:
            best = max(best, 1)
    return best


def _blank_mask(raw: pd.Series) -> pd.Series:
    missing = raw.isna()
    as_text = raw.astype(str).str.strip()
    return missing | as_text.eq("") | as_text.str.casefold().eq("nan")


def _coerce_numeric(raw: pd.Series, column: str) -> pd.Series:
    blank = _blank_mask(raw)
    converted = pd.to_numeric(raw.where(~blank, np.nan), errors="coerce").astype(float)
    bad = converted.isna() & ~blank
    if bool(bad.any()):
        index = int(np.flatnonzero(bad.to_numpy())[0])
        raise ScientificWorkflowError(
            "non_numeric",
            f"Column {column!r} contains a non-numeric value at data row {index + 2}.",
            column=column,
            row=index + 2,
        )
    finite = converted.isna() | np.isfinite(converted)
    if not bool(finite.all()):
        index = int(np.flatnonzero((~finite).to_numpy())[0])
        raise ScientificWorkflowError(
            "non_finite",
            f"Column {column!r} contains a non-finite value at data row {index + 2}.",
            column=column,
            row=index + 2,
        )
    return converted


def _numeric_compatible(raw: pd.Series) -> bool:
    try:
        converted = _coerce_numeric(raw, str(raw.name))
    except ScientificWorkflowError:
        return False
    return int(converted.notna().sum()) >= 1


def _material_numeric_role(column: str, template_id: str) -> str:
    """Classify a numeric non-X column without silently plotting metadata."""
    if _alias_score(column, _MATERIAL_SIGNAL_ALIASES[template_id]) > 0:
        return "signal"
    if _alias_score(column, _MATERIAL_NUMERIC_METADATA_ALIASES) > 0:
        return "metadata"
    return "uncertain"


def _select_x_column(frame: pd.DataFrame, template_id: str) -> tuple[str, float, tuple[str, ...]]:
    aliases = _X_ALIASES[template_id]
    scored = [(column, _alias_score(str(column), aliases)) for column in frame.columns]
    best_score = max((score for _, score in scored), default=0)
    winners = [str(column) for column, score in scored if score == best_score and score > 0]
    if len(winners) == 1:
        confidence = {3: 0.98, 2: 0.95, 1: 0.90}[best_score]
        return winners[0], confidence, ()
    numeric = [str(column) for column in frame.columns if _numeric_compatible(frame[column])]
    if not numeric:
        raise ScientificWorkflowError("x_missing", "No numeric X column could be identified.")
    reasons = ("x_role_ambiguous",) if len(winners) > 1 else ("x_role_inferred",)
    return (winners or numeric)[0], 0.62, reasons


def _error_info(column: str) -> tuple[str, str] | None:
    text = unicodedata.normalize("NFKC", column).strip()
    patterns = (
        (r"(?i)(?:[_\-\s]+|\()SEM\)?$", "sem"),
        (r"(?i)(?:[_\-\s]+|\()SD\)?$", "sd"),
        (r"(?i)(?:[_\-\s]+|\()SE\)?$", "se"),
        (r"(?i)(?:[_\-\s]+|\()(?:ERR|ERROR)\)?$", "custom"),
        (r"标准差$", "sd"),
        (r"标准误(?:差)?$", "se"),
        (r"误差$", "custom"),
    )
    for pattern, kind in patterns:
        match = re.search(pattern, text)
        if match:
            base = text[: match.start()].rstrip(" _-(（")
            return base, kind
    return None


def _physical_unit(column: str) -> str | None:
    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]\s*$", column)
    if not match:
        return None
    unit = match.group(1).strip()
    canonical = _canonical(unit)
    if unit in {"°C", "℃", "K", "%"} or canonical in {"c", "k", "nm", "ppm", "au"}:
        return unit
    known = (
        "v",
        "mv",
        "a",
        "ma",
        "ua",
        "na",
        "pa",
        "ev",
        "hz",
        "khz",
        "mhz",
        "ohm",
        "degree",
        "deg",
        "cm-1",
        "cm-2",
        "cm2",
        "s",
        "min",
        "h",
        "w/g",
        "mw/mg",
        "j/g",
        "kj/mol",
    )
    if not any(token in canonical for token in known):
        return None
    return unit


def _format_unit(unit: str) -> str:
    value = unicodedata.normalize("NFKC", unit).strip()
    if _canonical(value) in {"ohm", "omega"}:
        return "Ω"
    value = re.sub(r"(?i)cm\s*\^?\s*-\s*2", "cm⁻²", value)
    value = re.sub(r"(?i)cm\s*\^?\s*-\s*1", "cm⁻¹", value)
    return value


def _common_unit(columns: list[str]) -> str | None:
    units = [_physical_unit(column) for column in columns]
    if not units or any(unit is None for unit in units):
        return None
    canonical = {_canonical(unit) for unit in units if unit is not None}
    return _format_unit(units[0]) if len(canonical) == 1 and units[0] is not None else None


def _standard_line_axis_titles(
    template_id: str,
    x_column: str,
    series_columns: list[str],
) -> tuple[str, str]:
    x_unit = _physical_unit(x_column)
    if template_id == "xrd" and x_unit and "," in x_unit:
        # GSAS-II Publication headers commonly use ``X (2theta, deg)``.
        # ``2theta`` describes the coordinate rather than its unit, so retain
        # only the final, recognized angular unit in the public axis title.
        coordinate_hint, candidate_unit = x_unit.rsplit(",", maxsplit=1)
        if "2theta" in _canonical(coordinate_hint) and _canonical(candidate_unit) in {
            "deg",
            "degree",
            "degrees",
        }:
            x_unit = candidate_unit.strip()
    unit_suffix = f" ({_format_unit(x_unit)})" if x_unit else ""
    if template_id in {"cv", "lsv"}:
        x_title = f"Potential{unit_suffix}"
        y_unit = _common_unit(series_columns)
        density = any(
            any(token in _canonical(column) for token in ("currentdensity", "电流密度"))
            for column in series_columns
        ) or bool(y_unit and "cm⁻²" in y_unit)
        y_title = "Current density" if density else "Current"
        if y_unit:
            y_title += f" ({y_unit})"
        return x_title, y_title
    if template_id == "xas":
        x_title = f"Energy{unit_suffix}"
        y_title = series_columns[0] if len(series_columns) == 1 else "Absorption signal"
        return x_title, y_title
    if template_id == "xrd":
        return f"2θ{unit_suffix}", "Intensity (a.u.)"
    if template_id == "scatter":
        return x_column, series_columns[0] if len(series_columns) == 1 else "Response"
    return x_column, series_columns[0] if len(series_columns) == 1 else "Value"


def _automatic_line_mapping(loaded: LoadedTable, template_id: str) -> _AutoMapping:
    x_column, confidence, reasons = _select_x_column(loaded.frame, template_id)
    assignments = {
        str(column): ("x" if str(column) == x_column else "series") for column in loaded.frame.columns
    }
    warnings = list(reasons)
    return _AutoMapping(assignments, "default", confidence, reasons, tuple(warnings))


def _automatic_xrd_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Map XRD columns from the source-bound semantic proposal.

    Unknown numeric columns are assigned to the non-rendering support role as a
    safe suggestion, but their blocking ambiguity remains visible to the user.
    """

    try:
        proposal = propose_xrd_semantics(loaded)
        source_profile = detect_xrd_source_profile(loaded)
    except XrdSemanticError as exc:
        raise ScientificWorkflowError(
            exc.code,
            str(exc),
            column=(
                str(exc.details["columns"][0])
                if isinstance(exc.details.get("columns"), list) and exc.details["columns"]
                else None
            ),
        ) from exc

    role_map = {
        "x_coordinate": "x",
        "intensity_series": "series",
        "observed_intensity": "observed",
        "calculated_intensity": "calculated",
        "background_intensity": "background",
        "difference_curve": "difference",
        "phase_reflection_positions": "phase_tick",
        "statistical_weight": "support",
        "alternative_q_coordinate": "support",
        "fit_mask": "support",
        "weighted_residual_diagnostic": "support",
        "upstream_axis_limits": "support",
        "phase_tick_position_control": "support",
        "unbound_phase_tick_metadata": "support",
        "unclassified_numeric": "support",
        "unclassified_metadata": "ignored",
    }
    has_identified_ordinary_series = any(
        item.semantic_role == "intensity_series" for item in proposal.data_items
    )
    assignments: dict[str, str] = {}
    for item in proposal.data_items:
        role = role_map.get(item.semantic_role, "support")
        if (
            source_profile == "ordinary_xrd"
            and item.semantic_role == "unclassified_numeric"
            and not has_identified_ordinary_series
        ):
            # Keep generic numeric-wide data reachable through the confirmation
            # UI; no such suggested series can render before user approval.
            role = "series"
        assignments[item.source_column] = role
    reasons = [ambiguity.code for ambiguity in proposal.ambiguities if ambiguity.blocking]
    if source_profile == "generic_rietveld":
        reasons.append("xrd_generic_rietveld_requires_confirmation")
    reasons = list(dict.fromkeys(reasons))
    confidence = min(proposal.domain_confidence, 0.68) if reasons else proposal.domain_confidence
    return _AutoMapping(
        assignments=assignments,
        plot_mode=proposal.domain_mode,
        confidence=confidence,
        reasons=tuple(reasons),
        warnings=tuple(reasons),
    )


def _automatic_error_mapping(loaded: LoadedTable, template_id: str) -> _AutoMapping:
    frame = loaded.frame
    if template_id in _CATEGORY_TABLE_TEMPLATE_IDS:
        scores = [(str(column), _alias_score(str(column), _CATEGORY_ALIASES)) for column in frame.columns]
        best = max((score for _, score in scores), default=0)
        winners = [column for column, score in scores if score == best and score > 0]
        if len(winners) == 1:
            anchor = winners[0]
            confidence = 0.98 if best == 3 else 0.94
            reasons: tuple[str, ...] = ()
        else:
            nonnumeric = [str(column) for column in frame.columns if not _numeric_compatible(frame[column])]
            anchor = (winners or nonnumeric or [str(frame.columns[0])])[0]
            confidence = 0.65
            reasons = ("category_role_inferred",)
        anchor_role = "category"
    else:
        anchor, confidence, reasons = _select_x_column(frame, template_id)
        anchor_role = "x"

    assignments: dict[str, str] = {}
    warnings = list(reasons)
    for column in map(str, frame.columns):
        if column == anchor:
            assignments[column] = anchor_role
        elif (
            template_id in {"bar", "horizontal_bar", "stacked_bar", "line_error"}
            and _error_info(column) is not None
        ):
            assignments[column] = "error"
            if _error_info(column)[1] == "custom":  # type: ignore[index]
                warnings.append("error_kind_unspecified")
        else:
            assignments[column] = "series"
    custom_error = "error_kind_unspecified" in warnings
    if custom_error:
        reasons = tuple((*reasons, "error_kind_unspecified"))
        confidence = min(confidence, 0.72)
    return _AutoMapping(assignments, "default", confidence, reasons, tuple(dict.fromkeys(warnings)))


def _automatic_sankey_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    role_aliases = {
        "source": _SOURCE_ALIASES,
        "target": _TARGET_ALIASES,
        "value": _VALUE_ALIASES,
    }
    selected: dict[str, str] = {}
    reasons: list[str] = []
    for role, aliases in role_aliases.items():
        scored = [(str(column), _alias_score(str(column), aliases)) for column in frame.columns]
        best = max((score for _, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if len(winners) == 1 and winners[0] not in selected.values():
            selected[role] = winners[0]
        elif len(winners) > 1:
            selected[role] = winners[0]
            reasons.append(f"{role}_role_ambiguous")

    if "value" not in selected:
        numeric = [
            str(column)
            for column in frame.columns
            if str(column) not in selected.values() and _numeric_compatible(frame[column])
        ]
        if numeric:
            selected["value"] = numeric[0]
            reasons.append("value_role_inferred")
    remaining_text = [
        str(column)
        for column in frame.columns
        if str(column) not in selected.values() and not _numeric_compatible(frame[column])
    ]
    for role in ("source", "target"):
        if role not in selected and remaining_text:
            selected[role] = remaining_text.pop(0)
            reasons.append(f"{role}_role_inferred")
    if set(selected) != {"source", "target", "value"}:
        raise ScientificWorkflowError(
            "sankey_roles_missing",
            "Sankey data needs one source, one target, and one numeric value column.",
        )
    if len(set(selected.values())) != 3:
        raise ScientificWorkflowError(
            "sankey_roles_conflict",
            "Source, target, and value must use three different columns.",
        )
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.97 if not reasons else 0.66
    return _AutoMapping(
        assignments,
        "default",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_circular_network_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Map a temporal directed edge list without inventing missing columns."""

    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    aliases_by_role = {
        "panel": _PANEL_ALIASES,
        # Match the more specific optional headers before generic Source and
        # Target aliases, so SourceGroup can never be stolen as a source node.
        "source_group": _SOURCE_GROUP_ALIASES,
        "target_group": _TARGET_GROUP_ALIASES,
        "edge_label": _EDGE_LABEL_ALIASES,
        "sign": _SIGN_ALIASES,
        "source": _SOURCE_ALIASES,
        "target": _TARGET_ALIASES,
        "value": _VALUE_ALIASES,
    }
    selected: dict[str, str] = {}
    reasons: list[str] = []
    used_columns: set[str] = set()
    for role, aliases in aliases_by_role.items():
        scored = [
            (str(column), _alias_score(str(column), aliases))
            for column in frame.columns
            if str(column) not in used_columns
        ]
        best = max((score for _, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if len(winners) == 1:
            selected[role] = winners[0]
            used_columns.add(winners[0])
            if best < 3:
                reasons.append(f"{role}_role_inferred")
        elif len(winners) > 1:
            selected[role] = winners[0]
            used_columns.add(winners[0])
            reasons.append(f"{role}_role_ambiguous")

    if "value" not in selected:
        numeric = [
            str(column)
            for column in frame.columns
            if str(column) not in used_columns and _numeric_compatible(frame[column])
        ]
        if numeric:
            selected["value"] = numeric[0]
            used_columns.add(numeric[0])
            reasons.append("value_role_inferred")

    remaining_text = [
        str(column)
        for column in frame.columns
        if str(column) not in used_columns and not _numeric_compatible(frame[column])
    ]
    for role in ("panel", "source", "target"):
        if role not in selected and remaining_text:
            selected[role] = remaining_text.pop(0)
            used_columns.add(selected[role])
            reasons.append(f"{role}_role_inferred")

    required = {"panel", "source", "target", "value"}
    if not required.issubset(selected):
        missing = ", ".join(sorted(required - set(selected)))
        raise ScientificWorkflowError(
            "circular_network_roles_missing",
            (
                "Circular network data needs Panel, Source, Target, and a positive "
                f"numeric Weight column. Missing role(s): {missing}."
            ),
        )
    if len({selected[role] for role in required}) != len(required):
        raise ScientificWorkflowError(
            "circular_network_roles_conflict",
            "Panel, Source, Target, and Weight must use four different columns.",
        )
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.98 if not reasons else 0.66
    return _AutoMapping(
        assignments,
        "default",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_raw_distribution_mapping(
    loaded: LoadedTable,
    template_id: str,
) -> _AutoMapping:
    """Map wide raw observations without inventing summaries or grouping."""
    assignments: dict[str, str] = {}
    ignored: list[str] = []
    for column in map(str, loaded.frame.columns):
        if _numeric_compatible(loaded.frame[column]):
            assignments[column] = "series"
        else:
            assignments[column] = "ignored"
            ignored.append(column)
    if not any(role == "series" for role in assignments.values()):
        raise ScientificWorkflowError(
            "raw_series_missing",
            f"{template_id} needs at least one numeric raw-observation column.",
        )
    reasons = ("nonnumeric_columns_ignored",) if ignored else ()
    confidence = 0.78 if ignored else 0.98
    return _AutoMapping(assignments, "wide_raw", confidence, reasons, reasons)


def _trajectory3d_semantic_axis(header: str) -> tuple[str, str] | None:
    """Return a real third-axis name/unit pair encoded in the source header."""
    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]\s*$", header)
    if match is None:
        return None
    unit = match.group(1).strip()
    meaning = header[: match.start()].strip(" _-/")
    if not meaning or not unit:
        return None
    if _canonical(meaning) in {
        "y",
        "axisy",
        "index",
        "condition",
        "value",
        "variable",
        "纵轴",
        "序号",
        "条件",
        "数值",
    }:
        return None
    return meaning, unit


def _density_ridgeline3d_semantic_axis(
    header: str,
    *,
    condition_axis: bool,
) -> tuple[str, str] | None:
    """Require an interpretable axis name plus unit for scientific 3D use."""

    canonical = _canonical(header)
    if condition_axis and (
        canonical in {"year", "年份", "年度"}
        or canonical.endswith("year")
        or canonical.endswith("年份")
    ):
        return header.strip(), "year"

    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]\s*$", header)
    if match is None:
        dimensionless_tokens = ("unitless", "dimensionless", "无量纲")
        if condition_axis or not any(token in canonical for token in dimensionless_tokens):
            return None
        meaning = header
        for token in dimensionless_tokens:
            meaning = re.sub(re.escape(token), "", meaning, flags=re.IGNORECASE)
        meaning = meaning.strip(" _-/()[]")
        unit = "dimensionless"
    else:
        meaning = header[: match.start()].strip(" _-/")
        unit = match.group(1).strip()
    if not meaning or not unit:
        return None
    generic_meanings = (
        {"y", "axisy", "index", "condition", "value", "variable", "纵轴", "序号", "条件", "数值"}
        if condition_axis
        else {"x", "axisx", "index", "coordinate", "value", "variable", "横轴", "序号", "坐标", "数值"}
    )
    if _canonical(meaning) in generic_meanings:
        return None
    if _canonical(unit) in {"unit", "units", "单位"}:
        return None
    return meaning, unit


def _density_ridgeline3d_density_unit(header: str) -> tuple[str, str] | None:
    """Return a comparison key and frozen display unit for a density column."""

    semantic = _density_ridgeline3d_semantic_axis(header, condition_axis=False)
    if semantic is None:
        return None
    meaning, unit = semantic
    if not any(token in _canonical(meaning) for token in ("density", "密度")):
        return None
    canonical_unit = _canonical(unit)
    if canonical_unit in {"dimensionless", "unitless", "无量纲"}:
        return "dimensionless", "dimensionless"
    if canonical_unit in {
        "au",
        "arbunit",
        "arbunits",
        "arbitraryunit",
        "arbitraryunits",
    }:
        return "au", "a.u."
    if not canonical_unit:
        return None
    return canonical_unit, _format_unit(unit)


def density_ridgeline3d_contract_issues(
    frame: pd.DataFrame,
    role_columns: dict[str, str],
) -> tuple[str, ...]:
    """Return deterministic strict-detection issues for the density 3D route.

    This helper is deliberately read-only and mirrors the scientific contract
    enforced by :func:`_build_density_ridgeline3d_spec`.  The public Skill CLI
    imports it after bootstrapping the bundled runtime so inspection and actual
    preparation cannot drift into two different definitions of "strict".
    """

    required_roles = (
        "condition_id",
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    )
    issues: list[str] = []

    missing_roles = [role for role in required_roles if role not in role_columns]
    if missing_roles:
        return tuple(f"{role}_role_not_unique" for role in missing_roles)
    selected_columns = [role_columns[role] for role in required_roles]
    if len(set(selected_columns)) != len(selected_columns):
        return ("density_role_columns_not_distinct",)
    missing_columns = [column for column in selected_columns if column not in frame.columns]
    if missing_columns:
        return tuple(f"{column}_column_missing" for column in missing_columns)

    position_column = role_columns["condition_position"]
    x_column = role_columns["density_x"]
    solid_column = role_columns["density_solid"]
    dashed_column = role_columns["density_dashed"]
    condition_id_column = role_columns["condition_id"]

    if _density_ridgeline3d_semantic_axis(position_column, condition_axis=True) is None:
        issues.append("condition_position_semantic_name_or_unit_missing")
    if _density_ridgeline3d_semantic_axis(x_column, condition_axis=False) is None:
        issues.append("density_x_semantic_name_or_unit_missing")
    solid_unit = _density_ridgeline3d_density_unit(solid_column)
    dashed_unit = _density_ridgeline3d_density_unit(dashed_column)
    if solid_unit is None:
        issues.append("density_solid_semantic_name_or_unit_missing")
    if dashed_unit is None:
        issues.append("density_dashed_semantic_name_or_unit_missing")
    if solid_unit is not None and dashed_unit is not None and solid_unit[0] != dashed_unit[0]:
        issues.append("density_units_mismatch")

    converted: dict[str, pd.Series] = {}
    numeric_invalid = False
    for role in (
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    ):
        column = role_columns[role]
        raw = frame[column]
        blank = _blank_mask(raw)
        numeric = pd.to_numeric(raw.where(~blank, np.nan), errors="coerce").astype(float)
        finite_or_blank = numeric.isna() | np.isfinite(numeric)
        invalid = (~blank & numeric.isna()) | ~finite_or_blank
        if bool(invalid.any()):
            issues.append(f"{role}_contains_non_numeric_or_nonfinite_values")
            numeric_invalid = True
        converted[role] = numeric

    condition_blank = _blank_mask(frame[condition_id_column])
    if bool(condition_blank.any()):
        issues.append("condition_id_contains_empty_values")
    if numeric_invalid or bool(condition_blank.any()):
        return tuple(dict.fromkeys(issues))

    for role in ("condition_position", "density_x", "density_solid", "density_dashed"):
        if bool(converted[role].isna().any()):
            issues.append(f"{role}_contains_missing_values")
    if any(
        bool(converted[role].isna().any())
        for role in ("condition_position", "density_x", "density_solid", "density_dashed")
    ):
        return tuple(dict.fromkeys(issues))

    audited = pd.DataFrame(
        {
            "condition_id": frame[condition_id_column].astype(str).str.strip(),
            "condition_position": converted["condition_position"],
            "density_x": converted["density_x"],
            "density_solid": converted["density_solid"],
            "density_dashed": converted["density_dashed"],
            "focal_x": converted["focal_x"],
        },
        index=frame.index,
    )
    group_order = tuple(dict.fromkeys(audited["condition_id"].tolist()))
    if not 2 <= len(group_order) <= 6:
        issues.append("condition_count_outside_2_to_6")
    if bool((audited[["density_solid", "density_dashed"]] < 0.0).any().any()):
        issues.append("density_contains_negative_values")

    id_to_positions = audited.groupby("condition_id", sort=False)["condition_position"].nunique()
    position_to_ids = audited.groupby("condition_position", sort=False)["condition_id"].nunique()
    positions_are_unique = True
    if bool((id_to_positions != 1).any()):
        issues.append("condition_id_maps_to_multiple_positions")
        positions_are_unique = False
    if bool((position_to_ids != 1).any()):
        issues.append("condition_position_maps_to_multiple_ids")
        positions_are_unique = False

    direction: int | None = None
    first_positions: list[float] = []
    for condition in group_order:
        group = audited.loc[audited["condition_id"] == condition]
        if len(group) < 5:
            issues.append("fewer_than_5_points_per_condition")
        if positions_are_unique:
            first_positions.append(float(group["condition_position"].iloc[0]))

        differences = np.diff(group["density_x"].to_numpy(dtype=float, copy=True))
        increasing = bool(np.all(differences > 0.0))
        decreasing = bool(np.all(differences < 0.0))
        if not (increasing or decreasing):
            issues.append("density_x_not_strictly_monotonic_in_source_order")
        else:
            current_direction = 1 if increasing else -1
            if direction is None:
                direction = current_direction
            elif direction != current_direction:
                issues.append("density_x_direction_mismatch_between_conditions")

        focal_values = group["focal_x"].dropna().to_numpy(dtype=float, copy=True)
        if focal_values.size != 1:
            issues.append("focal_x_must_have_exactly_one_finite_value_per_condition")
        elif not (
            float(group["density_x"].min())
            <= float(focal_values[0])
            <= float(group["density_x"].max())
        ):
            issues.append("focal_x_outside_condition_density_x_range")

    if positions_are_unique and len(first_positions) >= 2:
        if not bool(np.all(np.diff(np.asarray(first_positions, dtype=float)) > 0.0)):
            issues.append("condition_positions_not_strictly_increasing_in_first_appearance_order")

    return tuple(dict.fromkeys(issues))


def _automatic_trajectory3d_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Recognize only explicit long-table evidence for a scientific 3D trajectory."""
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    aliases = {
        "x3d": _TRAJECTORY3D_X_ALIASES,
        "y3d": _TRAJECTORY3D_Y_ALIASES,
        "z3d": _TRAJECTORY3D_Z_ALIASES,
        "series_id": _TRAJECTORY3D_SERIES_ALIASES,
    }
    selected: dict[str, str] = {}
    reasons: list[str] = []
    for role, role_aliases in aliases.items():
        scored = [
            (str(column), _alias_score(str(column), role_aliases))
            for column in frame.columns
            if str(column) not in selected.values()
        ]
        best = max((score for _column, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if len(winners) == 1:
            selected[role] = winners[0]
            if best < 2:
                reasons.append(f"{role}_role_weak")
        elif len(winners) > 1:
            selected[role] = winners[0]
            reasons.append(f"{role}_role_ambiguous")

    remaining_numeric = [
        str(column)
        for column in frame.columns
        if str(column) not in selected.values() and _numeric_compatible(frame[column])
    ]
    for role in ("x3d", "y3d", "z3d"):
        if role not in selected and remaining_numeric:
            selected[role] = remaining_numeric.pop(0)
            reasons.append(f"{role}_role_inferred")
    if "series_id" not in selected:
        remaining = [str(column) for column in frame.columns if str(column) not in selected.values()]
        nonnumeric = [column for column in remaining if not _numeric_compatible(frame[column])]
        if nonnumeric or remaining:
            selected["series_id"] = (nonnumeric or remaining)[0]
            reasons.append("series_id_role_inferred")
    if set(selected) != {"x3d", "y3d", "z3d", "series_id"}:
        raise ScientificWorkflowError(
            "trajectory3d_roles_missing",
            "trajectory3d needs four distinct long-table columns: Zreal, "
            "a real third variable with unit, -Zimag, and Series.",
        )
    if len(set(selected.values())) != 4:
        raise ScientificWorkflowError(
            "trajectory3d_roles_conflict",
            "Zreal, the third variable, -Zimag, and Series must use four different columns.",
        )
    y_column = selected["y3d"]
    if _trajectory3d_semantic_axis(y_column) is None:
        raise ScientificWorkflowError(
            "trajectory3d_third_axis_unit_missing",
            "The third-axis header must state a scientific meaning and unit, "
            "for example 'Condition Position (mm)' or 'Temperature (K)'.",
            column=y_column,
        )
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.98 if not reasons else 0.64
    unique_reasons = tuple(dict.fromkeys(reasons))
    return _AutoMapping(
        assignments,
        "multi_condition_nyquist",
        confidence,
        unique_reasons,
        unique_reasons,
    )


def _automatic_density_ridgeline3d_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Recognize the six-column, precomputed 3D density-focus contract.

    Weak fallbacks only propose a mapping and therefore keep the confirmation
    gate active.  This route never computes a density, threshold, normalization,
    interpolation, or smoothed replacement for a source column.
    """

    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    aliases = {
        "condition_id": _DENSITY3D_CONDITION_ID_ALIASES,
        "condition_position": _DENSITY3D_CONDITION_POSITION_ALIASES,
        "density_solid": _DENSITY3D_SOLID_ALIASES,
        "density_dashed": _DENSITY3D_DASHED_ALIASES,
        "focal_x": _DENSITY3D_FOCAL_X_ALIASES,
        "density_x": _DENSITY3D_X_ALIASES,
    }
    selected: dict[str, str] = {}
    reasons: list[str] = []
    for role, role_aliases in aliases.items():
        scored = [
            (str(column), _alias_score(str(column), role_aliases))
            for column in frame.columns
            if str(column) not in selected.values()
        ]
        best = max((score for _column, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if len(winners) == 1:
            selected[role] = winners[0]
            if best < 2:
                reasons.append(f"{role}_role_weak")
        elif len(winners) > 1:
            selected[role] = winners[0]
            reasons.append(f"{role}_role_ambiguous")

    remaining = [
        str(column) for column in frame.columns if str(column) not in selected.values()
    ]
    if "condition_id" not in selected:
        nonnumeric = [column for column in remaining if not _numeric_compatible(frame[column])]
        if nonnumeric:
            selected["condition_id"] = nonnumeric[0]
            remaining.remove(nonnumeric[0])
            reasons.append("condition_id_role_inferred")

    if "focal_x" not in selected:
        sparse_numeric = []
        for column in remaining:
            if not _numeric_compatible(frame[column]):
                continue
            nonmissing = int(_coerce_numeric(frame[column], column).notna().sum())
            if 1 <= nonmissing <= 6 and nonmissing < len(frame):
                sparse_numeric.append(column)
        if len(sparse_numeric) == 1:
            selected["focal_x"] = sparse_numeric[0]
            remaining.remove(sparse_numeric[0])
            reasons.append("focal_x_role_inferred")

    remaining_numeric = [column for column in remaining if _numeric_compatible(frame[column])]
    for role in (
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    ):
        if role not in selected and remaining_numeric:
            column = remaining_numeric.pop(0)
            selected[role] = column
            reasons.append(f"{role}_role_inferred")

    required = {
        "condition_id",
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    }
    if set(selected) != required or len(set(selected.values())) != len(required):
        raise ScientificWorkflowError(
            "density_ridgeline3d_roles_missing",
            "density_ridgeline3d needs six distinct columns: condition ID, "
            "condition position, density X, solid density, dashed density, and focal X.",
        )
    for role, column in selected.items():
        assignments[column] = role
    if any(role == "ignored" for role in assignments.values()):
        reasons.append("additional_columns_retained_not_rendered")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return _AutoMapping(
        assignments,
        "ordered_dual_profile_focus",
        0.98 if not unique_reasons else 0.62,
        unique_reasons,
        unique_reasons,
    )


def _fit_base_name(column: str) -> str:
    text = unicodedata.normalize("NFKC", column).strip()
    text = re.sub(
        r"(?i)(?:[_\-\s]+|\()?\b(?:fit|fitted|fitting)\b\)?$",
        "",
        text,
    ).strip(" _-(（")
    text = re.sub(r"(?:[_\-\s]+|\()?拟合(?:曲线)?\)?$", "", text).strip(" _-(（")
    return text or column


def _automatic_material_mapping(
    loaded: LoadedTable,
    template_id: str,
) -> _AutoMapping:
    """Map one physical X coordinate and only numeric measured signal columns."""

    frame = loaded.frame
    x_column, confidence, x_reasons = _select_x_column(frame, template_id)
    assignments = {str(column): "ignored" for column in frame.columns}
    assignments[x_column] = "x"
    reasons = list(x_reasons)
    signal_columns: list[str] = []
    ignored_columns: list[str] = []
    metadata_columns: list[str] = []
    uncertain_columns: list[str] = []
    for column in map(str, frame.columns):
        if column == x_column:
            continue
        if not _numeric_compatible(frame[column]):
            ignored_columns.append(column)
            continue
        numeric_role = _material_numeric_role(column, template_id)
        if numeric_role == "signal":
            assignments[column] = "series"
            signal_columns.append(column)
        elif numeric_role == "metadata":
            metadata_columns.append(column)
        else:
            uncertain_columns.append(column)
    if not signal_columns and uncertain_columns:
        for column in uncertain_columns:
            assignments[column] = "series"
        signal_columns.extend(uncertain_columns)
        uncertain_columns.clear()
        reasons.append("material_series_roles_require_confirmation")
    if not signal_columns:
        raise ScientificWorkflowError(
            "series_missing",
            f"{template_id.upper()} data needs at least one numeric signal series.",
        )
    if ignored_columns:
        reasons.append("nonnumeric_columns_ignored")
    if metadata_columns:
        reasons.append("material_numeric_metadata_ignored")
    if uncertain_columns:
        reasons.append("material_numeric_columns_ignored_uncertain")
    unique_reasons = tuple(dict.fromkeys(reasons))
    warnings = unique_reasons
    if len(signal_columns) > 10:
        warnings = tuple(dict.fromkeys((*warnings, "material_series_count_high")))
    return _AutoMapping(
        assignments,
        "overlay",
        min(confidence, 0.68) if unique_reasons else 0.98,
        unique_reasons,
        warnings,
    )


def _automatic_xps_compare_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Select only independent measured XPS spectra, never fit-table columns."""
    frame = loaded.frame
    x_column, confidence, x_reasons = _select_x_column(frame, "xps_compare")
    assignments = {str(column): "ignored" for column in frame.columns}
    assignments[x_column] = "x"
    measured: list[str] = []
    uncertain: list[str] = []
    fit_columns: list[str] = []
    metadata: list[str] = []
    nonnumeric: list[str] = []
    for column in map(str, frame.columns):
        if column == x_column:
            continue
        if not _numeric_compatible(frame[column]):
            nonnumeric.append(column)
            continue
        if _alias_score(column, _XPS_FIT_COLUMN_ALIASES) > 0:
            fit_columns.append(column)
            continue
        numeric_role = _material_numeric_role(column, "xps_compare")
        if numeric_role == "signal":
            assignments[column] = "series"
            measured.append(column)
        elif numeric_role == "metadata":
            metadata.append(column)
        else:
            uncertain.append(column)
    if len(measured) < 2:
        needed = 2 - len(measured)
        promoted = uncertain[:needed] if measured else uncertain
        for column in promoted:
            assignments[column] = "series"
            measured.append(column)
        uncertain = [column for column in uncertain if column not in promoted]
    if len(measured) < 2:
        code = "xps_fit_table_requires_fit_template" if fit_columns else "xps_compare_series_missing"
        raise ScientificWorkflowError(
            code,
            "XPS comparison needs at least two independent measured spectra. "
            "Use the XPS fit template when the remaining columns are background, "
            "envelope, residual, or component peaks.",
        )
    reasons = list(x_reasons)
    if fit_columns:
        reasons.append("xps_fit_columns_ignored_use_fit_template")
    if metadata:
        reasons.append("material_numeric_metadata_ignored")
    if uncertain:
        reasons.append("xps_numeric_columns_ignored_uncertain")
    if nonnumeric:
        reasons.append("nonnumeric_columns_ignored")
    # Any series without a measured-signal alias was promoted only to keep a
    # two-or-more comparison possible and must still be confirmed by the user.
    if any(_material_numeric_role(column, "xps_compare") == "uncertain" for column in measured):
        reasons.append("xps_series_roles_require_confirmation")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return _AutoMapping(
        assignments,
        "overlay",
        min(confidence, 0.62) if unique_reasons else 0.98,
        unique_reasons,
        unique_reasons,
    )


def _automatic_pl_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    x_column, confidence, x_reasons = _select_x_column(frame, "pl")
    assignments: dict[str, str] = {}
    fit_columns: list[str] = []
    ignored: list[str] = []
    metadata_numeric: list[str] = []
    uncertain_numeric: list[str] = []
    for column in map(str, frame.columns):
        if column == x_column:
            assignments[column] = "x"
        elif not _numeric_compatible(frame[column]):
            assignments[column] = "ignored"
            ignored.append(column)
        elif _alias_score(column, _FIT_ALIASES) > 0:
            assignments[column] = "fit"
            fit_columns.append(column)
        elif _material_numeric_role(column, "pl") == "metadata":
            assignments[column] = "ignored"
            metadata_numeric.append(column)
        else:
            assignments[column] = "series"
            if _material_numeric_role(column, "pl") == "uncertain":
                uncertain_numeric.append(column)
    if not any(role == "series" for role in assignments.values()):
        raise ScientificWorkflowError("series_missing", "PL data needs at least one measured signal series.")
    canonical_x = _canonical(x_column)
    time_like = any(token in canonical_x for token in ("time", "decay", "lifetime", "时间", "寿命"))
    wavelength_like = any(token in canonical_x for token in ("wavelength", "波长"))
    mode = "trpl" if time_like else "steady_state"
    reasons = list(x_reasons)
    if not time_like and not wavelength_like and fit_columns:
        mode = "trpl"
        reasons.append("pl_mode_inferred_from_fit")
    if ignored:
        reasons.append("nonnumeric_columns_ignored")
    if metadata_numeric:
        reasons.append("material_numeric_metadata_ignored")
    if uncertain_numeric:
        reasons.append("material_series_roles_require_confirmation")
    if mode == "trpl" and not fit_columns:
        reasons.append("trpl_fit_columns_absent")
    return _AutoMapping(
        assignments,
        mode,
        min(confidence, 0.82) if reasons else 0.98,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_uv_vis_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    x_column, confidence, x_reasons = _select_x_column(frame, "uv_vis")
    assignments = {str(column): "ignored" for column in frame.columns}
    assignments[x_column] = "x"
    selected = {x_column}
    reasons = list(x_reasons)
    role_aliases = (
        ("tauc_fit", _TAUC_FIT_ALIASES),
        ("photon_energy", _PHOTON_ENERGY_ALIASES),
        ("bandgap", _BANDGAP_ALIASES),
        ("tauc", _TAUC_VALUE_ALIASES),
    )
    for role, aliases in role_aliases:
        scored = [
            (str(column), _alias_score(str(column), aliases))
            for column in frame.columns
            if str(column) not in selected
        ]
        best = max((score for _column, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if winners:
            assignments[winners[0]] = role
            selected.add(winners[0])
            if len(winners) > 1:
                reasons.append(f"{role}_role_ambiguous")
    metadata_numeric: list[str] = []
    uncertain_numeric: list[str] = []
    for column in map(str, frame.columns):
        if column in selected:
            continue
        if not _numeric_compatible(frame[column]):
            reasons.append("nonnumeric_columns_ignored")
            continue
        numeric_role = _material_numeric_role(column, "uv_vis")
        if numeric_role == "metadata":
            metadata_numeric.append(column)
        else:
            assignments[column] = "series"
            if numeric_role == "uncertain":
                uncertain_numeric.append(column)
    if metadata_numeric:
        reasons.append("material_numeric_metadata_ignored")
    if uncertain_numeric:
        reasons.append("material_series_roles_require_confirmation")
    if not any(role == "series" for role in assignments.values()):
        raise ScientificWorkflowError(
            "series_missing",
            "UV-Vis data needs at least one absorbance or transmittance signal series.",
        )
    inset_roles = {
        role for role in assignments.values() if role in {"photon_energy", "tauc", "tauc_fit", "bandgap"}
    }
    if inset_roles and not {"photon_energy", "tauc"}.issubset(inset_roles):
        reasons.append("tauc_inset_roles_incomplete")
    return _AutoMapping(
        assignments,
        "uv_vis_with_tauc" if {"photon_energy", "tauc"}.issubset(inset_roles) else "uv_vis",
        min(confidence, 0.76) if reasons else 0.98,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_shap_summary_mapping(loaded: LoadedTable) -> _AutoMapping:
    """Map a long table of externally precomputed SHAP values.

    The workflow intentionally does not calculate SHAP values or train a model.
    It identifies the three required source roles plus optional, explicitly
    named ordering and summary roles.  Any summary derived from supplied rows is
    frozen separately and must pass the semantic approval gate.
    """
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    selected: dict[str, str] = {}
    reasons: list[str] = []

    feature, feature_ambiguous = _select_semantic_column(
        frame,
        _FEATURE_ALIASES,
        excluded=set(),
    )
    # A numeric header such as ``Feature value`` must never be mistaken for
    # the categorical feature-name column merely because it starts with
    # ``Feature``.
    if feature is not None and _numeric_compatible(frame[feature]):
        feature = None
    if feature_ambiguous:
        reasons.append("feature_role_ambiguous")
    if feature is None:
        text_columns = [str(column) for column in frame.columns if not _numeric_compatible(frame[column])]
        if text_columns:
            feature = text_columns[0]
            reasons.append("feature_role_inferred")
    if feature is not None:
        selected["feature"] = feature

    shap, shap_ambiguous = _select_semantic_column(
        frame,
        _SHAP_VALUE_ALIASES,
        excluded=set(selected.values()),
    )
    if shap_ambiguous:
        reasons.append("shap_role_ambiguous")
    if shap is None:
        numeric = [
            str(column)
            for column in frame.columns
            if str(column) not in selected.values() and _numeric_compatible(frame[column])
        ]
        if numeric:
            shap = numeric[0]
            reasons.append("shap_role_inferred")
    if shap is not None:
        selected["shap"] = shap

    feature_value, value_ambiguous = _select_semantic_column(
        frame,
        _FEATURE_VALUE_ALIASES,
        excluded=set(selected.values()),
    )
    if value_ambiguous:
        reasons.append("feature_value_role_ambiguous")
    if feature_value is None:
        numeric = [
            str(column)
            for column in frame.columns
            if str(column) not in selected.values() and _numeric_compatible(frame[column])
        ]
        if numeric:
            feature_value = numeric[0]
            reasons.append("feature_value_role_inferred")
    if feature_value is not None:
        selected["feature_value"] = feature_value

    missing = [role for role in ("feature", "shap", "feature_value") if role not in selected]
    if missing:
        raise ScientificWorkflowError(
            "shap_roles_missing",
            "SHAP summary data needs Feature, precomputed SHAP value, and numeric Feature value "
            f"columns; missing roles: {', '.join(missing)}.",
        )
    if len(set(selected.values())) != 3:
        raise ScientificWorkflowError(
            "shap_roles_conflict",
            "Feature, SHAP value, and Feature value must use different source columns.",
        )

    optional_roles = (
        ("sample_id", _SAMPLE_ID_ALIASES),
        ("feature_order", _FEATURE_ORDER_ALIASES),
        ("mean_abs_shap", _MEAN_ABS_SHAP_ALIASES),
        ("feature_group", _FEATURE_GROUP_ALIASES),
        ("group_contribution", _GROUP_CONTRIBUTION_ALIASES),
    )
    for role, aliases in optional_roles:
        column, ambiguous = _select_semantic_column(
            frame,
            aliases,
            excluded=set(selected.values()),
        )
        if ambiguous:
            reasons.append(f"{role}_role_ambiguous")
        if column is not None:
            selected[role] = column
            if role == "feature_group" and _canonical(column) == "domain":
                reasons.append("generic_domain_role_requires_confirmation")
    if "group_contribution" in selected and "feature_group" not in selected:
        reasons.append("group_contribution_requires_feature_group")
    derivation_warnings: list[str] = []
    if "mean_abs_shap" not in selected:
        derivation_warnings.append("mean_abs_shap_derivation_requires_confirmation")
    if "feature_group" in selected and "group_contribution" not in selected:
        derivation_warnings.append("group_contribution_derivation_requires_confirmation")

    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.98 if not reasons else 0.68
    unique_reasons = tuple(dict.fromkeys(reasons))
    unique_warnings = tuple(dict.fromkeys((*reasons, *derivation_warnings)))
    profile = (
        "beeswarm_mean_abs_grouped"
        if "feature_group" in selected
        else "beeswarm_mean_abs"
    )
    return _AutoMapping(
        assignments,
        profile,
        confidence,
        unique_reasons,
        unique_warnings,
    )


def _select_semantic_column(
    frame: pd.DataFrame,
    aliases: tuple[str, ...],
    *,
    excluded: set[str],
) -> tuple[str | None, bool]:
    scored = [
        (str(column), _alias_score(str(column), aliases))
        for column in frame.columns
        if str(column) not in excluded
    ]
    best = max((score for _, score in scored), default=0)
    winners = [column for column, score in scored if score == best and score > 0]
    return (winners[0] if winners else None, len(winners) > 1)


def _automatic_bubble_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    selected: dict[str, str] = {}
    reasons: list[str] = []
    x_column, x_confidence, x_reasons = _select_x_column(frame, "bubble")
    selected["x"] = x_column
    reasons.extend(x_reasons)
    size_column, size_ambiguous = _select_semantic_column(
        frame,
        _SIZE_ALIASES,
        excluded={x_column},
    )
    if size_ambiguous:
        reasons.append("size_role_ambiguous")
    numeric = [
        str(column)
        for column in frame.columns
        if str(column) != x_column and _numeric_compatible(frame[column])
    ]
    if size_column is None and numeric:
        size_column = numeric[-1]
        reasons.append("size_role_inferred")
    if size_column is None:
        raise ScientificWorkflowError(
            "size_missing",
            "Bubble data needs one numeric size column.",
        )
    selected["size"] = size_column
    responses = [column for column in numeric if column != size_column]
    if len(responses) != 1:
        if not responses:
            raise ScientificWorkflowError(
                "bubble_response_missing",
                "Bubble data needs one numeric response column in addition to X and Size.",
            )
        reasons.append("bubble_response_ambiguous")
    selected["series"] = responses[0]
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.97 if not reasons else min(0.72, x_confidence)
    return _AutoMapping(
        assignments,
        "indexed_size",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_forest_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    selected: dict[str, str] = {}
    reasons: list[str] = []
    role_aliases = {
        "category": _CATEGORY_ALIASES,
        "estimate": _ESTIMATE_ALIASES,
        "lower": _LOWER_ALIASES,
        "upper": _UPPER_ALIASES,
        "reference": _REFERENCE_ALIASES,
    }
    for role, aliases in role_aliases.items():
        column, ambiguous = _select_semantic_column(
            frame,
            aliases,
            excluded=set(selected.values()),
        )
        if column is not None:
            selected[role] = column
        if ambiguous:
            reasons.append(f"{role}_role_ambiguous")
    if "category" not in selected:
        text_columns = [str(column) for column in frame.columns if not _numeric_compatible(frame[column])]
        if text_columns:
            selected["category"] = text_columns[0]
            reasons.append("category_role_inferred")
    missing = [role for role in ("category", "estimate", "lower", "upper") if role not in selected]
    if missing:
        raise ScientificWorkflowError(
            "forest_roles_missing",
            "Forest data needs Label, Estimate, CI Low, and CI High columns.",
        )
    if len(set(selected.values())) != len(selected):
        raise ScientificWorkflowError(
            "forest_roles_conflict",
            "Forest roles must use different source columns.",
        )
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.98 if not reasons else 0.70
    return _AutoMapping(
        assignments,
        "interval",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_diagnostic_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    x_column, confidence, reasons_tuple = _select_x_column(frame, "diagnostic_curve")
    reasons = list(reasons_tuple)
    canonical_x = _canonical(x_column)
    if any(token in canonical_x for token in ("fpr", "falsepositiverate", "假阳性率")):
        mode = "roc"
    elif any(token in canonical_x for token in ("recall", "sensitivity", "召回率", "敏感度")):
        mode = "pr"
    else:
        mode = "roc"
        reasons.append("diagnostic_mode_ambiguous")
        confidence = min(confidence, 0.65)
    assignments[x_column] = "x"
    reference_column, reference_ambiguous = _select_semantic_column(
        frame,
        _PREVALENCE_ALIASES,
        excluded={x_column},
    )
    if reference_ambiguous:
        reasons.append("reference_role_ambiguous")
    if mode == "pr" and reference_column is not None:
        assignments[reference_column] = "reference"
    numeric_series: list[str] = []
    for column in map(str, frame.columns):
        if column == x_column or assignments[column] == "reference":
            continue
        if _numeric_compatible(frame[column]):
            assignments[column] = "series"
            numeric_series.append(column)
    if not numeric_series:
        raise ScientificWorkflowError(
            "diagnostic_series_missing",
            "Diagnostic curves need at least one numeric TPR or Precision series.",
        )
    if mode == "pr" and reference_column is None:
        reasons.append("prevalence_missing")
        confidence = min(confidence, 0.64)
    return _AutoMapping(
        assignments,
        mode,
        confidence if not reasons else min(confidence, 0.72),
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_calibration_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    x_column, confidence, reasons_tuple = _select_x_column(frame, "calibration_curve")
    reasons = list(reasons_tuple)
    assignments[x_column] = "x"
    observed_column, observed_ambiguous = _select_semantic_column(
        frame,
        _OBSERVED_FRACTION_ALIASES,
        excluded={x_column},
    )
    count_column, count_ambiguous = _select_semantic_column(
        frame,
        _COUNT_ALIASES,
        excluded={x_column, observed_column} if observed_column else {x_column},
    )
    if observed_ambiguous:
        reasons.append("observed_fraction_role_ambiguous")
    if count_ambiguous:
        reasons.append("count_role_ambiguous")
    if observed_column is None or count_column is None:
        missing = []
        if observed_column is None:
            missing.append("Observed fraction")
        if count_column is None:
            missing.append("Bin count")
        raise ScientificWorkflowError(
            "calibration_roles_missing",
            "Calibration V1 needs Predicted probability, Observed fraction, and Bin count; "
            f"missing roles: {', '.join(missing)}.",
        )
    assignments[observed_column] = "series"
    assignments[count_column] = "count"
    confidence = confidence if not reasons else min(confidence, 0.70)
    return _AutoMapping(
        assignments,
        "precomputed_bins",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_decision_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    x_column, confidence, reasons_tuple = _select_x_column(frame, "decision_curve")
    reasons = list(reasons_tuple)
    assignments[x_column] = "x"
    treat_all, all_ambiguous = _select_semantic_column(
        frame,
        _TREAT_ALL_ALIASES,
        excluded={x_column},
    )
    treat_none, none_ambiguous = _select_semantic_column(
        frame,
        _TREAT_NONE_ALIASES,
        excluded={x_column, treat_all} if treat_all else {x_column},
    )
    if all_ambiguous:
        reasons.append("treat_all_role_ambiguous")
    if none_ambiguous:
        reasons.append("treat_none_role_ambiguous")
    if treat_all is None or treat_none is None:
        missing = []
        if treat_all is None:
            missing.append("Treat all")
        if treat_none is None:
            missing.append("Treat none")
        raise ScientificWorkflowError(
            "decision_reference_missing",
            "Decision-curve V1 needs explicit Treat all and Treat none net-benefit columns; "
            f"missing roles: {', '.join(missing)}.",
        )
    assignments[treat_all] = "treat_all"
    assignments[treat_none] = "treat_none"
    model_columns: list[str] = []
    for column in map(str, frame.columns):
        if assignments[column] != "ignored":
            continue
        if _numeric_compatible(frame[column]):
            assignments[column] = "series"
            model_columns.append(column)
    if not model_columns:
        raise ScientificWorkflowError(
            "decision_model_missing",
            "Decision-curve input needs at least one model net-benefit series.",
        )
    confidence = confidence if not reasons else min(confidence, 0.70)
    return _AutoMapping(
        assignments,
        "precomputed_net_benefit",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _automatic_bland_altman_mapping(loaded: LoadedTable) -> _AutoMapping:
    frame = loaded.frame
    assignments = {str(column): "ignored" for column in frame.columns}
    aliases = {
        "mean": _MEAN_ALIASES,
        "difference": _DIFFERENCE_ALIASES,
        "bias": _BIAS_ALIASES,
        "loa_lower": _LOA_LOWER_ALIASES,
        "loa_upper": _LOA_UPPER_ALIASES,
    }
    selected: dict[str, str] = {}
    reasons: list[str] = []
    for role, role_aliases in aliases.items():
        column, ambiguous = _select_semantic_column(
            frame,
            role_aliases,
            excluded=set(selected.values()),
        )
        if ambiguous:
            reasons.append(f"{role}_role_ambiguous")
        if column is not None:
            selected[role] = column
    if set(selected) != set(aliases):
        missing = sorted(set(aliases) - set(selected))
        raise ScientificWorkflowError(
            "bland_altman_roles_missing",
            "Bland-Altman V1 needs Mean, Difference, Bias, Lower LoA, and Upper LoA columns; "
            f"missing roles: {', '.join(missing)}.",
        )
    for role, column in selected.items():
        assignments[column] = role
    confidence = 0.98 if not reasons else 0.68
    return _AutoMapping(
        assignments,
        "precomputed_limits",
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(reasons)),
    )


def _eis_role_score(column: str, role: str) -> int:
    value = _canonical(column)
    raw = unicodedata.normalize("NFKC", column).casefold().replace(" ", "")
    if role == "z_imag":
        if any(token in value for token in ("zimag", "zim", "imaginary", "虚部")):
            return 3
        if "z''" in raw or "im(z)" in raw or "-im" in raw:
            return 3
    elif role == "z_real":
        if any(token in value for token in ("zreal", "zre", "realz", "实部")):
            return 3
        if "z''" not in raw and ("z'" in raw or "re(z)" in raw):
            return 3
    elif role == "frequency":
        return _alias_score(column, ("frequency", "freq", "频率", "hz"))
    elif role == "magnitude":
        if "|z|" in raw:
            return 3
        return _alias_score(column, ("zmod", "modulus", "magnitude", "impedance", "阻抗模"))
    elif role == "phase":
        return _alias_score(column, ("phaseangle", "phase", "相位角", "相位"))
    return 0


def _automatic_eis_mapping(loaded: LoadedTable) -> _AutoMapping:
    assignments = {str(column): "ignored" for column in loaded.frame.columns}
    found: dict[str, str] = {}
    ambiguous = False
    for role in ("z_real", "z_imag", "frequency", "magnitude", "phase"):
        scored = [(str(column), _eis_role_score(str(column), role)) for column in loaded.frame.columns]
        best = max((score for _, score in scored), default=0)
        winners = [column for column, score in scored if score == best and score > 0]
        if len(winners) == 1:
            found[role] = winners[0]
        elif len(winners) > 1:
            found[role] = winners[0]
            ambiguous = True
    for role, column in found.items():
        if assignments[column] != "ignored":
            ambiguous = True
        assignments[column] = role

    nyquist = "z_real" in found and "z_imag" in found
    bode = "frequency" in found and ("magnitude" in found or "phase" in found)
    reasons: list[str] = []
    warnings: list[str] = []
    if nyquist and bode:
        mode = "nyquist"
        reasons.append("plot_mode_ambiguous")
    elif nyquist:
        mode = "nyquist"
    elif bode:
        mode = "bode"
    else:
        numeric = [
            str(column) for column in loaded.frame.columns if _numeric_compatible(loaded.frame[column])
        ]
        if len(numeric) < 2:
            raise ScientificWorkflowError(
                "eis_roles_missing",
                "EIS needs Z real/Z imaginary columns or frequency with magnitude/phase.",
            )
        assignments = {str(column): "ignored" for column in loaded.frame.columns}
        assignments[numeric[0]] = "z_real"
        assignments[numeric[1]] = "z_imag"
        mode = "nyquist"
        reasons.append("eis_roles_inferred")
    if ambiguous:
        reasons.append("eis_role_ambiguous")
    ignored_numeric = [
        column
        for column, role in assignments.items()
        if role == "ignored" and _numeric_compatible(loaded.frame[column])
    ]
    if ignored_numeric and not (nyquist and bode):
        warnings.append("additional_numeric_columns_ignored")
    confidence = 0.97 if not reasons else 0.68
    warnings.extend(reasons)
    return _AutoMapping(
        assignments,
        mode,
        confidence,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(warnings)),
    )


def _validate_assignment_shape(
    loaded: LoadedTable,
    template_id: str,
    mapping: ScientificColumnMapping,
) -> tuple[dict[str, str], str]:
    assignments = dict(mapping.assignments)
    if len(assignments) != len(mapping.assignments):
        raise ScientificWorkflowError("mapping_duplicate_column", "A source column is mapped more than once.")
    if set(assignments) != set(loaded.columns):
        raise ScientificWorkflowError(
            "mapping_incomplete", "Every source column must be assigned a role or ignored."
        )
    options = {key for key, _label, _unique in role_options(template_id)}
    invalid = next((role for role in assignments.values() if role not in options), None)
    if invalid is not None:
        raise ScientificWorkflowError("mapping_unknown_role", f"Unknown mapping role: {invalid}")
    for role in {key for key, _label, unique in role_options(template_id) if unique}:
        columns = [column for column, assigned in assignments.items() if assigned == role]
        if len(columns) > 1:
            raise ScientificWorkflowError(
                f"mapping_{role}_conflict", f"Only one column can be assigned to {role}."
            )
    if template_id == "xrd":
        inferred_xrd_mode = (
            "rietveld_refinement"
            if {"observed", "calculated"}.issubset(assignments.values())
            else "ordinary_scan"
        )
        mode = mapping.plot_mode or inferred_xrd_mode
    elif template_id in {"dsc", "nmr", "ftir", "xps_compare"}:
        mode = mapping.plot_mode or "overlay"
    elif template_id == "shap_summary":
        mode = mapping.plot_mode or (
            "beeswarm_mean_abs_grouped"
            if "feature_group" in assignments.values()
            else "beeswarm_mean_abs"
        )
        if mode == "precomputed_long":
            mode = "beeswarm_only"
    else:
        mode = mapping.plot_mode or ("nyquist" if template_id == "eis" else "default")
    if template_id == "xrd" and mode not in {"ordinary_scan", "rietveld_refinement"}:
        raise ScientificWorkflowError(
            "mapping_plot_mode",
            "Select ordinary XRD or Rietveld refinement mode.",
        )
    if (
        template_id == "xrd"
        and loaded.source_profile
        in {
            "gsas_ii_powder_csv",
            GSAS_II_PUBLICATION_CSV,
        }
        and mode != "rietveld_refinement"
    ):
        raise ScientificWorkflowError(
            "xrd_source_profile_mode_conflict",
            "Documented GSAS-II exports must keep the Rietveld refinement mode.",
        )
    if template_id == "eis" and mode not in {"nyquist", "bode"}:
        raise ScientificWorkflowError("mapping_plot_mode", "Select Nyquist or Bode for EIS.")
    if template_id == "diagnostic_curve" and mode not in {"roc", "pr"}:
        raise ScientificWorkflowError("mapping_plot_mode", "Select ROC or Precision-Recall mode.")
    if template_id == "pl" and mode not in {"steady_state", "trpl"}:
        raise ScientificWorkflowError("mapping_plot_mode", "Select steady-state PL or TRPL mode.")
    if template_id == "shap_summary" and mode not in SHAP_COMPOSITE_PROFILES:
        raise ScientificWorkflowError(
            "mapping_plot_mode",
            "Select SHAP beeswarm only, beeswarm with Mean |SHAP|, or the grouped composite profile.",
        )
    if template_id in {"dsc", "nmr", "ftir", "xps_compare"} and mode not in {
        "overlay",
        "stacked_offset",
    }:
        raise ScientificWorkflowError("mapping_plot_mode", "Select overlay or stacked-offset mode.")
    return assignments, mode


def _require_one(assignments: dict[str, str], role: str) -> str:
    matches = [column for column, assigned in assignments.items() if assigned == role]
    if len(matches) != 1:
        raise ScientificWorkflowError(f"{role}_missing", f"Exactly one column must be assigned to {role}.")
    return matches[0]


def _require_series(assignments: dict[str, str]) -> list[str]:
    series = [column for column, role in assignments.items() if role == "series"]
    if not series:
        raise ScientificWorkflowError("series_missing", "At least one data series is required.")
    return series


def _pair_errors(series_columns: list[str], error_columns: list[str]) -> dict[str, tuple[str, str]]:
    available = list(error_columns)
    pairs: dict[str, tuple[str, str]] = {}
    for series in series_columns:
        exact = [
            error
            for error in available
            if _error_info(error) is not None and _canonical(_error_info(error)[0]) == _canonical(series)  # type: ignore[index]
        ]
        if len(exact) == 1:
            error = exact[0]
            info = _error_info(error)
            if info is None:
                continue
            pairs[series] = (error, info[1])
            available.remove(error)
    for series in series_columns:
        if series in pairs or not available:
            continue
        error = available.pop(0)
        info = _error_info(error)
        pairs[series] = (error, info[1] if info else "custom")
    if available:
        raise ScientificWorkflowError(
            "error_pair_ambiguous", "Some error columns could not be paired to a data series."
        )
    return pairs


def _coerced_selected_frame(
    loaded: LoadedTable,
    assignments: dict[str, str],
) -> pd.DataFrame:
    frame = loaded.copy_frame()
    numeric_roles = {
        "x",
        "series",
        "observed",
        "calculated",
        "background",
        "phase_tick",
        "error",
        "z_real",
        "z_imag",
        "frequency",
        "magnitude",
        "phase",
        "value",
        "size",
        "estimate",
        "lower",
        "upper",
        "reference",
        "mean",
        "difference",
        "bias",
        "loa_lower",
        "loa_upper",
        "count",
        "treat_all",
        "treat_none",
        "shap",
        "feature_value",
        "feature_order",
        "mean_abs_shap",
        "group_contribution",
        "fit",
        "photon_energy",
        "tauc",
        "tauc_fit",
        "bandgap",
        "x3d",
        "y3d",
        "z3d",
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    }
    for column, role in assignments.items():
        if role in numeric_roles:
            frame[column] = _coerce_numeric(frame[column], column)
    return frame


def _require_points(
    frame: pd.DataFrame,
    x_column: str | None,
    series_columns: list[str],
    *,
    category_column: str | None = None,
) -> None:
    if category_column is not None:
        category = frame[category_column]
        blank = _blank_mask(category)
        if bool(blank.any()):
            index = int(np.flatnonzero(blank.to_numpy())[0])
            raise ScientificWorkflowError(
                "empty_category",
                f"Category column {category_column!r} is empty at data row {index + 2}.",
                column=category_column,
                row=index + 2,
            )
    for column in series_columns:
        valid = frame[column].notna()
        if x_column is not None:
            valid &= frame[x_column].notna()
        minimum = 1 if category_column is not None else 2
        if int(valid.sum()) < minimum:
            raise ScientificWorkflowError(
                "series_too_short",
                f"Series {column!r} needs at least {minimum} valid plotted values.",
                column=column,
            )


def _nice_number(value: float, *, round_value: bool) -> float:
    if not math.isfinite(value) or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / 10**exponent
    if round_value:
        nice_fraction = 1.0 if fraction < 1.5 else 2.0 if fraction < 3.0 else 5.0 if fraction < 7.0 else 10.0
    else:
        nice_fraction = (
            1.0 if fraction <= 1.0 else 2.0 if fraction <= 2.0 else 5.0 if fraction <= 5.0 else 10.0
        )
    return nice_fraction * 10**exponent


def _nice_axis(
    values: np.ndarray,
    *,
    include_zero: bool = False,
    padding_fraction: float = 0.05,
) -> tuple[float, float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ScientificWorkflowError("no_finite_values", "No finite values are available for an axis.")
    lower = float(np.min(finite))
    upper = float(np.max(finite))
    source_lower = lower
    source_upper = upper
    if math.isclose(lower, upper):
        pad = max(abs(lower) * 0.08, 1.0)
    else:
        pad = (upper - lower) * padding_fraction
    lower -= pad
    upper += pad
    if include_zero and source_lower >= 0:
        lower = 0.0
    elif include_zero and source_upper <= 0:
        upper = 0.0
    elif include_zero:
        lower = min(0.0, lower)
        upper = max(0.0, upper)
    step = _nice_number((upper - lower) / 5.0, round_value=True)
    return lower, upper, step


def _histogram_bin_geometry(values: np.ndarray) -> tuple[float, float, float]:
    """Freeze robust equal-width bins shared by preview and Origin."""
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        raise ScientificWorkflowError(
            "raw_series_too_short",
            "Histogram data needs at least two finite observations.",
        )
    lower = float(np.min(finite))
    upper = float(np.max(finite))
    span = upper - lower
    q25, q75 = np.quantile(finite, (0.25, 0.75))
    iqr = float(q75 - q25)
    if iqr > 0.0:
        raw_width = 2.0 * iqr * finite.size ** (-1.0 / 3.0)
    elif span > 0.0:
        raw_width = span / max(1.0, math.ceil(math.log2(finite.size) + 1.0))
    else:
        raw_width = max(abs(lower) * 0.10, 1.0)
    size = _nice_number(raw_width, round_value=True)
    if not math.isfinite(size) or size <= 0.0:
        size = max(span, 1.0)
    begin = math.floor(lower / size) * size
    end = math.ceil(upper / size) * size
    # Origin bins are lower-inclusive and upper-exclusive.
    if math.isclose(upper, end, rel_tol=0.0, abs_tol=max(1e-12, size * 1e-10)):
        end += size
    if end <= begin:
        end = begin + size
    return round(begin, 12), round(end, 12), round(size, 12)


def log_decade_increment(values: object) -> float:
    """Return a label-safe decade step for a fixed 24 pt log axis."""
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array) & (array > 0)]
    if finite.size < 2:
        return 1.0
    span = math.log10(float(np.max(finite))) - math.log10(float(np.min(finite)))
    return 2.0 if span >= 5.0 else 1.0


def _axis_plan(
    frame: pd.DataFrame,
    *,
    x_column: str | None,
    series: tuple[ScientificSeries, ...],
    category: bool,
    include_zero_y: bool,
    include_zero_x: bool = False,
    padding_fraction: float = 0.05,
) -> ScientificAxisPlan:
    if x_column is None or category:
        x_values = None
        x_axis = (None, None, None)
    else:
        x_values = frame[x_column].to_numpy(dtype=float)
        x_axis = _nice_axis(
            x_values,
            include_zero=include_zero_x,
            padding_fraction=padding_fraction,
        )

    def display_arrays(item: ScientificSeries) -> list[np.ndarray]:
        values = series_values(frame, item)
        arrays = [values]
        if item.error_column is not None:
            errors = frame[item.error_column].to_numpy(dtype=float, copy=True)
            arrays.extend((values - errors, values + errors))
        return arrays

    left_arrays = [array for item in series if item.axis == "left" for array in display_arrays(item)]
    right_arrays = [array for item in series if item.axis == "right" for array in display_arrays(item)]
    if not left_arrays:
        raise ScientificWorkflowError("series_missing", "No series is assigned to the left Y axis.")
    left = np.concatenate(left_arrays)
    y_axis = _nice_axis(
        left,
        include_zero=include_zero_y,
        padding_fraction=padding_fraction,
    )
    if right_arrays:
        right = np.concatenate(right_arrays)
        y2_axis: tuple[float | None, float | None, float | None] = _nice_axis(
            right,
            padding_fraction=padding_fraction,
        )
    else:
        y2_axis = (None, None, None)
    return ScientificAxisPlan(*x_axis, *y_axis, *y2_axis)


def _eis_imag_transform(frame: pd.DataFrame, column: str) -> tuple[SeriesTransform, tuple[str, ...]]:
    raw = unicodedata.normalize("NFKC", column).casefold().replace(" ", "").replace("−", "-")
    explicit_negative = raw.startswith("-") or "-im" in raw or "负虚部" in raw
    values = frame[column].dropna().to_numpy(dtype=float)
    median = float(np.median(values)) if values.size else 0.0
    if explicit_negative and median < 0:
        raise ScientificWorkflowError(
            "eis_sign_conflict",
            "The imaginary column is labelled as negative imaginary impedance "
            "but contains mostly negative values.",
            column=column,
        )
    if explicit_negative:
        return "identity", ()
    if median < 0:
        return "negate", ()
    return "identity", ("eis_imaginary_sign_inferred",)


def _build_line_spec(
    template_id: str,
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    series_columns = _require_series(assignments)
    _require_points(frame, x_column, series_columns)
    series = tuple(ScientificSeries(column, column) for column in series_columns)
    plot_kind = (
        "scatter"
        if template_id == "scatter"
        else "paired_trajectory"
        if template_id == "paired_trajectory"
        else "line"
    )
    display_transform = "identity"
    warnings: list[str] = []
    if template_id == "xrd" and len(series) > 1:
        plot_kind = "stacked_line"
        display_transform = "normalize_max_and_offset"
        warnings.append("display_normalized_and_offset")
    marker_size = 7.0
    if template_id == "scatter":
        if len(frame) > 500:
            marker_size = 4.2
            warnings.append("scatter_density_high")
        elif len(frame) > 100:
            marker_size = 5.5
            warnings.append("scatter_density_medium")
    if len(series) > 12:
        warnings.append("series_count_excessive")
    elif len(series) > 8:
        warnings.append("series_count_high")
    x_title, y_title = _standard_line_axis_titles(
        template_id,
        x_column,
        series_columns,
    )
    if template_id == "paired_trajectory":
        y_title = "Value"
        if len(series) > 30:
            warnings.append("paired_subject_count_excessive")
        elif len(series) > 15:
            warnings.append("paired_subject_count_high")
    style = resolve_adaptive_style(
        template_id=template_id,
        plot_kind=plot_kind,
        row_count=len(frame),
        series_count=len(series),
    )
    axis_plan = _axis_plan(
        frame,
        x_column=x_column,
        series=series,
        category=False,
        include_zero_y=False,
    )
    if template_id == "paired_trajectory":
        finite_x = np.sort(frame[x_column].dropna().unique().astype(float))
        if (
            finite_x.size >= 2
            and np.allclose(finite_x, np.round(finite_x), rtol=0.0, atol=1e-10)
            and np.allclose(np.diff(finite_x), 1.0, rtol=0.0, atol=1e-10)
        ):
            axis_plan = ScientificAxisPlan(
                axis_plan.x_from,
                axis_plan.x_to,
                1.0,
                axis_plan.y_from,
                axis_plan.y_to,
                axis_plan.y_step,
            )
    spec = ScientificPlotSpec(
        plot_kind=plot_kind,
        plot_mode="default",
        x_column=x_column,
        category_column=None,
        series=series,
        x_title=x_title,
        y_title=y_title,
        y2_title=None,
        x_scale="linear",
        y_scale="linear",
        display_transform=display_transform,
        display_plan=ScientificDisplayPlan(marker_size, 0.8, 0.72, figure_style=style),
        axis_plan=axis_plan,
    )
    return spec, tuple(warnings)


def _build_xrd_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
    source_profile: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    """Freeze ordinary or Rietveld XRD without deriving scientific values."""

    if plot_mode == "ordinary_scan":
        refinement_roles = {
            "observed",
            "calculated",
            "background",
            "difference",
            "phase_tick",
        }
        if any(role in refinement_roles for role in assignments.values()):
            raise ScientificWorkflowError(
                "xrd_role_mode_conflict",
                "Rietveld roles require the Rietveld refinement plotting mode.",
            )
        ordinary_spec, warnings = _build_line_spec("xrd", frame, assignments)
        return (
            replace(
                ordinary_spec,
                plot_mode="ordinary_scan",
                source_profile=source_profile,
            ),
            warnings,
        )

    if plot_mode != "rietveld_refinement":
        raise ScientificWorkflowError(
            "mapping_plot_mode",
            "Select ordinary XRD or Rietveld refinement mode.",
        )
    if any(role == "series" for role in assignments.values()):
        raise ScientificWorkflowError(
            "xrd_role_mode_conflict",
            "Assign refinement curves as Observed, Calculated, Background, or Difference.",
        )

    x_column = _require_one(assignments, "x")
    observed_column = _require_one(assignments, "observed")
    calculated_column = _require_one(assignments, "calculated")

    def optional_role(role: str) -> str | None:
        columns = [column for column, assigned in assignments.items() if assigned == role]
        if len(columns) > 1:
            raise ScientificWorkflowError(
                f"mapping_{role}_conflict",
                f"Only one column can be assigned to {role}.",
            )
        return columns[0] if columns else None

    background_column = optional_role("background")
    difference_column = optional_role("difference")
    if source_profile == GSAS_II_PUBLICATION_CSV and difference_column is None:
        raise ScientificWorkflowError(
            "xrd_publication_difference_missing",
            "GSAS-II Publication CSV requires its supplied Diff column.",
        )

    series_items = [
        ScientificSeries(
            observed_column,
            "Observed",
            series_role="observed",
        ),
        ScientificSeries(
            calculated_column,
            "Calculated",
            series_role="calculated",
        ),
    ]
    if background_column is not None:
        series_items.append(
            ScientificSeries(
                background_column,
                "Background",
                series_role="background",
            )
        )
    if difference_column is not None:
        series_items.append(
            ScientificSeries(
                difference_column,
                "Difference",
                transform="identity",
                series_role="difference",
            )
        )
    series = tuple(series_items)
    _require_points(
        frame,
        x_column,
        [item.source_column for item in series],
    )

    phase_tick_columns = tuple(column for column, role in assignments.items() if role == "phase_tick")
    for column in phase_tick_columns:
        if int(frame[column].notna().sum()) < 1:
            raise ScientificWorkflowError(
                "xrd_phase_tick_empty",
                f"Phase tick column {column!r} has no supplied positions.",
                column=column,
            )

    style = resolve_adaptive_style(
        template_id="xrd",
        plot_kind="rietveld_refinement",
        row_count=len(frame),
        series_count=len(series),
    )
    return (
        ScientificPlotSpec(
            plot_kind="rietveld_refinement",
            plot_mode="rietveld_refinement",
            x_column=x_column,
            category_column=None,
            series=series,
            x_title=_standard_line_axis_titles(
                "xrd",
                x_column,
                [observed_column],
            )[0],
            y_title="Intensity (a.u.)",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                5.2,
                0.8,
                0.72,
                figure_style=style,
            ),
            axis_plan=_axis_plan(
                frame,
                x_column=x_column,
                series=series,
                category=False,
                include_zero_y=False,
            ),
            phase_tick_columns=phase_tick_columns,
            source_profile=source_profile,
        ),
        (),
    )


def _build_trajectory3d_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    """Freeze a real XYZ/Series long table without deriving scientific values."""
    x_column = _require_one(assignments, "x3d")
    y_column = _require_one(assignments, "y3d")
    z_column = _require_one(assignments, "z3d")
    series_column = _require_one(assignments, "series_id")
    if _alias_score(x_column, _TRAJECTORY3D_X_ALIASES) == 0:
        raise ScientificWorkflowError(
            "trajectory3d_x_semantics_missing",
            "The X column must explicitly identify Zreal/real impedance.",
            column=x_column,
        )
    if _alias_score(z_column, _TRAJECTORY3D_Z_ALIASES) == 0:
        raise ScientificWorkflowError(
            "trajectory3d_z_semantics_missing",
            "The Z column must explicitly identify supplied -Zimag/negative imaginary impedance.",
            column=z_column,
        )
    if _trajectory3d_semantic_axis(y_column) is None:
        raise ScientificWorkflowError(
            "trajectory3d_third_axis_unit_missing",
            "The third-axis header must state a scientific meaning and unit.",
            column=y_column,
        )

    blank_series = _blank_mask(frame[series_column])
    if bool(blank_series.any()):
        index = int(np.flatnonzero(blank_series.to_numpy())[0])
        raise ScientificWorkflowError(
            "trajectory3d_series_empty",
            f"Series is empty at data row {index + 2}.",
            column=series_column,
            row=index + 2,
        )
    labels = frame[series_column].astype(str).str.strip()
    group_order = tuple(dict.fromkeys(labels.tolist()))
    if len(group_order) > 6:
        raise ScientificWorkflowError(
            "trajectory3d_series_limit",
            "trajectory3d supports 1–6 Series groups; split a denser dataset into separate figures.",
            column=series_column,
        )
    for column in (x_column, y_column, z_column):
        missing = frame[column].isna()
        if bool(missing.any()):
            index = int(np.flatnonzero(missing.to_numpy())[0])
            raise ScientificWorkflowError(
                "trajectory3d_coordinate_missing",
                f"Column {column!r} has a missing coordinate at data row {index + 2}.",
                column=column,
                row=index + 2,
            )
    series: list[ScientificSeries] = []
    for label in group_order:
        count = int((labels == label).sum())
        if count < 2:
            raise ScientificWorkflowError(
                "trajectory3d_series_too_short",
                f"Series {label!r} needs at least two complete XYZ points.",
                column=series_column,
            )
        series.append(
            ScientificSeries(
                source_column=z_column,
                label=label,
                group=label,
                series_role="trajectory3d",
            )
        )

    x_axis = _nice_axis(
        frame[x_column].to_numpy(dtype=float),
        include_zero=True,
        padding_fraction=0.04,
    )
    y_axis = _nice_axis(
        frame[y_column].to_numpy(dtype=float),
        include_zero=False,
        padding_fraction=0.08,
    )
    z_axis = _nice_axis(
        frame[z_column].to_numpy(dtype=float),
        include_zero=True,
        padding_fraction=0.04,
    )
    style = resolve_adaptive_style(
        template_id="trajectory3d",
        plot_kind="trajectory3d",
        row_count=len(frame),
        series_count=len(series),
    )
    return (
        ScientificPlotSpec(
            plot_kind="trajectory3d",
            plot_mode="multi_condition_nyquist",
            x_column=x_column,
            category_column=series_column,
            series=tuple(series),
            x_title=x_column,
            y_title=y_column,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                marker_size_pt=6.0,
                bar_group_span=0.8,
                bar_inner_width=0.72,
                figure_style=style,
            ),
            axis_plan=ScientificAxisPlan(
                x_from=x_axis[0],
                x_to=x_axis[1],
                x_step=x_axis[2],
                y_from=y_axis[0],
                y_to=y_axis[1],
                y_step=y_axis[2],
                z_from=z_axis[0],
                z_to=z_axis[1],
                z_step=z_axis[2],
            ),
            y_column=y_column,
            z_title=z_column,
            group_order=group_order,
        ),
        (),
    )


def _build_density_ridgeline3d_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    """Freeze supplied dual density profiles and one baseline focus per condition.

    All six scientific columns remain source-bound.  In particular, this
    function performs no KDE, normalization, smoothing, interpolation,
    threshold search, or focus-point inference.
    """

    condition_column = _require_one(assignments, "condition_id")
    position_column = _require_one(assignments, "condition_position")
    x_column = _require_one(assignments, "density_x")
    solid_column = _require_one(assignments, "density_solid")
    dashed_column = _require_one(assignments, "density_dashed")
    focal_column = _require_one(assignments, "focal_x")
    if _density_ridgeline3d_semantic_axis(position_column, condition_axis=True) is None:
        raise ScientificWorkflowError(
            "density_ridgeline3d_condition_axis_semantics_missing",
            "Condition Position must state a real scientific meaning and unit, or explicitly be Year/年份.",
            column=position_column,
        )
    if _density_ridgeline3d_semantic_axis(x_column, condition_axis=False) is None:
        raise ScientificWorkflowError(
            "density_ridgeline3d_x_axis_semantics_missing",
            "Density X must state a scientific meaning and unit, or explicitly be "
            "unitless/dimensionless/无量纲.",
            column=x_column,
        )
    solid_unit = _density_ridgeline3d_density_unit(solid_column)
    if solid_unit is None:
        raise ScientificWorkflowError(
            "density_ridgeline3d_density_semantics_missing",
            "Solid density must identify density/密度 and state a unit or explicit dimensionless status.",
            column=solid_column,
        )
    dashed_unit = _density_ridgeline3d_density_unit(dashed_column)
    if dashed_unit is None:
        raise ScientificWorkflowError(
            "density_ridgeline3d_density_semantics_missing",
            "Dashed density must identify density/密度 and state a unit or explicit dimensionless status.",
            column=dashed_column,
        )
    if solid_unit[0] != dashed_unit[0]:
        raise ScientificWorkflowError(
            "density_ridgeline3d_density_unit_mismatch",
            "Solid and dashed density columns must use the same normalized unit.",
        )
    density_unit = solid_unit[1]

    blank_condition = _blank_mask(frame[condition_column])
    if bool(blank_condition.any()):
        index = int(np.flatnonzero(blank_condition.to_numpy())[0])
        raise ScientificWorkflowError(
            "density_ridgeline3d_condition_empty",
            f"Condition is empty at data row {index + 2}.",
            column=condition_column,
            row=index + 2,
        )
    conditions = frame[condition_column].astype(str).str.strip()
    group_order = tuple(dict.fromkeys(conditions.tolist()))
    if not 2 <= len(group_order) <= 6:
        raise ScientificWorkflowError(
            "density_ridgeline3d_condition_count",
            "density_ridgeline3d requires 2–6 condition groups.",
            column=condition_column,
        )

    required_numeric = (position_column, x_column, solid_column, dashed_column)
    for column in required_numeric:
        missing = frame[column].isna()
        if bool(missing.any()):
            index = int(np.flatnonzero(missing.to_numpy())[0])
            raise ScientificWorkflowError(
                "density_ridgeline3d_required_value_missing",
                f"Column {column!r} has a missing plotted value at data row {index + 2}.",
                column=column,
                row=index + 2,
            )

    condition_positions: list[tuple[str, float]] = []
    direction: int | None = None
    for condition in group_order:
        mask = conditions == condition
        row_indices = np.flatnonzero(mask.to_numpy())
        if row_indices.size < 5:
            raise ScientificWorkflowError(
                "density_ridgeline3d_condition_too_short",
                f"Condition {condition!r} needs at least five supplied profile points.",
                column=condition_column,
            )

        position = frame.loc[mask, position_column].to_numpy(dtype=float, copy=True)
        if not bool(np.all(position == position[0])):
            raise ScientificWorkflowError(
                "density_ridgeline3d_position_not_constant",
                f"Condition position must be constant within {condition!r}.",
                column=position_column,
            )
        condition_positions.append((condition, float(position[0])))

        x = frame.loc[mask, x_column].to_numpy(dtype=float, copy=True)
        differences = np.diff(x)
        increasing = bool(np.all(differences > 0.0))
        decreasing = bool(np.all(differences < 0.0))
        if not (increasing or decreasing):
            raise ScientificWorkflowError(
                "density_ridgeline3d_x_not_strict_monotonic",
                f"Density X must be strictly monotonic with no duplicates in {condition!r}.",
                column=x_column,
            )
        current_direction = 1 if increasing else -1
        if direction is None:
            direction = current_direction
        elif direction != current_direction:
            raise ScientificWorkflowError(
                "density_ridgeline3d_x_direction_mismatch",
                "All condition groups must use the same Density X direction.",
                column=x_column,
            )

        for density_column in (solid_column, dashed_column):
            values = frame.loc[mask, density_column].to_numpy(dtype=float, copy=True)
            if bool(np.any(values < 0.0)):
                local_index = int(np.flatnonzero(values < 0.0)[0])
                source_index = int(row_indices[local_index])
                raise ScientificWorkflowError(
                    "density_ridgeline3d_density_negative",
                    f"Density values must be nonnegative at data row {source_index + 2}.",
                    column=density_column,
                    row=source_index + 2,
                )

        focal = frame.loc[mask, focal_column]
        supplied_focus = focal[focal.notna()].to_numpy(dtype=float, copy=True)
        if supplied_focus.size != 1:
            raise ScientificWorkflowError(
                "density_ridgeline3d_focal_count",
                f"Condition {condition!r} needs exactly one supplied Focal X value and blanks elsewhere.",
                column=focal_column,
            )
        focal_value = float(supplied_focus[0])
        x_lower = float(np.min(x))
        x_upper = float(np.max(x))
        if not x_lower <= focal_value <= x_upper:
            raise ScientificWorkflowError(
                "density_ridgeline3d_focal_out_of_range",
                f"Focal X for {condition!r} must lie inside its supplied Density X range.",
                column=focal_column,
            )

    positions = np.asarray([position for _condition, position in condition_positions], dtype=float)
    if not bool(np.all(np.diff(positions) > 0.0)):
        raise ScientificWorkflowError(
            "density_ridgeline3d_condition_order_invalid",
            "Condition first-appearance order must follow strictly increasing condition positions.",
            column=position_column,
        )

    parity_issues = density_ridgeline3d_contract_issues(
        frame,
        {
            "condition_id": condition_column,
            "condition_position": position_column,
            "density_x": x_column,
            "density_solid": solid_column,
            "density_dashed": dashed_column,
            "focal_x": focal_column,
        },
    )
    if parity_issues:
        raise ScientificWorkflowError(
            "density_ridgeline3d_contract_parity_failed",
            "The density_ridgeline3d strict-detection contract diverged from runtime preparation: "
            + ", ".join(parity_issues),
        )

    series = (
        ScientificSeries(
            source_column=solid_column,
            label=solid_column,
            group="solid",
            series_role="density_solid",
        ),
        ScientificSeries(
            source_column=dashed_column,
            label=dashed_column,
            group="dashed",
            series_role="density_dashed",
        ),
    )
    x_axis = _nice_axis(
        frame[x_column].to_numpy(dtype=float),
        include_zero=False,
        padding_fraction=0.04,
    )
    y_axis = _nice_axis(positions, include_zero=False, padding_fraction=0.08)
    density_values = np.concatenate(
        (
            frame[solid_column].to_numpy(dtype=float, copy=True),
            frame[dashed_column].to_numpy(dtype=float, copy=True),
        )
    )
    z_axis = _nice_axis(density_values, include_zero=True, padding_fraction=0.06)
    style = resolve_adaptive_style(
        template_id="density_ridgeline3d",
        plot_kind="density_ridgeline3d",
        row_count=len(frame),
        series_count=len(group_order),
    )
    return (
        ScientificPlotSpec(
            plot_kind="density_ridgeline3d",
            plot_mode="ordered_dual_profile_focus",
            x_column=x_column,
            category_column=condition_column,
            series=series,
            x_title=x_column,
            y_title=position_column,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                marker_size_pt=9.0,
                bar_group_span=0.8,
                bar_inner_width=0.72,
                figure_style=style,
            ),
            axis_plan=ScientificAxisPlan(
                x_from=x_axis[0],
                x_to=x_axis[1],
                x_step=x_axis[2],
                y_from=y_axis[0],
                y_to=y_axis[1],
                y_step=y_axis[2],
                z_from=z_axis[0],
                z_to=z_axis[1],
                z_step=z_axis[2],
            ),
            y_column=position_column,
            z_title=f"Density ({density_unit})",
            group_order=group_order,
            focal_x_column=focal_column,
            condition_positions=tuple(condition_positions),
        ),
        (),
    )


def _build_error_spec(
    template_id: str,
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    category = template_id in _CATEGORY_TABLE_TEMPLATE_IDS
    anchor = _require_one(assignments, "category" if category else "x")
    series_columns = _require_series(assignments)
    error_columns = [column for column, role in assignments.items() if role == "error"]
    if template_id == "line_error" and not error_columns:
        raise ScientificWorkflowError("error_missing", "A line-with-error plot needs an error column.")
    aggregate_error_column = None
    if template_id == "stacked_bar" and error_columns:
        if len(error_columns) != 1:
            raise ScientificWorkflowError(
                "stacked_total_error_count",
                "A stacked chart accepts one explicit total SD/SE/SEM column.",
            )
        aggregate_error_column = error_columns[0]
        pairs: dict[str, tuple[str, str]] = {}
    else:
        pairs = _pair_errors(series_columns, error_columns)
    warnings: list[str] = []
    series_items: list[ScientificSeries] = []
    for column in series_columns:
        error_column = None
        error_kind = None
        if column in pairs:
            error_column, error_kind = pairs[column]
            values = frame[error_column]
            negative = values.notna() & (values < 0)
            if bool(negative.any()):
                index = int(np.flatnonzero(negative.to_numpy())[0])
                raise ScientificWorkflowError(
                    "negative_error",
                    f"Error column {error_column!r} contains a negative value at data row {index + 2}.",
                    column=error_column,
                    row=index + 2,
                )
            if error_kind == "custom":
                warnings.append("error_kind_unspecified")
        series_items.append(
            ScientificSeries(
                column,
                column,
                error_column=error_column,
                error_kind=error_kind,
            )
        )
    if aggregate_error_column is not None:
        aggregate_values = frame[aggregate_error_column]
        negative = aggregate_values.notna() & (aggregate_values < 0)
        if bool(negative.any()):
            index = int(np.flatnonzero(negative.to_numpy())[0])
            raise ScientificWorkflowError(
                "negative_error",
                f"Error column {aggregate_error_column!r} contains a negative value at data row {index + 2}.",
                column=aggregate_error_column,
                row=index + 2,
            )
        warnings.append("stacked_total_error_explicit")
    series = tuple(series_items)
    _require_points(
        frame,
        None if category else anchor,
        series_columns,
        category_column=anchor if category else None,
    )
    if template_id not in {"heatmap", "confusion_matrix"}:
        if len(series) > 12:
            warnings.append("series_count_excessive")
        elif len(series) > 8:
            warnings.append("series_count_high")
    bar_group_span = 0.8
    bar_inner_width = 0.72
    if category and len(series) >= 5:
        bar_group_span = 0.86 if len(series) <= 8 else 0.90
        bar_inner_width = 0.78 if len(series) <= 8 else 0.80
    if category:
        categories = [str(value) for value in frame[anchor].tolist()]
        if len(categories) > 20 and template_id not in {"heatmap", "confusion_matrix"}:
            warnings.append("category_count_high")
        if categories and max(len(value) for value in categories) > 12:
            warnings.append("category_labels_long")
    else:
        categories = []
    category_rotation = (
        45.0
        if category
        and template_id not in {"horizontal_bar", "pie", "radar", "heatmap", "confusion_matrix"}
        and (len(categories) > 6 or max((len(value) for value in categories), default=0) > 10)
        else 0.0
    )
    y_title = (
        "Composition (%)"
        if template_id == "percent_stacked_bar"
        else series[0].label
        if len(series) == 1
        else "Value"
    )
    plot_kinds = {
        "bar": "bar_error",
        "horizontal_bar": "horizontal_bar",
        "stacked_bar": "stacked_bar",
        "percent_stacked_bar": "percent_stacked_bar",
        "pie": "pie",
        "radar": "radar",
        "heatmap": "heatmap",
        "confusion_matrix": "heatmap",
    }
    if template_id in {"stacked_bar", "percent_stacked_bar", "pie"}:
        for column in series_columns:
            negative = frame[column].notna() & (frame[column] < 0)
            if bool(negative.any()):
                index = int(np.flatnonzero(negative.to_numpy())[0])
                raise ScientificWorkflowError(
                    "negative_value",
                    f"Column {column!r} contains a negative value at data row {index + 2}.",
                    column=column,
                    row=index + 2,
                )
    if template_id == "pie" and len(series) != 1:
        raise ScientificWorkflowError(
            "pie_series_count",
            "A pie chart needs exactly one numeric value column.",
        )
    if template_id in {"stacked_bar", "percent_stacked_bar"} and len(series) < 2:
        raise ScientificWorkflowError(
            "stacked_series_count",
            "A stacked chart needs at least two numeric series.",
        )
    if template_id == "radar":
        if len(series) < 2 or len(frame) < 3:
            raise ScientificWorkflowError(
                "radar_shape",
                "A radar chart needs at least three metrics and two numeric series.",
            )
        all_values = frame[series_columns].to_numpy(dtype=float)
        if bool(np.any(all_values < 0)):
            raise ScientificWorkflowError(
                "radar_negative_value",
                "Radar values must be non-negative; use a diverging chart for signed values.",
            )
    if template_id == "heatmap" and (len(series) < 2 or len(frame) < 2):
        raise ScientificWorkflowError(
            "heatmap_shape",
            "A heatmap needs at least two rows and two numeric value columns.",
        )
    if template_id == "heatmap" and not heatmap_cell_labels_enabled(len(frame), len(series)):
        warnings.append("heatmap_cell_labels_hidden")
        if max(len(frame), len(series)) > 60 or len(frame) * len(series) > 3600:
            warnings.append("heatmap_ultra_dense")
        else:
            warnings.append("heatmap_dense_matrix")
    if template_id == "confusion_matrix":
        if len(series) < 2 or len(frame) < 2:
            raise ScientificWorkflowError(
                "confusion_matrix_shape",
                "A confusion matrix needs at least two actual classes and two predicted classes.",
            )
        if len(series) != len(frame):
            warnings.append("confusion_matrix_not_square")
        negative = frame[series_columns].notna() & (frame[series_columns] < 0)
        if bool(negative.any().any()):
            row_index, column_index = np.argwhere(negative.to_numpy())[0]
            raise ScientificWorkflowError(
                "confusion_matrix_negative",
                "Confusion-matrix counts or supplied proportions cannot be negative.",
                column=series_columns[int(column_index)],
                row=int(row_index) + 2,
            )
    if template_id == "percent_stacked_bar":
        totals = frame[series_columns].sum(axis=1, min_count=1)
        invalid = totals.isna() | (totals <= 0)
        if bool(invalid.any()):
            index = int(np.flatnonzero(invalid.to_numpy())[0])
            raise ScientificWorkflowError(
                "percent_total_nonpositive",
                f"Percent-stacked data needs a positive row total at data row {index + 2}.",
                row=index + 2,
            )
        warnings.append("display_percent_normalized")
    if template_id == "pie":
        total = float(frame[series_columns[0]].sum(skipna=True))
        if total <= 0:
            raise ScientificWorkflowError("pie_total_nonpositive", "Pie values must have a positive total.")
        if len(frame) > 12:
            warnings.append("pie_category_count_excessive")
        elif len(frame) > 8:
            warnings.append("pie_category_count_high")
    plot_kind = plot_kinds.get(template_id, "line_error")
    numeric_values = frame[series_columns].to_numpy(dtype=float)
    signed_values = bool(np.nanmin(numeric_values) < 0 < np.nanmax(numeric_values))
    max_label_length = max((len(value) for value in categories), default=0)
    style = resolve_adaptive_style(
        template_id=template_id,
        plot_kind=plot_kind,
        row_count=len(frame),
        series_count=len(series),
        max_label_length=max_label_length,
        category_rotation_deg=category_rotation,
        signed_values=signed_values,
    )
    if template_id == "confusion_matrix":
        x_title = "Predicted class"
        y_title = "Actual class"
    elif template_id == "heatmap":
        x_title = "Series"
        y_title = anchor
    else:
        x_title = anchor
    spec = ScientificPlotSpec(
        plot_kind=plot_kind,
        plot_mode="default",
        x_column=None if category else anchor,
        category_column=anchor if category else None,
        series=series,
        x_title=x_title,
        y_title=y_title,
        y2_title=None,
        x_scale="linear",
        y_scale="linear",
        display_transform="identity",
        display_plan=ScientificDisplayPlan(
            7.0,
            bar_group_span,
            bar_inner_width,
            category_rotation,
            style,
        ),
        axis_plan=_axis_plan(
            frame,
            x_column=None if category else anchor,
            series=series,
            category=category,
            include_zero_y=category,
        ),
        aggregate_error_column=aggregate_error_column,
    )
    return spec, tuple(dict.fromkeys(warnings))


def _build_raw_distribution_spec(
    template_id: str,
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    series_columns = _require_series(assignments)
    _require_points(frame, None, series_columns)
    minimum = 5 if template_id in {"violin", "histogram", "raincloud"} else 2
    for column in series_columns:
        count = int(frame[column].notna().sum())
        if count < minimum:
            raise ScientificWorkflowError(
                "raw_series_too_short",
                f"Series {column!r} needs at least {minimum} raw observations for {template_id}.",
                column=column,
            )
    series = tuple(ScientificSeries(column, column) for column in series_columns)
    values = np.concatenate([frame[column].dropna().to_numpy(dtype=float) for column in series_columns])
    warnings: list[str] = []
    if len(series) > 12:
        warnings.append("series_count_excessive")
    elif len(series) > 8:
        warnings.append("series_count_high")
    if template_id == "histogram":
        bin_begin, bin_end, bin_size = _histogram_bin_geometry(values)
        edges = np.arange(bin_begin, bin_end + bin_size * 0.5, bin_size)
        maximum_count = max(
            int(np.histogram(frame[column].dropna().to_numpy(dtype=float), bins=edges)[0].max())
            for column in series_columns
        )
        y_step = _nice_number(maximum_count * 1.05 / 5.0, round_value=True)
        y_upper = math.ceil(maximum_count * 1.05 / y_step) * y_step
        axis_plan = ScientificAxisPlan(
            bin_begin,
            bin_end,
            bin_size,
            0.0,
            y_upper,
            y_step,
        )
        x_title = series_columns[0] if len(series_columns) == 1 else "Observed value"
        y_title = "Count"
        bin_rule = "freedman_diaconis_nice_step_v1"
    else:
        # The half-violin kernel may extend slightly beyond the outermost raw
        # observation.  Freeze a larger display-only margin so the editable
        # density tail never touches the frame in the public Raincloud route.
        y_axis = _nice_axis(
            values,
            padding_fraction=0.25 if template_id == "raincloud" else 0.05,
        )
        axis_plan = ScientificAxisPlan(None, None, None, *y_axis)
        x_title = "Group"
        y_title = "Observed value"
        bin_rule = None
        bin_begin = None
        bin_end = None
        bin_size = None
    plot_kind = template_id
    style = resolve_adaptive_style(
        template_id=template_id,
        plot_kind=plot_kind,
        row_count=len(frame),
        series_count=len(series),
        max_label_length=max(map(len, series_columns), default=0),
    )
    return (
        ScientificPlotSpec(
            plot_kind=plot_kind,
            plot_mode="wide_raw",
            x_column=None,
            category_column=None,
            series=series,
            x_title=x_title,
            y_title=y_title,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform=(
                "origin_box_halfviolin_kernel_density_raw_dots_mean_plus_minus_1sd_v1"
                if template_id == "raincloud"
                else "identity"
            ),
            display_plan=ScientificDisplayPlan(7.0, 0.8, 0.72, figure_style=style),
            axis_plan=axis_plan,
            bin_rule=bin_rule,
            bin_begin=bin_begin,
            bin_end=bin_end,
            bin_size=bin_size,
        ),
        tuple(warnings),
    )


def _build_shap_summary_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    feature_column = _require_one(assignments, "feature")
    shap_column = _require_one(assignments, "shap")
    feature_value_column = _require_one(assignments, "feature_value")

    blank_features = _blank_mask(frame[feature_column])
    if bool(blank_features.any()):
        index = int(np.flatnonzero(blank_features.to_numpy())[0])
        raise ScientificWorkflowError(
            "shap_feature_empty",
            f"Feature column {feature_column!r} is empty at data row {index + 2}.",
            column=feature_column,
            row=index + 2,
        )
    missing_numeric = frame[[shap_column, feature_value_column]].isna().any(axis=1)
    if bool(missing_numeric.any()):
        index = int(np.flatnonzero(missing_numeric.to_numpy())[0])
        raise ScientificWorkflowError(
            "shap_value_missing",
            "SHAP summary rows need both a precomputed SHAP value and a numeric feature value "
            f"at data row {index + 2}; rows are not silently dropped.",
            row=index + 2,
        )

    feature_names = [str(value).strip() for value in frame[feature_column].tolist()]
    input_order = tuple(dict.fromkeys(feature_names))
    if len(input_order) < 2:
        raise ScientificWorkflowError(
            "shap_feature_count",
            "SHAP summary needs at least two distinct features.",
            column=feature_column,
        )
    for feature in input_order:
        count = feature_names.count(feature)
        if count < 3:
            raise ScientificWorkflowError(
                "shap_feature_too_short",
                f"Feature {feature!r} needs at least three supplied observations.",
                column=feature_column,
            )

    try:
        shap_plan = build_shap_composite_plan(
            frame,
            assignments,
            profile=plot_mode,
        )
    except ShapCompositeError as exc:
        raise ScientificWorkflowError(
            exc.code,
            str(exc),
            column=exc.column,
            row=exc.row,
        ) from exc
    category_order = shap_plan.feature_order

    shap_values = frame[shap_column].to_numpy(dtype=float, copy=True)
    x_axis = _nice_axis(shap_values, include_zero=True, padding_fraction=0.08)
    style = resolve_adaptive_style(
        template_id="shap_summary",
        plot_kind="shap_summary",
        row_count=len(category_order),
        series_count=1,
        max_label_length=max(map(len, category_order), default=0),
        signed_values=True,
    )
    warnings = ["feature_value_color_normalized_within_feature"]
    if shap_plan.mean_abs_source == "derived_from_supplied_shap":
        warnings.append("mean_abs_shap_derived_from_supplied_rows_requires_confirmation")
    elif shap_plan.mean_abs_source == "provided":
        warnings.append("provided_mean_abs_shap_validated_against_supplied_rows")
    if shap_plan.group_contribution_source == "derived_from_supplied_shap":
        warnings.append("group_contribution_derived_from_supplied_rows_requires_confirmation")
    elif shap_plan.group_contribution_source == "provided":
        warnings.append("provided_group_contribution_validated_against_supplied_rows")
    for feature in category_order:
        mask = np.asarray(feature_names, dtype=object) == feature
        values = frame.loc[mask, feature_value_column].to_numpy(dtype=float)
        if values.size and math.isclose(float(np.min(values)), float(np.max(values))):
            warnings.append("constant_feature_value_centered")
            break
    return (
        ScientificPlotSpec(
            plot_kind="shap_summary",
            plot_mode=shap_plan.profile,
            x_column=shap_column,
            category_column=feature_column,
            series=(
                ScientificSeries(
                    shap_column,
                    "SHAP value",
                    color_column=feature_value_column,
                ),
            ),
            x_title="SHAP value (impact on model output)",
            y_title="",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform=(
                "preserve_precomputed_shap_values; deterministic_binned_symmetric_beeswarm; "
                "within_feature_minmax_color_only"
            ),
            display_plan=ScientificDisplayPlan(
                6.8,
                0.8,
                0.72,
                figure_style=style,
            ),
            axis_plan=ScientificAxisPlan(
                x_axis[0],
                x_axis[1],
                x_axis[2],
                0.5,
                len(category_order) + 0.85,
                1.0,
            ),
            reference_value=0.0,
            jitter_rule="deterministic_binned_symmetric_v1",
            color_rule="within_feature_minmax_low_blue_high_red_v1",
            category_order=category_order,
            group_order=shap_plan.group_order,
            shap_plan=shap_plan,
        ),
        tuple(dict.fromkeys(warnings)),
    )


def _build_bubble_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    size_column = _require_one(assignments, "size")
    series_columns = _require_series(assignments)
    if len(series_columns) != 1:
        raise ScientificWorkflowError(
            "bubble_series_count",
            "Bubble data needs exactly one Y/response series.",
        )
    response = series_columns[0]
    _require_points(frame, x_column, [response, size_column])
    invalid_size = frame[size_column].notna() & (frame[size_column] <= 0)
    if bool(invalid_size.any()):
        index = int(np.flatnonzero(invalid_size.to_numpy())[0])
        raise ScientificWorkflowError(
            "bubble_size_nonpositive",
            f"Bubble size {size_column!r} must be positive at data row {index + 2}.",
            column=size_column,
            row=index + 2,
        )
    series = (ScientificSeries(response, response, size_column=size_column),)
    style = resolve_adaptive_style(
        template_id="bubble",
        plot_kind="bubble",
        row_count=len(frame),
        series_count=1,
    )
    return (
        ScientificPlotSpec(
            plot_kind="bubble",
            plot_mode="indexed_size",
            x_column=x_column,
            category_column=None,
            series=series,
            x_title=x_column,
            y_title=response,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(7.0, 0.8, 0.72, figure_style=style),
            axis_plan=_axis_plan(
                frame,
                x_column=x_column,
                series=series,
                category=False,
                include_zero_y=False,
                # Indexed point sizes are expressed in typographic points and
                # can otherwise be clipped even when the data centers lie
                # inside a conventional 5% numeric margin.
                padding_fraction=0.12,
            ),
        ),
        (),
    )


def _build_forest_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    category = _require_one(assignments, "category")
    estimate = _require_one(assignments, "estimate")
    lower = _require_one(assignments, "lower")
    upper = _require_one(assignments, "upper")
    reference_columns = [column for column, role in assignments.items() if role == "reference"]
    _require_points(frame, None, [estimate, lower, upper], category_column=category)
    complete = frame[[estimate, lower, upper]].notna().all(axis=1)
    if not bool(complete.all()):
        index = int(np.flatnonzero((~complete).to_numpy())[0])
        raise ScientificWorkflowError(
            "forest_interval_missing",
            f"Forest estimate and interval are incomplete at data row {index + 2}.",
            row=index + 2,
        )
    invalid = (frame[lower] > frame[estimate]) | (frame[estimate] > frame[upper])
    if bool(invalid.any()):
        index = int(np.flatnonzero(invalid.to_numpy())[0])
        raise ScientificWorkflowError(
            "forest_interval_order",
            f"Forest data must satisfy lower <= estimate <= upper at data row {index + 2}.",
            row=index + 2,
        )
    reference_value: float | None = None
    if reference_columns:
        reference = frame[reference_columns[0]].dropna().to_numpy(dtype=float)
        if reference.size:
            if not np.allclose(reference, reference[0], rtol=0.0, atol=1e-12):
                raise ScientificWorkflowError(
                    "forest_reference_not_constant",
                    "Forest reference values must be identical in every non-empty row.",
                    column=reference_columns[0],
                )
            reference_value = float(reference[0])
    x_values = np.concatenate((frame[lower].to_numpy(dtype=float), frame[upper].to_numpy(dtype=float)))
    x_axis = _nice_axis(x_values)
    series = (
        ScientificSeries(
            estimate,
            estimate,
            lower_column=lower,
            upper_column=upper,
        ),
    )
    labels = [str(value) for value in frame[category]]
    style = resolve_adaptive_style(
        template_id="forest",
        plot_kind="forest",
        row_count=len(frame),
        series_count=1,
        max_label_length=max(map(len, labels), default=0),
    )
    return (
        ScientificPlotSpec(
            plot_kind="forest",
            plot_mode="interval",
            x_column=None,
            category_column=category,
            series=series,
            x_title=estimate,
            y_title="",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(8.0, 0.8, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(
                x_axis[0],
                x_axis[1],
                x_axis[2],
                0.5,
                len(frame) + 0.5,
                1.0,
            ),
            reference_value=reference_value,
        ),
        (),
    )


def _constant_role_value(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    role: str,
) -> tuple[str, float]:
    column = _require_one(assignments, role)
    values = frame[column].dropna().to_numpy(dtype=float)
    if not values.size:
        raise ScientificWorkflowError(
            f"{role}_empty",
            f"Column {column!r} has no numeric {role} value.",
            column=column,
        )
    if not np.allclose(values, values[0], rtol=0.0, atol=1e-12):
        raise ScientificWorkflowError(
            f"{role}_not_constant",
            f"Column {column!r} must repeat one constant {role} value.",
            column=column,
        )
    return column, float(values[0])


def _build_diagnostic_curve_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    series_columns = _require_series(assignments)
    _require_points(frame, x_column, series_columns)
    values = frame[[x_column, *series_columns]].to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size and (float(np.min(finite)) < 0.0 or float(np.max(finite)) > 1.0):
        raise ScientificWorkflowError(
            "diagnostic_probability_range",
            "ROC and Precision-Recall coordinates must stay within 0 to 1.",
        )
    x_values = frame[x_column].dropna().to_numpy(dtype=float)
    if x_values.size < 2:
        raise ScientificWorkflowError(
            "diagnostic_curve_too_short",
            "A diagnostic curve needs at least two coordinate pairs.",
        )
    warnings: list[str] = []
    reference_values: tuple[float, ...] = ()
    reference_labels: tuple[str, ...] = ()
    reference_geometry = "diagonal"
    if plot_mode == "pr":
        reference_columns = [column for column, role in assignments.items() if role == "reference"]
        if len(reference_columns) != 1:
            raise ScientificWorkflowError(
                "prevalence_missing",
                "Precision-Recall input needs one explicit prevalence baseline column.",
            )
        _, prevalence = _constant_role_value(frame, assignments, "reference")
        if not 0.0 <= prevalence <= 1.0:
            raise ScientificWorkflowError(
                "prevalence_range",
                "Precision-Recall prevalence must stay within 0 to 1.",
                column=reference_columns[0],
            )
        reference_values = (prevalence,)
        reference_labels = ("Prevalence",)
        reference_geometry = "horizontal"
        x_title = "Recall"
        y_title = "Precision"
    else:
        plot_mode = "roc"
        reference_labels = ("Chance",)
        x_title = "False positive rate"
        y_title = "True positive rate"
    series = tuple(ScientificSeries(column, column) for column in series_columns)
    style = resolve_adaptive_style(
        template_id="diagnostic_curve",
        plot_kind="diagnostic_curve",
        row_count=len(frame),
        series_count=len(series),
    )
    return (
        ScientificPlotSpec(
            plot_kind="diagnostic_curve",
            plot_mode=plot_mode,
            x_column=x_column,
            category_column=None,
            series=series,
            x_title=x_title,
            y_title=y_title,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(6.5, 0.8, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(0.0, 1.0, 0.2, 0.0, 1.0, 0.2),
            reference_values=reference_values,
            reference_labels=reference_labels,
            reference_geometry=reference_geometry,
        ),
        tuple(warnings),
    )


def _build_calibration_curve_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    observed_column = _require_one(assignments, "series")
    count_column = _require_one(assignments, "count")
    _require_points(frame, x_column, [observed_column, count_column])
    probability_values = frame[[x_column, observed_column]].to_numpy(dtype=float)
    finite_probability = probability_values[np.isfinite(probability_values)]
    if finite_probability.size and (
        float(np.min(finite_probability)) < 0.0 or float(np.max(finite_probability)) > 1.0
    ):
        raise ScientificWorkflowError(
            "calibration_probability_range",
            "Predicted probability and observed fraction must stay within 0 to 1.",
        )
    counts = frame[count_column].dropna().to_numpy(dtype=float)
    if counts.size < 2 or np.any(counts < 0.0) or not np.any(counts > 0.0):
        raise ScientificWorkflowError(
            "calibration_count_invalid",
            "Bin count needs at least two non-negative values and one positive value.",
            column=count_column,
        )
    series = (
        ScientificSeries(
            observed_column,
            observed_column,
            size_column=count_column,
        ),
    )
    style = resolve_adaptive_style(
        template_id="calibration_curve",
        plot_kind="calibration_curve",
        row_count=len(frame),
        series_count=1,
    )
    return (
        ScientificPlotSpec(
            plot_kind="calibration_curve",
            plot_mode="precomputed_bins",
            x_column=x_column,
            category_column=None,
            series=series,
            x_title="Predicted probability",
            y_title="Observed fraction",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="scale_bin_count_to_bottom_12_percent",
            display_plan=ScientificDisplayPlan(7.0, 0.8, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(0.0, 1.0, 0.2, 0.0, 1.0, 0.2),
            reference_labels=("Perfect calibration",),
            reference_geometry="diagonal",
        ),
        ("bin_count_display_scaled",),
    )


def _build_decision_curve_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    model_columns = _require_series(assignments)
    treat_all_column = _require_one(assignments, "treat_all")
    treat_none_column = _require_one(assignments, "treat_none")
    plotted_columns = [*model_columns, treat_all_column, treat_none_column]
    _require_points(frame, x_column, plotted_columns)
    thresholds = frame[x_column].dropna().to_numpy(dtype=float)
    if thresholds.size < 2 or np.any(thresholds < 0.0) or np.any(thresholds > 1.0):
        raise ScientificWorkflowError(
            "decision_threshold_range",
            "Decision-curve thresholds must stay within 0 to 1.",
            column=x_column,
        )
    series = tuple(
        ScientificSeries(column, column) for column in [*model_columns, treat_all_column, treat_none_column]
    )
    # The model is the evidentiary target.  Treat-all can diverge sharply at
    # high thresholds and must not collapse every model into a few pixels.
    # Keep all source points editable, but plan the visible Y window from the
    # model curves and the explicit zero baseline.
    y_values = np.concatenate([frame[column].dropna().to_numpy(dtype=float) for column in model_columns])
    y_axis = _nice_axis(
        np.concatenate([y_values, np.asarray([0.0])]),
        include_zero=True,
        padding_fraction=0.08,
    )
    warnings: list[str] = []
    treat_all_values = frame[treat_all_column].dropna().to_numpy(dtype=float)
    if treat_all_values.size and (
        float(np.min(treat_all_values)) < y_axis[0] or float(np.max(treat_all_values)) > y_axis[1]
    ):
        warnings.append("treat_all_clipped_to_model_evidence_window")
    threshold_min = float(np.min(thresholds))
    threshold_max = float(np.max(thresholds))
    threshold_span = max(threshold_max - threshold_min, 0.05)
    x_step = _nice_number(threshold_span / 5.0, round_value=True)
    x_from = max(0.0, math.floor(threshold_min / x_step) * x_step)
    x_to = min(1.0, math.ceil(threshold_max / x_step) * x_step)
    if math.isclose(x_from, x_to):
        x_to = min(1.0, x_from + x_step)
    style = resolve_adaptive_style(
        template_id="decision_curve",
        plot_kind="decision_curve",
        row_count=len(frame),
        series_count=len(series),
    )
    return (
        ScientificPlotSpec(
            plot_kind="decision_curve",
            plot_mode="precomputed_net_benefit",
            x_column=x_column,
            category_column=None,
            series=series,
            x_title="Threshold probability",
            y_title="Net benefit",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(0.0, 0.8, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(
                x_from,
                x_to,
                x_step,
                y_axis[0],
                y_axis[1],
                y_axis[2],
            ),
        ),
        tuple(warnings),
    )


def _build_bland_altman_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    mean_column = _require_one(assignments, "mean")
    difference_column = _require_one(assignments, "difference")
    _require_points(frame, mean_column, [difference_column])
    _, bias = _constant_role_value(frame, assignments, "bias")
    _, lower = _constant_role_value(frame, assignments, "loa_lower")
    _, upper = _constant_role_value(frame, assignments, "loa_upper")
    if not lower <= bias <= upper:
        raise ScientificWorkflowError(
            "bland_altman_limit_order",
            "Bland-Altman input must satisfy Lower LoA <= Bias <= Upper LoA.",
        )
    series = (ScientificSeries(difference_column, difference_column),)
    base_axis = _axis_plan(
        frame,
        x_column=mean_column,
        series=series,
        category=False,
        include_zero_y=False,
        padding_fraction=0.10,
    )
    y_axis = _nice_axis(
        np.concatenate(
            [frame[difference_column].dropna().to_numpy(dtype=float), np.asarray([lower, bias, upper])]
        ),
        padding_fraction=0.10,
    )
    style = resolve_adaptive_style(
        template_id="bland_altman",
        plot_kind="bland_altman",
        row_count=len(frame),
        series_count=1,
    )
    return (
        ScientificPlotSpec(
            plot_kind="bland_altman",
            plot_mode="precomputed_limits",
            x_column=mean_column,
            category_column=None,
            series=series,
            x_title="Pair mean",
            y_title="Difference",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(7.0, 0.8, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(
                base_axis.x_from,
                base_axis.x_to,
                base_axis.x_step,
                y_axis[0],
                y_axis[1],
                y_axis[2],
            ),
            reference_values=(bias, lower, upper),
            reference_labels=("Bias", "Lower LoA", "Upper LoA"),
            reference_geometry="horizontal",
        ),
        (),
    )


def _parse_grouped_box_header(column: str) -> tuple[str, str]:
    parts = re.split(r"\s*[|｜]\s*", unicodedata.normalize("NFKC", column), maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ScientificWorkflowError(
            "grouped_box_header",
            f"Grouped box column {column!r} must use 'Category | Group'.",
            column=column,
        )
    return parts[0].strip(), parts[1].strip()


def _build_grouped_box_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    series_columns = _require_series(assignments)
    if len(series_columns) < 2:
        raise ScientificWorkflowError(
            "grouped_box_columns",
            "Grouped box data needs at least two raw-observation columns.",
        )
    parsed = [(column, *_parse_grouped_box_header(column)) for column in series_columns]
    categories = tuple(dict.fromkeys(category for _column, category, _group in parsed))
    groups = tuple(dict.fromkeys(group for _column, _category, group in parsed))
    if len(categories) < 2 or len(groups) < 2:
        raise ScientificWorkflowError(
            "grouped_box_design",
            "Grouped box data needs at least two categories and two groups.",
        )
    for column in series_columns:
        if int(frame[column].notna().sum()) < 5:
            raise ScientificWorkflowError(
                "grouped_box_series_too_short",
                f"Series {column!r} needs at least five raw observations.",
                column=column,
            )
    combinations = {(category, group) for _column, category, group in parsed}
    warnings: list[str] = []
    if any((category, group) not in combinations for category in categories for group in groups):
        warnings.append("grouped_box_unbalanced_design")
    series = tuple(
        ScientificSeries(column, column, category=category, group=group) for column, category, group in parsed
    )
    values = np.concatenate([frame[column].dropna().to_numpy(dtype=float) for column in series_columns])
    # Reserve a stable lower evidence band for per-box sample-size labels.
    # The labels are part of the graph, not page-margin decorations.
    y_axis = _nice_axis(values, padding_fraction=0.30)
    style = resolve_adaptive_style(
        template_id="grouped_box",
        plot_kind="grouped_box",
        row_count=len(frame),
        series_count=len(series),
        max_label_length=max(map(len, categories), default=0),
    )
    return (
        ScientificPlotSpec(
            plot_kind="grouped_box",
            plot_mode="wide_category_group_raw",
            x_column=None,
            category_column=None,
            series=series,
            x_title="Condition",
            y_title="Observed value",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="origin_grouped_box_quartiles_raw_points_n_v2",
            display_plan=ScientificDisplayPlan(5.5, 0.82, 0.72, figure_style=style),
            axis_plan=ScientificAxisPlan(0.5, len(series) + 0.5, 1.0, *y_axis),
            category_order=categories,
            group_order=groups,
        ),
        tuple(warnings),
    )


def _match_fit_series(fit_column: str, observed_columns: list[str]) -> str:
    base = _canonical(_fit_base_name(fit_column))
    matches = [column for column in observed_columns if _canonical(column) == base]
    if len(matches) == 1:
        return matches[0]
    if len(observed_columns) == 1:
        return observed_columns[0]
    raise ScientificWorkflowError(
        "pl_fit_pair_ambiguous",
        f"Fit column {fit_column!r} cannot be paired to one measured PL series by name.",
        column=fit_column,
    )


def _nmr_nucleus_prefix(column: str) -> str:
    normalized = unicodedata.normalize("NFKC", column)
    match = re.search(r"(?<!\d)(\d{1,3})\s*([A-Z][a-z]?)", normalized)
    if match is None:
        return ""
    superscript = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"{match.group(1).translate(superscript)}{match.group(2)} "


def _material_axis_titles(
    template_id: str,
    x_column: str,
    series_columns: list[str],
) -> tuple[str, str, tuple[str, ...]]:
    x_unit = _physical_unit(x_column)
    suffix = f" ({_format_unit(x_unit)})" if x_unit else ""
    warnings: list[str] = []
    if not x_unit:
        warnings.append("material_x_unit_missing")
    if template_id == "dsc":
        y_unit = _common_unit(series_columns)
        return (
            f"Temperature{suffix}",
            f"Heat flow ({y_unit})" if y_unit else "Heat flow",
            tuple(warnings),
        )
    if template_id == "nmr":
        return (
            f"{_nmr_nucleus_prefix(x_column)}Chemical shift{suffix}",
            "Intensity (a.u.)",
            tuple(warnings),
        )
    if template_id == "xps_compare":
        canonical = [_canonical(column) for column in series_columns]
        y_title = (
            "Counts"
            if all(any(token in value for token in ("count", "计数")) for value in canonical)
            else "Intensity (a.u.)"
        )
        return f"Binding Energy{suffix}", y_title, tuple(warnings)
    canonical = [_canonical(column) for column in series_columns]
    if all(
        any(token in value for token in ("transmittance", "transmission", "透过率", "透射"))
        for value in canonical
    ):
        y_title = "Transmittance (%)"
    elif all(
        any(token in value for token in ("absorbance", "absorption", "吸光度", "吸收")) for value in canonical
    ):
        y_title = "Absorbance (a.u.)"
    else:
        y_title = "IR signal (a.u.)"
    return f"Wavenumber{suffix}", y_title, tuple(warnings)


def _material_series(
    frame: pd.DataFrame,
    columns: list[str],
    plot_mode: str,
) -> tuple[ScientificSeries, ...]:
    base = tuple(ScientificSeries(column, column) for column in columns)
    if plot_mode != "stacked_offset":
        return base
    spans = []
    for column in columns:
        values = frame[column].dropna().to_numpy(dtype=float)
        spans.append(float(np.max(values) - np.min(values)) if values.size else 0.0)
    step = max(spans, default=0.0) * 1.12
    if not math.isfinite(step) or step <= 0.0:
        step = 1.0
    return tuple(replace(series, display_offset=index * step) for index, series in enumerate(base))


def _build_material_spectrum_spec(
    template_id: str,
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    series_columns = _require_series(assignments)
    _require_points(frame, x_column, series_columns)
    mode = plot_mode or "overlay"
    if mode not in {"overlay", "stacked_offset"}:
        raise ScientificWorkflowError(
            "mapping_plot_mode",
            "Select overlay or stacked-offset mode.",
        )
    series = _material_series(frame, series_columns, mode)
    x_title, y_title, title_warnings = _material_axis_titles(
        template_id,
        x_column,
        series_columns,
    )
    warnings = list(title_warnings)
    if mode == "stacked_offset":
        warnings.append("display_vertical_offset_helper_only")
    axis_plan = _axis_plan(
        frame,
        x_column=x_column,
        series=series,
        category=False,
        include_zero_y=False,
        padding_fraction=0.06,
    )
    if template_id in {"nmr", "ftir", "xps_compare"}:
        axis_plan = replace(
            axis_plan,
            x_from=axis_plan.x_to,
            x_to=axis_plan.x_from,
            x_step=(-abs(axis_plan.x_step) if axis_plan.x_step is not None else None),
        )
        warnings.append("descending_spectral_axis")
    style = resolve_adaptive_style(
        template_id=template_id,
        plot_kind=template_id,
        row_count=len(frame),
        series_count=len(series),
    )
    return (
        ScientificPlotSpec(
            plot_kind=template_id,
            plot_mode=mode,
            x_column=x_column,
            category_column=None,
            series=series,
            x_title=x_title,
            y_title=y_title,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform=("vertical_offset_helper_only" if mode == "stacked_offset" else "identity"),
            display_plan=ScientificDisplayPlan(0.0, 0.8, 0.72, figure_style=style),
            axis_plan=axis_plan,
        ),
        tuple(dict.fromkeys(warnings)),
    )


def _build_pl_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    observed_columns = _require_series(assignments)
    fit_columns = [column for column, role in assignments.items() if role == "fit"]
    _require_points(frame, x_column, [*observed_columns, *fit_columns])
    mode = plot_mode or "steady_state"
    if mode not in {"steady_state", "trpl"}:
        raise ScientificWorkflowError("mapping_plot_mode", "Select steady-state PL or TRPL mode.")
    observed = [ScientificSeries(column, column) for column in observed_columns]
    fits = [
        ScientificSeries(
            column,
            column,
            series_role="fit",
            paired_with=_match_fit_series(column, observed_columns),
        )
        for column in fit_columns
    ]
    if mode == "trpl":
        for column in [*observed_columns, *fit_columns]:
            values = frame[column].dropna().to_numpy(dtype=float)
            if values.size and np.any(values <= 0.0):
                raise ScientificWorkflowError(
                    "pl_log_nonpositive",
                    f"TRPL log-axis series {column!r} contains a non-positive value.",
                    column=column,
                )
    x_unit = _physical_unit(x_column)
    unit_suffix = f" ({_format_unit(x_unit)})" if x_unit else ""
    x_title = f"Time after excitation{unit_suffix}" if mode == "trpl" else f"Wavelength{unit_suffix}"
    normalized = all(
        any(token in _canonical(column) for token in ("normalized", "normalised", "归一化"))
        for column in observed_columns
    )
    y_title = "Normalized PL intensity" if normalized else "PL intensity (a.u.)"
    plot_kind = "pl_decay" if mode == "trpl" else "pl_spectrum"
    series = tuple([*observed, *fits])
    style = resolve_adaptive_style(
        template_id="pl",
        plot_kind=plot_kind,
        row_count=len(frame),
        series_count=len(observed),
    )
    marker_size_pt = 6.5 if mode == "trpl" else (0.0 if len(observed) > 1 or len(frame) > 80 else 4.8)
    return (
        ScientificPlotSpec(
            plot_kind=plot_kind,
            plot_mode=mode,
            x_column=x_column,
            category_column=None,
            series=series,
            x_title=x_title,
            y_title=y_title,
            y2_title=None,
            x_scale="linear",
            y_scale="log10" if mode == "trpl" else "linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                marker_size_pt,
                0.8,
                0.72,
                figure_style=style,
            ),
            axis_plan=_axis_plan(
                frame,
                x_column=x_column,
                series=series,
                category=False,
                include_zero_y=False,
                padding_fraction=0.06,
            ),
        ),
        ("user_provided_fit_only",) if fit_columns else (),
    )


def _build_uv_vis_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    x_column = _require_one(assignments, "x")
    signal_columns = _require_series(assignments)
    _require_points(frame, x_column, signal_columns)
    signals = tuple(ScientificSeries(column, column) for column in signal_columns)
    photon_columns = [column for column, role in assignments.items() if role == "photon_energy"]
    tauc_columns = [column for column, role in assignments.items() if role == "tauc"]
    tauc_fit_columns = [column for column, role in assignments.items() if role == "tauc_fit"]
    bandgap_columns = [column for column, role in assignments.items() if role == "bandgap"]
    optional_present = bool(photon_columns or tauc_columns or tauc_fit_columns or bandgap_columns)
    if optional_present and (len(photon_columns) != 1 or len(tauc_columns) != 1):
        raise ScientificWorkflowError(
            "tauc_inset_incomplete",
            "A Tauc inset needs one Photon energy column and one precomputed Tauc value column.",
        )
    if len(tauc_fit_columns) > 1 or len(bandgap_columns) > 1:
        raise ScientificWorkflowError("tauc_inset_conflict", "Tauc fit and band-gap roles are unique.")
    inset_series: tuple[ScientificSeries, ...] = ()
    inset_axis_plan = None
    inset_annotation = None
    warnings: list[str] = []
    if optional_present:
        photon = photon_columns[0]
        tauc = tauc_columns[0]
        _require_points(frame, photon, [tauc, *tauc_fit_columns])
        inset_items = [ScientificSeries(tauc, tauc)]
        if tauc_fit_columns:
            inset_items.append(
                ScientificSeries(
                    tauc_fit_columns[0],
                    tauc_fit_columns[0],
                    series_role="fit",
                    paired_with=tauc,
                )
            )
            warnings.append("user_provided_tauc_fit_only")
        inset_series = tuple(inset_items)
        inset_axis_plan = _axis_plan(
            frame,
            x_column=photon,
            series=inset_series,
            category=False,
            include_zero_y=True,
            padding_fraction=0.06,
        )
        if bandgap_columns:
            _column, bandgap = _constant_role_value(frame, assignments, "bandgap")
            inset_annotation = f"Eg = {bandgap:g} eV"
            warnings.append("bandgap_annotation_from_input")
    canonical_signals = [_canonical(column) for column in signal_columns]
    if all(
        any(token in value for token in ("absorbance", "absorption", "吸光度", "吸收"))
        for value in canonical_signals
    ):
        y_title = "Absorbance (a.u.)"
    elif all(
        any(token in value for token in ("transmittance", "transmission", "透过率", "透射"))
        for value in canonical_signals
    ):
        y_title = "Transmittance (%)"
    else:
        y_title = signal_columns[0] if len(signal_columns) == 1 else "Optical response"
    x_unit = _physical_unit(x_column)
    x_title = f"Wavelength ({_format_unit(x_unit)})" if x_unit else "Wavelength (nm)"
    style = resolve_adaptive_style(
        template_id="uv_vis",
        plot_kind="uv_vis",
        row_count=len(frame),
        series_count=len(signals),
    )
    marker_size_pt = 0.0 if len(signals) > 1 or len(frame) > 80 else 4.8
    return (
        ScientificPlotSpec(
            plot_kind="uv_vis",
            plot_mode="uv_vis_with_tauc" if optional_present else "uv_vis",
            x_column=x_column,
            category_column=None,
            series=signals,
            x_title=x_title,
            y_title=y_title,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(marker_size_pt, 0.8, 0.72, figure_style=style),
            axis_plan=_axis_plan(
                frame,
                x_column=x_column,
                series=signals,
                category=False,
                include_zero_y=False,
                padding_fraction=0.06,
            ),
            inset_x_column=photon_columns[0] if optional_present else None,
            inset_series=inset_series,
            inset_x_title="hν (eV)" if optional_present else None,
            inset_y_title="Tauc value" if optional_present else None,
            inset_axis_plan=inset_axis_plan,
            inset_annotation=inset_annotation,
        ),
        tuple(warnings),
    )


def _build_sankey_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    source = _require_one(assignments, "source")
    target = _require_one(assignments, "target")
    value = _require_one(assignments, "value")
    for column in (source, target):
        blank = _blank_mask(frame[column])
        if bool(blank.any()):
            index = int(np.flatnonzero(blank.to_numpy())[0])
            raise ScientificWorkflowError(
                "sankey_node_empty",
                f"Column {column!r} is empty at data row {index + 2}.",
                column=column,
                row=index + 2,
            )
    values = frame[value]
    invalid = values.isna() | (values <= 0)
    if bool(invalid.any()):
        index = int(np.flatnonzero(invalid.to_numpy())[0])
        raise ScientificWorkflowError(
            "sankey_value_nonpositive",
            f"Sankey weights must be positive at data row {index + 2}.",
            column=value,
            row=index + 2,
        )
    self_link = frame[source].astype(str).str.strip() == frame[target].astype(str).str.strip()
    if bool(self_link.any()):
        index = int(np.flatnonzero(self_link.to_numpy())[0])
        raise ScientificWorkflowError(
            "sankey_self_link",
            f"Sankey source and target are identical at data row {index + 2}.",
            row=index + 2,
        )
    series = (ScientificSeries(value, value),)
    total = float(values.sum())
    axis_plan = ScientificAxisPlan(None, None, None, 0.0, total, None)
    nodes = set(frame[source].astype(str)) | set(frame[target].astype(str))
    warnings: list[str] = []
    if len(nodes) > 30:
        warnings.append("sankey_node_count_high")
    if len(frame) > 60:
        warnings.append("sankey_link_count_high")
    return (
        ScientificPlotSpec(
            plot_kind="sankey",
            plot_mode="default",
            x_column=None,
            category_column=None,
            series=series,
            x_title=source,
            y_title=value,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                7.0,
                0.8,
                0.72,
                figure_style=resolve_adaptive_style(
                    template_id="sankey",
                    plot_kind="sankey",
                    row_count=len(frame),
                    series_count=1,
                    max_label_length=max(
                        max((len(str(value)) for value in frame[source]), default=0),
                        max((len(str(value)) for value in frame[target]), default=0),
                    ),
                ),
            ),
            axis_plan=axis_plan,
            source_column=source,
            target_column=target,
        ),
        tuple(warnings),
    )


def _normalize_circular_network_sign(
    value: object,
    *,
    column: str,
    row: int,
) -> tuple[str, bool]:
    if pd.isna(value) or str(value).strip() == "":
        return "neutral", True
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    compact = re.sub(r"\s+", "", text).replace("−", "-")
    positive = {
        "positive",
        "pos",
        "plus",
        "+",
        "+1",
        "1",
        ">0",
        "p>0",
        "正",
        "正向",
        "正相关",
        "正效应",
        "促进",
        "增加",
        "↑",
    }
    negative = {
        "negative",
        "neg",
        "minus",
        "-",
        "-1",
        "<0",
        "p<0",
        "负",
        "负向",
        "负相关",
        "负效应",
        "抑制",
        "减少",
        "↓",
    }
    neutral = {
        "neutral",
        "none",
        "zero",
        "0",
        "unknown",
        "na",
        "n/a",
        "中性",
        "无方向",
        "无显著关系",
        "未知",
        "不显著",
    }
    if compact in positive:
        return "positive", False
    if compact in negative:
        return "negative", False
    if compact in neutral:
        return "neutral", False
    raise ScientificWorkflowError(
        "circular_network_sign_unknown",
        (
            f"Sign column {column!r} has an unsupported value {value!r} at "
            f"data row {row}. Use positive/negative/neutral, +/−, p>0/p<0, "
            "or the corresponding Chinese wording."
        ),
        column=column,
        row=row,
    )


def _build_circular_network_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    panel_column = _require_one(assignments, "panel")
    source_column = _require_one(assignments, "source")
    target_column = _require_one(assignments, "target")
    weight_column = _require_one(assignments, "value")

    def optional_role(role: str) -> str | None:
        matches = [column for column, assigned in assignments.items() if assigned == role]
        return matches[0] if matches else None

    sign_column = optional_role("sign")
    source_group_column = optional_role("source_group")
    target_group_column = optional_role("target_group")
    edge_label_column = optional_role("edge_label")
    if (source_group_column is None) != (target_group_column is None):
        raise ScientificWorkflowError(
            "circular_network_group_pair_incomplete",
            "SourceGroup and TargetGroup must either both be mapped or both be omitted.",
        )

    text_columns = (panel_column, source_column, target_column)
    for column in text_columns:
        blank = _blank_mask(frame[column])
        if bool(blank.any()):
            index = int(np.flatnonzero(blank.to_numpy())[0])
            raise ScientificWorkflowError(
                "circular_network_text_empty",
                f"Column {column!r} is empty at data row {index + 2}.",
                column=column,
                row=index + 2,
            )
        for index, value in enumerate(frame[column]):
            text = str(value)
            if text != text.strip():
                raise ScientificWorkflowError(
                    "circular_network_text_whitespace",
                    (
                        f"Column {column!r} contains leading or trailing whitespace "
                        f"at data row {index + 2}."
                    ),
                    column=column,
                    row=index + 2,
                )

    weight_values = frame[weight_column].to_numpy(dtype=float, copy=True)
    invalid_weight = ~np.isfinite(weight_values) | (weight_values <= 0.0)
    if bool(np.any(invalid_weight)):
        index = int(np.flatnonzero(invalid_weight)[0])
        raise ScientificWorkflowError(
            "circular_network_weight_invalid",
            f"Circular-network weights must be finite and greater than zero at data row {index + 2}.",
            column=weight_column,
            row=index + 2,
        )

    panels: list[str] = []
    nodes: list[str] = []
    seen_panels: set[str] = set()
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    edges_per_panel: dict[str, int] = {}
    node_group_map: dict[str, str] = {}
    records: list[CircularNetworkEdgeRecord] = []
    blank_sign_seen = False

    for index, row_values in frame.iterrows():
        panel = str(row_values[panel_column])
        source = str(row_values[source_column])
        target = str(row_values[target_column])
        data_row = int(index) + 2 if isinstance(index, (int, np.integer)) else len(records) + 2
        if panel not in seen_panels:
            seen_panels.add(panel)
            panels.append(panel)
        for node in (source, target):
            if node not in seen_nodes:
                seen_nodes.add(node)
                nodes.append(node)
        if source == target:
            raise ScientificWorkflowError(
                "circular_network_self_link",
                f"Source and target are identical at data row {data_row}.",
                row=data_row,
            )
        edge_key = (panel, source, target)
        if edge_key in seen_edges:
            raise ScientificWorkflowError(
                "circular_network_duplicate_edge",
                (
                    f"Duplicate directed edge {source!r} → {target!r} occurs in "
                    f"panel {panel!r} at data row {data_row}."
                ),
                row=data_row,
            )
        seen_edges.add(edge_key)
        edges_per_panel[panel] = edges_per_panel.get(panel, 0) + 1

        sign = "neutral"
        if sign_column is not None:
            sign, was_blank = _normalize_circular_network_sign(
                row_values[sign_column],
                column=sign_column,
                row=data_row,
            )
            blank_sign_seen = blank_sign_seen or was_blank

        if source_group_column is not None and target_group_column is not None:
            for node, group_column in (
                (source, source_group_column),
                (target, target_group_column),
            ):
                group_value = row_values[group_column]
                if pd.isna(group_value) or str(group_value).strip() == "":
                    raise ScientificWorkflowError(
                        "circular_network_group_empty",
                        f"Node group is empty in column {group_column!r} at data row {data_row}.",
                        column=group_column,
                        row=data_row,
                    )
                group = str(group_value)
                if group != group.strip():
                    raise ScientificWorkflowError(
                        "circular_network_group_whitespace",
                        (
                            f"Node group in column {group_column!r} contains leading "
                            f"or trailing whitespace at data row {data_row}."
                        ),
                        column=group_column,
                        row=data_row,
                    )
                existing_group = node_group_map.get(node)
                if existing_group is not None and existing_group != group:
                    raise ScientificWorkflowError(
                        "circular_network_node_group_conflict",
                        (
                            f"Node {node!r} is assigned to both {existing_group!r} "
                            f"and {group!r}; every node must keep one group."
                        ),
                        column=group_column,
                        row=data_row,
                    )
                node_group_map[node] = group

        label = ""
        if edge_label_column is not None:
            label_value = row_values[edge_label_column]
            label = "" if pd.isna(label_value) else str(label_value)
        records.append(
            CircularNetworkEdgeRecord(
                panel=panel,
                source=source,
                target=target,
                weight=float(row_values[weight_column]),
                sign=sign,
                label=label,
            )
        )

    if not 1 <= len(panels) <= 4:
        raise ScientificWorkflowError(
            "circular_network_panel_count",
            f"Circular network supports 1–4 panels; this table contains {len(panels)}.",
        )
    if len(nodes) > 24:
        raise ScientificWorkflowError(
            "circular_network_node_count",
            f"Circular network supports at most 24 global nodes; this table contains {len(nodes)}.",
        )
    group_order = tuple(dict.fromkeys(node_group_map.values()))
    if len(group_order) > MAX_NODE_GROUP_COUNT:
        raise ScientificWorkflowError(
            "circular_network_node_group_count",
            (
                f"Circular network supports at most {MAX_NODE_GROUP_COUNT} node groups "
                f"with independent colour encoding; this table contains {len(group_order)}."
            ),
        )
    excessive_panel = next(
        ((panel, count) for panel, count in edges_per_panel.items() if count > 60),
        None,
    )
    if excessive_panel is not None:
        panel, count = excessive_panel
        raise ScientificWorkflowError(
            "circular_network_edge_count",
            f"Panel {panel!r} contains {count} edges; the per-panel limit is 60.",
        )

    layout = resolve_circular_network_layout(
        panel_order=panels,
        node_order=nodes,
        edges=records,
    )
    max_label_length = max(
        (len(value) for value in (*panels, *nodes, *node_group_map.values())),
        default=0,
    )
    style = resolve_adaptive_style(
        template_id="circular_network",
        plot_kind="circular_network",
        row_count=len(frame),
        series_count=len(panels),
        max_label_length=max_label_length,
    )
    warnings: list[str] = []
    if sign_column is None:
        warnings.append("circular_network_sign_defaults_neutral")
    elif blank_sign_seen:
        warnings.append("circular_network_blank_sign_defaults_neutral")
    if edge_label_column is not None and any(
        not panel.edge_labels_visible and any(edge.label for edge in panel.edges)
        for panel in layout.panels
    ):
        warnings.append("circular_network_edge_labels_hidden_dense")
    series = (ScientificSeries(weight_column, weight_column),)
    return (
        ScientificPlotSpec(
            plot_kind="circular_network",
            plot_mode="temporal_directed_weighted",
            x_column=None,
            category_column=None,
            series=series,
            x_title="Directed network",
            y_title=weight_column,
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                15.0,
                0.8,
                0.72,
                figure_style=style,
            ),
            axis_plan=ScientificAxisPlan(-1.25, 1.25, None, -1.25, 1.25, None),
            source_column=source_column,
            target_column=target_column,
            panel_column=panel_column,
            weight_column=weight_column,
            sign_column=sign_column,
            source_group_column=source_group_column,
            target_group_column=target_group_column,
            edge_label_column=edge_label_column,
            node_groups=tuple(
                (node, node_group_map[node])
                for node in nodes
                if node in node_group_map
            ),
            network_layout=layout,
            category_order=tuple(nodes),
            group_order=group_order,
        ),
        tuple(warnings),
    )


def _build_eis_spec(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    warnings: list[str] = []
    if plot_mode == "nyquist":
        x_column = _require_one(assignments, "z_real")
        y_column = _require_one(assignments, "z_imag")
        transform, sign_warnings = _eis_imag_transform(frame, y_column)
        warnings.extend(sign_warnings)
        series = (ScientificSeries(y_column, y_column, transform=transform),)
        _require_points(frame, x_column, [y_column])
        x_title = _eis_axis_title("Z'", x_column)
        y_title = _eis_axis_title("−Z''", y_column)
        return (
            ScientificPlotSpec(
                plot_kind="nyquist",
                plot_mode="nyquist",
                x_column=x_column,
                category_column=None,
                series=series,
                x_title=x_title,
                y_title=y_title,
                y2_title=None,
                x_scale="linear",
                y_scale="linear",
                display_transform="negate_imaginary" if transform == "negate" else "identity",
                display_plan=ScientificDisplayPlan(
                    7.0,
                    0.8,
                    0.72,
                    figure_style=resolve_adaptive_style(
                        template_id="eis",
                        plot_kind="nyquist",
                        row_count=len(frame),
                        series_count=1,
                    ),
                ),
                axis_plan=_axis_plan(
                    frame,
                    x_column=x_column,
                    series=series,
                    category=False,
                    include_zero_y=True,
                    include_zero_x=True,
                ),
            ),
            tuple(warnings),
        )

    frequency = _require_one(assignments, "frequency")
    magnitude = [column for column, role in assignments.items() if role == "magnitude"]
    phase = [column for column, role in assignments.items() if role == "phase"]
    if not magnitude and not phase:
        raise ScientificWorkflowError(
            "bode_series_missing", "Bode EIS needs an impedance magnitude or phase column."
        )
    frequency_values = frame[frequency]
    nonpositive = frequency_values.notna() & (frequency_values <= 0)
    if bool(nonpositive.any()):
        index = int(np.flatnonzero(nonpositive.to_numpy())[0])
        raise ScientificWorkflowError(
            "log_axis_nonpositive",
            f"Log-frequency column {frequency!r} contains a nonpositive value at data row {index + 2}.",
            column=frequency,
            row=index + 2,
        )
    items: list[ScientificSeries] = []
    frequency_title = _eis_axis_title("Frequency", frequency)
    magnitude_title = _eis_axis_title("|Z|", magnitude[0]) if magnitude else None
    phase_title = _eis_axis_title("Phase", phase[0]) if phase else None
    if magnitude:
        magnitude_values = frame[magnitude[0]]
        nonpositive_magnitude = magnitude_values.notna() & (magnitude_values <= 0)
        if bool(nonpositive_magnitude.any()):
            index = int(np.flatnonzero(nonpositive_magnitude.to_numpy())[0])
            raise ScientificWorkflowError(
                "log_axis_nonpositive",
                f"Log-magnitude column {magnitude[0]!r} contains a nonpositive "
                f"value at data row {index + 2}.",
                column=magnitude[0],
                row=index + 2,
            )
        items.append(ScientificSeries(magnitude[0], magnitude_title or "|Z|", axis="left"))
    if phase:
        items.append(
            ScientificSeries(
                phase[0],
                phase_title or "Phase",
                axis="right" if magnitude else "left",
            )
        )
    series = tuple(items)
    _require_points(frame, frequency, [item.source_column for item in series])
    return (
        ScientificPlotSpec(
            plot_kind="bode_dual" if magnitude and phase else "bode",
            plot_mode="bode",
            x_column=frequency,
            category_column=None,
            series=series,
            x_title=frequency_title,
            y_title=magnitude_title or phase_title or "Response",
            y2_title=phase_title if magnitude and phase else None,
            x_scale="log10",
            y_scale="log10" if magnitude else "linear",
            display_transform="identity",
            display_plan=ScientificDisplayPlan(
                7.0,
                0.8,
                0.72,
                figure_style=resolve_adaptive_style(
                    template_id="eis",
                    plot_kind="bode_dual" if magnitude and phase else "bode",
                    row_count=len(frame),
                    series_count=len(series),
                ),
            ),
            axis_plan=_axis_plan(
                frame,
                x_column=frequency,
                series=series,
                category=False,
                include_zero_y=False,
            ),
        ),
        tuple(warnings),
    )


def _eis_axis_title(symbol: str, source_column: str) -> str:
    match = re.search(r"([\(\[].+?[\)\]])\s*$", source_column)
    if not match:
        return symbol
    unit = match.group(1)[1:-1].strip()
    formatted = _format_unit(unit)
    if symbol == "Phase" and _canonical(unit) in {"deg", "degree", "degrees"}:
        formatted = "°"
    return f"{symbol} ({formatted})" if unit else symbol


def _build_plot_spec(
    template_id: str,
    frame: pd.DataFrame,
    assignments: dict[str, str],
    plot_mode: str,
    *,
    source_profile: str | None = None,
) -> tuple[ScientificPlotSpec, tuple[str, ...]]:
    if template_id == "xrd":
        return _build_xrd_spec(
            frame,
            assignments,
            plot_mode,
            source_profile or "ordinary_xrd",
        )
    if template_id == "trajectory3d":
        return _build_trajectory3d_spec(frame, assignments)
    if template_id == "density_ridgeline3d":
        return _build_density_ridgeline3d_spec(frame, assignments)
    if template_id == "eis":
        return _build_eis_spec(frame, assignments, plot_mode)
    if template_id == "sankey":
        return _build_sankey_spec(frame, assignments)
    if template_id == "circular_network":
        return _build_circular_network_spec(frame, assignments)
    if template_id in {"raw_summary", "violin", "histogram", "raincloud"}:
        return _build_raw_distribution_spec(template_id, frame, assignments)
    if template_id == "shap_summary":
        return _build_shap_summary_spec(frame, assignments, plot_mode)
    if template_id == "bubble":
        return _build_bubble_spec(frame, assignments)
    if template_id == "forest":
        return _build_forest_spec(frame, assignments)
    if template_id == "diagnostic_curve":
        return _build_diagnostic_curve_spec(frame, assignments, plot_mode)
    if template_id == "calibration_curve":
        return _build_calibration_curve_spec(frame, assignments)
    if template_id == "decision_curve":
        return _build_decision_curve_spec(frame, assignments)
    if template_id == "bland_altman":
        return _build_bland_altman_spec(frame, assignments)
    if template_id == "grouped_box":
        return _build_grouped_box_spec(frame, assignments)
    if template_id in {"dsc", "nmr", "ftir", "xps_compare"}:
        return _build_material_spectrum_spec(template_id, frame, assignments, plot_mode)
    if template_id == "pl":
        return _build_pl_spec(frame, assignments, plot_mode)
    if template_id == "uv_vis":
        return _build_uv_vis_spec(frame, assignments)
    if template_id in {*_CATEGORY_TABLE_TEMPLATE_IDS, "line_error"}:
        return _build_error_spec(template_id, frame, assignments)
    return _build_line_spec(template_id, frame, assignments)


def _automatic_mapping(loaded: LoadedTable, template_id: str) -> _AutoMapping:
    if template_id == "xrd":
        return _automatic_xrd_mapping(loaded)
    if template_id == "trajectory3d":
        return _automatic_trajectory3d_mapping(loaded)
    if template_id == "density_ridgeline3d":
        return _automatic_density_ridgeline3d_mapping(loaded)
    if template_id == "eis":
        return _automatic_eis_mapping(loaded)
    if template_id == "sankey":
        return _automatic_sankey_mapping(loaded)
    if template_id == "circular_network":
        return _automatic_circular_network_mapping(loaded)
    if template_id in {"raw_summary", "violin", "histogram", "raincloud"}:
        return _automatic_raw_distribution_mapping(loaded, template_id)
    if template_id == "shap_summary":
        return _automatic_shap_summary_mapping(loaded)
    if template_id == "bubble":
        return _automatic_bubble_mapping(loaded)
    if template_id == "forest":
        return _automatic_forest_mapping(loaded)
    if template_id == "diagnostic_curve":
        return _automatic_diagnostic_mapping(loaded)
    if template_id == "calibration_curve":
        return _automatic_calibration_mapping(loaded)
    if template_id == "decision_curve":
        return _automatic_decision_mapping(loaded)
    if template_id == "bland_altman":
        return _automatic_bland_altman_mapping(loaded)
    if template_id == "grouped_box":
        return _automatic_raw_distribution_mapping(loaded, template_id)
    if template_id in {"dsc", "nmr", "ftir"}:
        return _automatic_material_mapping(loaded, template_id)
    if template_id == "xps_compare":
        return _automatic_xps_compare_mapping(loaded)
    if template_id == "pl":
        return _automatic_pl_mapping(loaded)
    if template_id == "uv_vis":
        return _automatic_uv_vis_mapping(loaded)
    if template_id in {*_CATEGORY_TABLE_TEMPLATE_IDS, "line_error"}:
        return _automatic_error_mapping(loaded, template_id)
    return _automatic_line_mapping(loaded, template_id)


def _load(path: str | Path) -> LoadedTable:
    try:
        return load_table(path)
    except DataLoadError as exc:
        raise ScientificWorkflowError(
            exc.code,
            str(exc),
            column=exc.column,
            row=exc.row,
        ) from exc


def prepare_scientific(
    path: str | Path,
    template_id: str,
    *,
    column_mapping: ScientificColumnMapping | None = None,
) -> ScientificPreparation:
    """Audit a source table and freeze a shared non-XPS plot plan."""
    if template_id not in SUPPORTED_SCIENTIFIC_TEMPLATE_IDS:
        raise ScientificWorkflowError("template_unknown", f"Unknown scientific template: {template_id}")
    loaded = _load(path)
    automatic = _automatic_mapping(loaded, template_id)
    mapping_confirmed = column_mapping is not None
    if column_mapping is None:
        assignments = automatic.assignments
        plot_mode = automatic.plot_mode
    else:
        assignments, plot_mode = _validate_assignment_shape(loaded, template_id, column_mapping)
    frame = _coerced_selected_frame(loaded, assignments)
    source_profile = detect_xrd_source_profile(loaded) if template_id == "xrd" else None
    spec, build_warnings = _build_plot_spec(
        template_id,
        frame,
        assignments,
        plot_mode,
        source_profile=source_profile,
    )

    warnings = list(automatic.warnings if column_mapping is None else ())
    warnings.extend(build_warnings)
    if loaded.ignored_empty_rows:
        warnings.append("empty_rows_ignored")
    warnings = list(dict.fromkeys(warnings))
    confirmation_reasons = automatic.reasons if column_mapping is None else ()
    requires_confirmation = bool(confirmation_reasons) and not mapping_confirmed
    confidence = 1.0 if mapping_confirmed else automatic.confidence
    digest_payload = {
        "template_id": template_id,
        "source_sha256": loaded.source_sha256,
        "source_columns": loaded.columns,
        "assignments": [(column, assignments[column]) for column in loaded.columns],
        "plot_spec": asdict(spec),
        "mapping_confirmed": mapping_confirmed,
    }
    plan_digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return ScientificPreparation(
        template_id=template_id,
        source_path=loaded.source_path,
        source_sha256=loaded.source_sha256,
        source_size_bytes=loaded.source_size_bytes,
        source_format=loaded.source_format,
        source_sheet=loaded.sheet_name,
        source_columns=loaded.columns,
        row_count=len(loaded.frame),
        ignored_empty_rows=loaded.ignored_empty_rows,
        assignments=tuple((column, assignments[column]) for column in loaded.columns),
        plot_spec=spec,
        confidence=confidence,
        requires_confirmation=requires_confirmation,
        confirmation_reasons=tuple(confirmation_reasons),
        warnings=tuple(warnings),
        mapping_confirmed=mapping_confirmed,
        plan_digest=plan_digest,
    )


def load_scientific_frame(
    path: str | Path,
    preparation: ScientificPreparation,
) -> pd.DataFrame:
    """Reload and verify the exact source described by a preparation."""
    loaded = _load(path)
    if loaded.source_sha256 != preparation.source_sha256:
        raise ScientificWorkflowError(
            "analysis_changed",
            "The scientific data changed after preview. Refresh the preview and run again.",
        )
    if loaded.columns != preparation.source_columns:
        raise ScientificWorkflowError(
            "source_columns_changed",
            "The scientific data columns changed after preview.",
        )
    assignments = dict(preparation.assignments)
    return _coerced_selected_frame(loaded, assignments)


def series_values(frame: pd.DataFrame, series: ScientificSeries) -> np.ndarray:
    """Return display values without modifying the source frame."""
    values = frame[series.source_column].to_numpy(dtype=float, copy=True)
    if series.transform == "negate":
        values = -values
    if series.display_offset:
        values = values + series.display_offset
    return values


def evidence_jitter_offsets(count: int, series_index: int = 0) -> np.ndarray:
    """Return stable, decorrelated offsets shared by preview and Origin.

    Observations may arrive sorted by value. A monotone offset sequence then
    creates a misleading diagonal pattern, so evenly spaced offsets are
    permuted with a frozen seed instead of adding non-repeatable random noise.
    """
    if count <= 0:
        return np.array([], dtype=float)
    if count == 1:
        return np.zeros(1, dtype=float)
    offsets = np.linspace(-0.17, 0.17, count, dtype=float)
    generator = np.random.default_rng(20_240_718 + count * 101 + series_index * 4_099)
    return generator.permutation(offsets)


def shap_beeswarm_offsets(
    values: object,
    *,
    max_offset: float = 0.30,
) -> np.ndarray:
    """Return deterministic vertical offsets for supplied SHAP values.

    This is a display-only collision reduction rule.  It preserves every X
    value and uses no random state, density fitting, feature ranking, or model
    computation.  Points are assigned to fixed value bins and stacked
    symmetrically around the feature row.
    """
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("SHAP beeswarm values must be one-dimensional.")
    if array.size == 0:
        return np.array([], dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError("SHAP beeswarm values must be finite.")
    if max_offset <= 0.0:
        raise ValueError("SHAP beeswarm max_offset must be positive.")

    lower = float(np.min(array))
    upper = float(np.max(array))
    if math.isclose(lower, upper):
        bin_index = np.zeros(array.size, dtype=int)
    else:
        bin_count = max(6, min(24, int(math.ceil(math.sqrt(array.size) * 2.0))))
        scaled = (array - lower) / (upper - lower)
        bin_index = np.minimum((scaled * bin_count).astype(int), bin_count - 1)

    offsets = np.zeros(array.size, dtype=float)
    for current_bin in np.unique(bin_index):
        members = np.flatnonzero(bin_index == current_bin)
        members = members[np.lexsort((members, array[members]))]
        count = members.size
        if count <= 1:
            continue
        if count % 2:
            levels = [0.0]
            for level in range(1, count // 2 + 1):
                levels.extend((float(level), float(-level)))
        else:
            levels = []
            for level in range(count // 2):
                value = level + 0.5
                levels.extend((float(value), float(-value)))
        largest = max(abs(value) for value in levels)
        spacing = min(0.075, max_offset / largest) if largest else 0.0
        offsets[members] = np.asarray(levels[:count], dtype=float) * spacing
    return offsets


def shap_within_feature_color_values(
    frame: pd.DataFrame,
    feature_column: str,
    value_column: str,
) -> np.ndarray:
    """Normalize feature values within each feature for display color only."""
    features = np.asarray([str(value).strip() for value in frame[feature_column]], dtype=object)
    values = frame[value_column].to_numpy(dtype=float, copy=True)
    if values.size != features.size or not np.all(np.isfinite(values)):
        raise ValueError("SHAP color values must align with finite feature values.")
    normalized = np.empty(values.size, dtype=float)
    for feature in dict.fromkeys(features.tolist()):
        mask = features == feature
        subset = values[mask]
        lower = float(np.min(subset))
        upper = float(np.max(subset))
        if math.isclose(lower, upper):
            normalized[mask] = 0.5
        else:
            normalized[mask] = (subset - lower) / (upper - lower)
    return normalized


__all__ = [
    "SUPPORTED_SCIENTIFIC_TEMPLATE_IDS",
    "ScientificAxisPlan",
    "ScientificColumnMapping",
    "ScientificDisplayPlan",
    "ScientificPlotSpec",
    "ScientificPreparation",
    "ScientificSeries",
    "ScientificWorkflowError",
    "evidence_jitter_offsets",
    "shap_beeswarm_offsets",
    "shap_within_feature_color_values",
    "load_scientific_frame",
    "mapping_context_options",
    "prepare_scientific",
    "role_label",
    "role_options",
    "series_values",
]
