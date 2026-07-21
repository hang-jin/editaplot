"""Deterministic inspection, recommendation, planning, and verification for EditaPlot."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover - Python 3.10+ is required, kept for a useful doctor error
    try:
        import importlib_metadata  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover - lets doctor explain unsupported legacy Python
        importlib_metadata = None  # type: ignore[assignment]


PLAN_VERSION = "1.0"
MEDICAL_PANEL_PLAN_VERSION = "1.0"
AUTO_SCORE_THRESHOLD = 0.84
AUTO_MARGIN_THRESHOLD = 0.13
MANAGED_ENV_DIRECTORY = ".editaplot-venv"
RUNTIME_DEPENDENCIES = (
    ("numpy", "numpy==1.26.4"),
    ("pandas", "pandas==2.3.3"),
    ("yaml", "PyYAML==6.0.3"),
    ("jsonschema", "jsonschema==4.26.0"),
    ("matplotlib", "matplotlib==3.10.9"),
    ("originpro", "originpro==1.1.15"),
    ("openpyxl", "openpyxl==3.1.5"),
    ("xlrd", "xlrd==2.0.2"),
    ("PIL", "pillow==12.3.0"),
)
VERIFIED_TEMPLATE_IDS = frozenset(
    {
        "xps",
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
        "pl",
        "uv_vis",
        "trajectory3d",
    }
)


class EditaPlotError(RuntimeError):
    """Stable, JSON-friendly EditaPlot failure."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": str(self), **self.details}}


def _canonical(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fffμθ]+", "", text)


def _trajectory3d_semantic_axis_header(column: str) -> bool:
    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]\s*$", column)
    if match is None or not match.group(1).strip():
        return False
    meaning = column[: match.start()].strip(" _-/")
    return bool(meaning) and _canonical(meaning) not in {
        "x",
        "y",
        "z",
        "index",
        "condition",
        "value",
        "variable",
        "序号",
        "条件",
        "数值",
    }


def _explicit_negative_zimag_header(column: str) -> bool:
    text = unicodedata.normalize("NFKC", column).casefold().replace("−", "-")
    compact = re.sub(r"\s+", "", text)
    return (
        compact.startswith("-z")
        or "negativezimag" in compact
        or "minuszimag" in compact
        or "负阻抗虚部" in compact
        or "负虚部" in compact
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _engine_marker(path: Path) -> bool:
    return (
        (path / "src" / "origin_sciplot" / "__init__.py").is_file()
        and (path / "templates").is_dir()
        and (path / "src" / "origin_sciplot" / "workers" / "run_template_worker.py").is_file()
    )


def resolve_engine_home(value: str | Path | None = None) -> Path:
    """Resolve an unpacked EditaPlot engine without a private hard-coded path."""
    candidates: list[Path] = []
    if value:
        candidates.append(Path(value))
    env_value = os.environ.get("EDITAPLOT_ENGINE_HOME")
    if env_value:
        candidates.append(Path(env_value))

    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for parent in (start, *start.parents):
            candidates.extend((parent, parent / "xps-origin-template-mvp", parent / "runtime"))

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _engine_marker(resolved):
            return resolved
    raise EditaPlotError(
        "engine_not_found",
        "EditaPlot could not locate the rendering engine. Pass --engine-home or set EDITAPLOT_ENGINE_HOME.",
    )


def bootstrap_engine(value: str | Path | None = None) -> Path:
    root = resolve_engine_home(value)
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return root


_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "xps_energy": ("bindingenergy", "kineticenergy", "结合能", "动能"),
    "raw": ("raw", "counts", "intensity", "强度", "计数", "原始"),
    "background": ("background", "baseline", "背景", "基线"),
    "envelope": ("envelope", "fitsum", "fittotal", "拟合包络", "总拟合"),
    "residual": ("residual", "resid", "difference", "残差", "差值"),
    "xrd_angle": ("2theta", "twotheta", "2θ", "衍射角"),
    "absorption": ("absorption", "mu", "μ", "xanes", "exafs", "吸收"),
    "wavelength": ("wavelength", "lambda", "波长"),
    "uv_signal": ("absorbance", "transmittance", "transmission", "吸光度", "透过率", "透射率"),
    "pl_signal": (
        "plintensity",
        "normalizedpl",
        "plsignal",
        "plcounts",
        "photoluminescence",
        "emissionintensity",
        "发光强度",
        "荧光强度",
        "光致发光",
    ),
    "time": ("time", "decaytime", "时间", "衰减时间"),
    "fit": ("fit", "fitted", "fitting", "拟合"),
    "photon_energy": ("photonenergy", "hnu", "hv", "光子能量"),
    "tauc": ("taucvalue", "tauc", "tauc值"),
    "bandgap": ("bandgap", "energygap", "eg", "带隙", "禁带宽度"),
    "frequency": ("frequency", "freq", "hz", "频率"),
    "z_real": ("zreal", "rez", "zre", "阻抗实部"),
    "z_imag": ("zimag", "imz", "zim", "阻抗虚部"),
    "phase": ("phase", "相位", "相位角"),
    "potential": ("potential", "voltage", "电位", "电压"),
    "current": ("current", "currentdensity", "电流", "电流密度"),
    "category": ("category", "group", "sample", "label", "类别", "组别", "样品", "标签"),
    "metric": ("metric", "indicator", "dimension", "指标", "维度"),
    "matrix_row": ("dataset", "cohort", "数据集", "队列"),
    "error": ("sd", "sem", "se", "stderr", "error", "标准差", "标准误", "误差"),
    "source": ("source", "from", "来源", "起点", "源"),
    "target": ("target", "to", "目标", "终点"),
    "value": ("value", "weight", "flow", "数值", "权重", "流量"),
    "size": (
        "size",
        "magnitude",
        "abundance",
        "count",
        "samplesize",
        "大小",
        "规模",
        "丰度",
        "数量",
        "样本量",
    ),
    "estimate": ("estimate", "effect", "difference", "coefficient", "估计", "效应", "差异", "系数"),
    "lower": ("cilow", "lowerci", "lower", "lcl", "置信下限", "下限"),
    "upper": ("cihigh", "upperci", "upper", "ucl", "置信上限", "上限"),
    "reference": ("reference", "null", "baseline", "参考值", "零效应", "基准"),
    "diagnostic_x": ("fpr", "falsepositiverate", "recall", "sensitivity", "假阳性率", "召回率", "敏感度"),
    "prevalence": ("prevalence", "患病率", "阳性率基线"),
    "predicted_probability": ("predictedprobability", "predictedrisk", "预测概率", "预测风险"),
    "observed_fraction": ("observedfraction", "eventrate", "observedrisk", "观察比例", "实际发生率"),
    "bin_count": ("bincount", "分箱样本数", "频数"),
    "threshold": ("threshold", "thresholdprobability", "阈值", "阈值概率"),
    "treat_all": ("treatall", "全部干预", "全部治疗"),
    "treat_none": ("treatnone", "不干预", "不治疗"),
    "actual_class": ("actualclass", "trueclass", "实际类别", "真实类别"),
    "pair_mean": ("pairmean", "mean", "average", "配对均值", "均值", "平均值"),
    "difference": ("difference", "methoddifference", "差值", "方法差"),
    "bias": ("bias", "meandifference", "偏倚", "平均差"),
    "loa_lower": ("lowerloa", "lowerlimitofagreement", "一致性下限"),
    "loa_upper": ("upperloa", "upperlimitofagreement", "一致性上限"),
    "visit": ("visit", "conditionindex", "访视", "条件序号"),
    "feature": ("feature", "featurename", "variable", "predictor", "特征", "特征名", "变量", "预测因子"),
    "shap_value": ("shapvalue", "shap", "shap值", "特征贡献", "贡献值"),
    "feature_value": ("featurevalue", "rawfeaturevalue", "特征值", "原始特征值"),
    "series_id": ("series", "seriesid", "sampleid", "conditionname", "系列", "样品编号", "组别"),
}


def _semantic_tags(column: str) -> list[str]:
    canonical = _canonical(column)
    tags: list[str] = []
    for tag, aliases in _SEMANTIC_ALIASES.items():
        if any(_canonical(alias) in canonical for alias in aliases):
            tags.append(tag)
    return tags


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def inspect_data(path: str | Path, *, engine_home: str | Path | None = None) -> dict[str, Any]:
    """Read a scientific table through the engine's immutable loader and profile its shape."""
    root = bootstrap_engine(engine_home)
    try:
        import numpy as np
        import pandas as pd
        from origin_sciplot.data_loader import DataLoadError, load_table
    except Exception as exc:  # noqa: BLE001
        raise EditaPlotError("engine_import_failed", f"Could not import the engine: {exc}") from exc

    try:
        loaded = load_table(path)
    except DataLoadError as exc:
        raise EditaPlotError(exc.code, str(exc), column=exc.column, row=exc.row) from exc

    profiles: list[dict[str, Any]] = []
    numeric_columns: list[str] = []
    categorical_columns: list[str] = []
    all_nonnegative = True
    max_label_length = 0
    first_category_unique = 0

    for index, column in enumerate(loaded.columns):
        series = loaded.frame[column]
        as_text = series.astype("string").str.strip()
        nonempty_mask = as_text.notna() & as_text.ne("")
        nonempty_count = int(nonempty_mask.sum())
        missing_count = int(len(series) - nonempty_count)
        numeric = pd.to_numeric(series.where(nonempty_mask), errors="coerce")
        numeric_array = numeric.to_numpy(dtype=float, na_value=np.nan)
        finite_mask = np.isfinite(numeric_array)
        numeric_count = int(finite_mask.sum())
        numeric_ratio = numeric_count / nonempty_count if nonempty_count else 0.0
        kind = "numeric" if nonempty_count and numeric_ratio >= 0.8 else "categorical"
        tags = _semantic_tags(column)
        profile: dict[str, Any] = {
            "name": column,
            "index": index,
            "kind": kind,
            "semantic_tags": tags,
            "nonempty_count": nonempty_count,
            "missing_count": missing_count,
            "numeric_ratio": round(numeric_ratio, 4),
            "unique_count": int(as_text[nonempty_mask].nunique(dropna=True)),
        }
        if kind == "numeric":
            numeric_columns.append(column)
            values = numeric_array[finite_mask]
            if values.size:
                diffs = np.diff(values)
                nonzero_signs = np.sign(diffs[np.abs(diffs) > 1e-12])
                direction_changes = (
                    int(np.sum(nonzero_signs[1:] != nonzero_signs[:-1])) if nonzero_signs.size > 1 else 0
                )
                minimum = float(np.min(values))
                maximum = float(np.max(values))
                all_nonnegative = all_nonnegative and minimum >= 0
                profile.update(
                    {
                        "minimum": minimum,
                        "maximum": maximum,
                        "monotonic_increasing": bool(np.all(diffs >= 0)),
                        "monotonic_decreasing": bool(np.all(diffs <= 0)),
                        "direction_changes": direction_changes,
                    }
                )
        else:
            categorical_columns.append(column)
            lengths = as_text[nonempty_mask].str.len()
            longest = int(lengths.max()) if not lengths.empty else 0
            max_label_length = max(max_label_length, longest)
            profile["maximum_label_length"] = longest
            if index == 0:
                first_category_unique = profile["unique_count"]
        profiles.append(profile)

    tags = {tag for profile in profiles for tag in profile["semantic_tags"]}
    layouts: list[str] = []
    if {"source", "target", "value"}.issubset(tags):
        layouts.append("edge_list")
    if profiles and profiles[0]["kind"] == "categorical" and numeric_columns:
        layouts.append("category_wide")
        if len(numeric_columns) >= 2:
            layouts.append("matrix_candidate")
    if len(numeric_columns) >= 2:
        layouts.append("numeric_xy")
    if "error" in tags:
        layouts.append("error_wide")
    if numeric_columns and not categorical_columns:
        layouts.append("numeric_wide")
        if len(numeric_columns) == 1:
            layouts.append("numeric_univariate")
    grouped_headers = [
        profile["name"] for profile in profiles if "|" in str(profile["name"]) or "｜" in str(profile["name"])
    ]
    if len(grouped_headers) >= 4 and len(grouped_headers) == len(numeric_columns):
        layouts.append("grouped_box_wide")
    if {"wavelength", "uv_signal"}.issubset(tags):
        layouts.append("uv_vis_wide")
    if "pl_signal" in tags and ("wavelength" in tags or "time" in tags):
        layouts.append("pl_wide")
        if "time" in tags or "fit" in tags:
            layouts.append("trpl_wide")
    if {"estimate", "lower", "upper"}.issubset(tags) and categorical_columns:
        layouts.append("interval_table")
    if "size" in tags and len(numeric_columns) >= 3:
        layouts.append("indexed_size")
    if "diagnostic_x" in tags and len(numeric_columns) >= 2:
        layouts.append("diagnostic_coordinates")
    if {"predicted_probability", "observed_fraction", "bin_count"}.issubset(tags):
        layouts.append("calibration_bins")
    if {"threshold", "treat_all", "treat_none"}.issubset(tags) and len(numeric_columns) >= 4:
        layouts.append("decision_net_benefit")
    if "actual_class" in tags and "matrix_candidate" in layouts:
        layouts.append("confusion_matrix")
    if {"pair_mean", "difference", "bias", "loa_lower", "loa_upper"}.issubset(tags):
        layouts.append("bland_altman_limits")
    if "visit" in tags and len(numeric_columns) >= 3:
        layouts.append("paired_wide")
    if {"feature", "shap_value", "feature_value"}.issubset(tags) and categorical_columns:
        layouts.append("shap_long")
    trajectory_x = [
        profile
        for profile in profiles
        if profile["kind"] == "numeric" and "z_real" in profile["semantic_tags"]
    ]
    trajectory_z = [
        profile
        for profile in profiles
        if profile["kind"] == "numeric" and _explicit_negative_zimag_header(str(profile["name"]))
    ]
    trajectory_y = [
        profile
        for profile in profiles
        if profile["kind"] == "numeric"
        and "z_real" not in profile["semantic_tags"]
        and "z_imag" not in profile["semantic_tags"]
        and _trajectory3d_semantic_axis_header(str(profile["name"]))
    ]
    trajectory_series = [
        profile
        for profile in profiles
        if "series_id" in profile["semantic_tags"] and 1 <= int(profile["unique_count"]) <= 6
    ]
    if (
        len(trajectory_x) == 1
        and len(trajectory_y) == 1
        and len(trajectory_z) == 1
        and len(trajectory_series) == 1
    ):
        layouts.append("trajectory3d_long")
    if not layouts:
        layouts.append("unclassified_rectangular")

    domain_signals = {
        "xps": sum(tag in tags for tag in ("xps_energy", "background", "envelope", "residual")),
        "xrd": int("xrd_angle" in tags),
        "xas": int("absorption" in tags),
        "eis": sum(tag in tags for tag in ("z_real", "z_imag", "frequency", "phase")),
        "electrochem": sum(tag in tags for tag in ("potential", "current")),
        "sankey": sum(tag in tags for tag in ("source", "target", "value")),
        "error": int("error" in tags),
        "distribution": int("numeric_wide" in layouts),
        "forest": sum(tag in tags for tag in ("estimate", "lower", "upper", "reference")),
        "bubble": int("size" in tags),
        "diagnostic": int("diagnostic_coordinates" in layouts),
        "calibration": int("calibration_bins" in layouts),
        "decision": int("decision_net_benefit" in layouts),
        "confusion": int("confusion_matrix" in layouts),
        "agreement": int("bland_altman_limits" in layouts),
        "paired": int("paired_wide" in layouts),
        "shap": int("shap_long" in layouts),
        "grouped_box": int("grouped_box_wide" in layouts),
        "pl": sum(tag in tags for tag in ("pl_signal", "time", "fit")),
        "uv_vis": sum(tag in tags for tag in ("wavelength", "uv_signal", "tauc", "bandgap")),
        "trajectory3d": int("trajectory3d_long" in layouts),
    }

    return {
        "schema_version": "1.0",
        "ok": True,
        "engine_home": str(root),
        "source": {
            "path": loaded.source_path,
            "sha256": loaded.source_sha256,
            "size_bytes": loaded.source_size_bytes,
            "format": loaded.source_format,
            "delimiter": loaded.delimiter,
            "sheet": loaded.sheet_name,
        },
        "table": {
            "row_count": len(loaded.frame),
            "column_count": len(loaded.columns),
            "ignored_empty_rows": loaded.ignored_empty_rows,
            "numeric_column_count": len(numeric_columns),
            "categorical_column_count": len(categorical_columns),
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "layouts": layouts,
            "all_numeric_values_nonnegative": all_nonnegative,
            "first_category_unique_count": first_category_unique,
            "maximum_category_label_length": max_label_length,
        },
        "domain_signals": domain_signals,
        "columns": profiles,
    }


_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "xps": ("xps", "photoelectron", "光电子", "结合能", "分峰"),
    "xrd": ("xrd", "diffraction", "衍射", "物相"),
    "xas": ("xas", "xanes", "exafs", "absorption", "吸收谱"),
    "eis": ("eis", "impedance", "nyquist", "bode", "阻抗"),
    "cv": ("cv", "cyclicvoltammetry", "循环伏安"),
    "lsv": ("lsv", "linearsweep", "线性扫描"),
    "bar": ("bar", "column", "柱状", "组间比较"),
    "horizontal_bar": ("horizontalbar", "ranking", "横向条形", "排名", "长标签"),
    "stacked_bar": ("stacked", "composition", "堆叠", "构成"),
    "percent_stacked_bar": ("percentstacked", "percentagecomposition", "百分比堆叠", "占比"),
    "pie": ("pie", "parttowhole", "饼图", "份额"),
    "sankey": ("sankey", "flow", "桑基", "流向"),
    "scatter": ("scatter", "correlation", "relationship", "散点", "相关", "关系"),
    "line_error": ("errorbar", "uncertainty", "trend", "误差", "不确定性", "趋势"),
    "trend": ("trendline", "timeseries", "progression", "折线趋势", "时间趋势", "阶段变化"),
    "radar": ("radar", "spider", "multimetric", "雷达", "蛛网", "多指标"),
    "heatmap": ("heatmap", "matrix", "colormap", "热力图", "矩阵", "色块图"),
    "raw_summary": ("rawsummary", "stripplot", "dotplot", "observations", "原始点", "原始观测", "点汇总"),
    "violin": ("violin", "violinplot", "小提琴", "小提琴图"),
    "histogram": ("histogram", "frequencydistribution", "直方图", "频数分布"),
    "forest": ("forestplot", "effectestimate", "confidenceinterval", "森林图", "效应量", "置信区间"),
    "bubble": ("bubbleplot", "indexedsize", "气泡图", "气泡", "大小映射"),
    "diagnostic_curve": ("roc", "precisionrecall", "prcurve", "诊断曲线", "受试者工作特征", "精确率召回率"),
    "confusion_matrix": ("confusionmatrix", "classificationmatrix", "混淆矩阵", "分类矩阵"),
    "bland_altman": ("blandaltman", "agreement", "methodcomparison", "一致性", "方法比较"),
    "paired_trajectory": ("paired", "longitudinal", "trajectory", "配对", "纵向", "轨迹"),
    "calibration_curve": ("calibrationcurve", "reliability", "校准曲线", "可靠性"),
    "decision_curve": ("decisioncurve", "netbenefit", "dca", "决策曲线", "净获益"),
    "raincloud": ("raincloud", "raincloudplot", "halfviolin", "雨云图", "半小提琴"),
    "shap_summary": (
        "shapsummary",
        "shapbeeswarm",
        "featurecontribution",
        "shap汇总",
        "shap蜂群",
        "特征贡献",
    ),
    "grouped_box": ("groupedbox", "boxplot", "boxanddots", "分组箱线", "箱线图", "箱体图"),
    "pl": ("pl", "trpl", "photoluminescence", "luminescence", "光致发光", "荧光寿命", "时间分辨荧光"),
    "uv_vis": (
        "uvvis",
        "uv-vis",
        "absorbance",
        "transmittance",
        "tauc",
        "紫外可见",
        "吸光度",
        "透过率",
        "带隙",
    ),
    "trajectory3d": ("trajectory3d", "3dnyquist", "3dtrajectory", "三维nyquist", "三维阻抗", "三维轨迹"),
}


def _intent_match(template_id: str, intent: str) -> bool:
    canonical = _canonical(intent)
    return bool(canonical) and any(_canonical(item) in canonical for item in _INTENT_KEYWORDS[template_id])


def _first_numeric_profile(inspection: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in inspection["columns"] if item["kind"] == "numeric"), None)


def _score_candidate(
    template_id: str,
    preparation: Any,
    inspection: dict[str, Any],
    intent: str,
) -> tuple[float, list[str], list[str]]:
    table = inspection["table"]
    layouts = set(table["layouts"])
    signals = inspection["domain_signals"]
    score = 0.22 + 0.36 * float(preparation.confidence)
    reason_codes = ["template_preparation_succeeded"]
    reasons = [f"模板内部数据校验通过，列识别置信度 {preparation.confidence:.2f}。"]

    if _intent_match(template_id, intent):
        score += 0.28
        reason_codes.append("intent_match")
        reasons.append("与用户描述的绘图意图直接匹配。")

    domain_map = {
        "xps": "xps",
        "xrd": "xrd",
        "xas": "xas",
        "eis": "eis",
        "pl": "pl",
        "uv_vis": "uv_vis",
    }
    if template_id in domain_map:
        signal = int(signals[domain_map[template_id]])
        if signal:
            score += min(0.36, 0.15 + 0.09 * signal)
            reason_codes.append("domain_header_match")
            reasons.append("表头包含该领域的明确列语义。")
        elif not _intent_match(template_id, intent):
            score -= 0.34
            reason_codes.append("domain_signal_missing")

    if template_id in {"cv", "lsv"}:
        signal = int(signals["electrochem"])
        if signal >= 2:
            score += 0.22
            reason_codes.append("electrochem_header_match")
            reasons.append("电位和电流列语义明确。")
        elif not _intent_match(template_id, intent):
            score -= 0.30
        first = _first_numeric_profile(inspection)
        changes = int(first.get("direction_changes", 0)) if first else 0
        if template_id == "cv" and changes >= 1:
            score += 0.10
            reasons.append("自变量存在扫描方向变化，符合循环扫描特征。")
        if (
            template_id == "lsv"
            and first
            and (first.get("monotonic_increasing") or first.get("monotonic_decreasing"))
        ):
            score += 0.07

    category_templates = {
        "bar",
        "horizontal_bar",
        "stacked_bar",
        "percent_stacked_bar",
        "pie",
        "radar",
        "heatmap",
        "confusion_matrix",
    }
    if template_id in category_templates:
        if "category_wide" in layouts:
            score += 0.16
            reason_codes.append("category_wide_match")
            reasons.append("类别列加数值系列的宽表结构适配该图形。")
        else:
            score -= 0.30
        if "interval_table" in layouts:
            score -= 0.18
            reason_codes.append("explicit_interval_route_preferred")

    numeric_count = int(table["numeric_column_count"])
    category_count = int(table["first_category_unique_count"])
    long_label = int(table["maximum_category_label_length"])
    all_nonnegative = bool(table["all_numeric_values_nonnegative"])

    if template_id == "bar" and "category_wide" in layouts:
        score += 0.05
    elif template_id == "horizontal_bar":
        if long_label >= 12 or category_count > 8:
            score += 0.15
            reasons.append("类别较多或标签较长，横向条形更易阅读。")
        else:
            score -= 0.03
    elif template_id == "stacked_bar":
        score += 0.12 if numeric_count >= 2 and all_nonnegative else -0.22
    elif template_id == "percent_stacked_bar":
        score += 0.10 if numeric_count >= 2 and all_nonnegative else -0.28
        if not _intent_match(template_id, intent):
            score -= 0.07
            reason_codes.append("percent_transform_needs_intent")
    elif template_id == "pie":
        score += 0.15 if numeric_count == 1 and 1 < category_count <= 8 and all_nonnegative else -0.28
        if category_count > 8:
            reason_codes.append("too_many_pie_categories")
    elif template_id == "radar":
        if 3 <= category_count <= 12 and numeric_count >= 2 and all_nonnegative:
            score += 0.12
            reason_codes.append("multimetric_profile_match")
            reasons.append("检测到至少三个指标和多个非负对象系列。")
        else:
            score -= 0.30
        if not _intent_match(template_id, intent):
            score -= 0.03
            reason_codes.append("radar_scale_confirmation_preferred")
    elif template_id == "heatmap":
        if "matrix_candidate" in layouts and category_count >= 2 and numeric_count >= 2:
            score += 0.12
            reason_codes.append("matrix_candidate_match")
            reasons.append("类别 × 数值系列的矩形结构适合颜色矩阵。")
        else:
            score -= 0.30
        if "confusion_matrix" in layouts and _intent_match("confusion_matrix", intent):
            score -= 0.24
            reason_codes.append("confusion_matrix_route_preferred")
    elif template_id == "confusion_matrix":
        if "confusion_matrix" in layouts:
            score += 0.34
            reason_codes.append("actual_predicted_matrix_match")
            reasons.append("检测到实际类别行与预测类别数值矩阵。")
        else:
            score -= 0.42

    if (
        "confusion_matrix" in layouts
        and _intent_match("confusion_matrix", intent)
        and template_id in category_templates
        and template_id != "confusion_matrix"
    ):
        score -= 0.20
        reason_codes.append("explicit_confusion_intent_prefers_matrix_route")

    if template_id == "sankey":
        if "edge_list" in layouts:
            score += 0.42
            reason_codes.append("edge_list_match")
            reasons.append("检测到 source、target、value 边列表。")
        else:
            score -= 0.45
    elif template_id in {"scatter", "trend"}:
        if "numeric_xy" in layouts:
            score += 0.15
            reason_codes.append("numeric_xy_match")
            reasons.append("包含连续数值 X 与一个或多个数值观测系列。")
            if template_id == "scatter" and int(table["row_count"]) > 100:
                score += 0.04
            if template_id == "trend" and _intent_match(template_id, intent):
                first = _first_numeric_profile(inspection)
                if first and (first.get("monotonic_increasing") or first.get("monotonic_decreasing")):
                    score += 0.04
                    reason_codes.append("ordered_x_match")
                    reasons.append("第一数值列单调有序，适合连续过程趋势。")
        else:
            score -= 0.25
        if template_id == "scatter" and "indexed_size" in layouts:
            score -= 0.25
            reason_codes.append("indexed_size_route_preferred")
    elif template_id == "line_error":
        if "error_wide" in layouts:
            score += 0.37
            reason_codes.append("error_column_match")
            reasons.append("检测到明确的误差列后缀或中文误差语义。")
        elif _intent_match(template_id, intent):
            score -= 0.05
        else:
            score -= 0.30

    if template_id == "grouped_box":
        if "grouped_box_wide" in layouts:
            score += 0.40
            reason_codes.append("grouped_box_header_match")
            reasons.append("检测到 Category | Group 原始观测宽表，可保留分组箱体、原始点和样本量。")
        else:
            score -= 0.45

    if template_id in {"raw_summary", "violin", "raincloud", "histogram"}:
        if "numeric_wide" not in layouts:
            score -= 0.40
        elif template_id == "histogram":
            if "numeric_univariate" in layouts:
                score += 0.27
                reason_codes.append("univariate_distribution_match")
                reasons.append("检测到单列原始连续观测，适合冻结分箱规则的直方图。")
            else:
                score += 0.08
                reason_codes.append("multiple_distribution_series")
        elif template_id == "raw_summary":
            score += 0.22 if int(table["row_count"]) <= 80 else 0.12
            reason_codes.append("raw_observation_table_match")
            reasons.append("纯数值宽表可保留每个原始观测和组中位数。")
        elif template_id == "raincloud":
            score += 0.24 if int(table["row_count"]) >= 12 else 0.11
            reason_codes.append("raincloud_distribution_match")
            reasons.append("纯数值宽表可用半小提琴、全部原始点与均值 ± 1 SD 展示分布。")
            if not _intent_match(template_id, intent):
                score -= 0.08
                reason_codes.append("raincloud_intent_preferred")
        else:
            score += 0.22 if int(table["row_count"]) >= 20 else 0.12
            reason_codes.append("distribution_density_match")
            reasons.append("每组观测数量足以展示分布形状与箱线摘要。")
        first_profile = _first_numeric_profile(inspection)
        first_name = _canonical(first_profile["name"]) if first_profile else ""
        if template_id in {"raw_summary", "violin", "raincloud"} and first_name in {
            "x",
            "xvalue",
            "time",
            "step",
            "epoch",
            "dose",
            "自变量",
            "时间",
            "步数",
            "剂量",
        }:
            score -= 0.28
            reason_codes.append("leading_x_column_penalty")
        if "grouped_box_wide" in layouts:
            score -= 0.30
            reason_codes.append("grouped_box_route_preferred")

    if template_id == "forest":
        if "interval_table" in layouts:
            score += 0.42
            reason_codes.append("explicit_interval_table_match")
            reasons.append("检测到标签、估计值和显式置信区间上下限。")
        else:
            score -= 0.45

    if template_id == "bubble":
        if "indexed_size" in layouts:
            score += 0.38
            reason_codes.append("indexed_size_match")
            reasons.append("检测到 X、Y 和正值 Size 列，可使用面积编码第三变量。")
        else:
            score -= 0.42

    if template_id == "trajectory3d":
        if "trajectory3d_long" in layouts:
            score += 0.46
            reason_codes.append("explicit_xyz_series_long_match")
            reasons.append("检测到明确的 Zreal、带科学含义和单位的真实第三轴、-Zimag 与 Series 长表。")
        else:
            score -= 0.60
            reason_codes.append("explicit_xyz_series_evidence_missing")
    elif template_id == "eis" and "trajectory3d_long" in layouts:
        score -= 0.38
        reason_codes.append("trajectory3d_route_preferred")
        reasons.append("数据包含真实第三轴和 Series 长表，应保留三维条件语义而不是忽略附加列。")

    medical_layouts = {
        "diagnostic_curve": ("diagnostic_coordinates", "diagnostic_coordinate_match"),
        "calibration_curve": ("calibration_bins", "calibration_bin_match"),
        "decision_curve": ("decision_net_benefit", "decision_curve_match"),
        "bland_altman": ("bland_altman_limits", "agreement_limit_match"),
        "paired_trajectory": ("paired_wide", "paired_identity_match"),
        "shap_summary": ("shap_long", "precomputed_shap_long_match"),
    }
    if template_id in medical_layouts:
        layout, code = medical_layouts[template_id]
        if layout in layouts:
            score += 0.34
            reason_codes.append(code)
            reasons.append("检测到该医学证据图所需的显式列语义和数据布局。")
        else:
            score -= 0.42

    if preparation.requires_confirmation:
        score -= 0.08
        reason_codes.append("column_confirmation_required")
        reasons.append("模板内部仍要求确认列角色。")

    return max(0.01, min(0.99, score)), reason_codes, reasons


def recommend_charts(
    path: str | Path,
    *,
    intent: str = "",
    engine_home: str | Path | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Rank verified public Origin routes using data semantics, shape, intent, and service validation."""
    inspection = inspect_data(path, engine_home=engine_home)
    root = bootstrap_engine(engine_home)
    try:
        from origin_sciplot.template_service import TemplateServiceError, TemplateServiceRegistry
    except Exception as exc:  # noqa: BLE001
        raise EditaPlotError("engine_import_failed", f"Could not import template services: {exc}") from exc

    services = TemplateServiceRegistry()
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for service in services.implemented():
        template_id = str(service.manifest.id)
        if template_id not in VERIFIED_TEMPLATE_IDS:
            continue
        try:
            prepared = service.prepare(path)
        except TemplateServiceError as exc:
            rejected.append({"template_id": template_id, "code": exc.code})
            continue
        score, reason_codes, reasons = _score_candidate(template_id, prepared, inspection, intent)
        candidates.append(
            {
                "template_id": template_id,
                "template_name": service.manifest.name,
                "support_level": "verified",
                "score": round(score, 4),
                "internal_confidence": round(float(prepared.confidence), 4),
                "requires_column_confirmation": bool(prepared.requires_confirmation),
                "renderer_template_id": prepared.renderer_template_id,
                "summary": prepared.summary.heading,
                "reason_codes": reason_codes,
                "reasons": reasons,
                "warnings": list(prepared.summary.warnings),
            }
        )

    candidates.sort(key=lambda item: (-item["score"], item["template_id"]))
    selected = candidates[: max(1, limit)]
    top = selected[0] if selected else None
    second_score = selected[1]["score"] if len(selected) > 1 else 0.0
    margin = (top["score"] - second_score) if top else 0.0
    auto_allowed = bool(
        top
        and top["score"] >= AUTO_SCORE_THRESHOLD
        and margin >= AUTO_MARGIN_THRESHOLD
        and not top["requires_column_confirmation"]
    )
    gate_reasons: list[str] = []
    if top is None:
        gate_reasons.append("no_verified_template_accepts_data")
    else:
        if top["score"] < AUTO_SCORE_THRESHOLD:
            gate_reasons.append("top_score_below_threshold")
        if margin < AUTO_MARGIN_THRESHOLD:
            gate_reasons.append("candidate_margin_too_small")
        if top["requires_column_confirmation"]:
            gate_reasons.append("column_confirmation_required")

    return {
        "schema_version": "1.0",
        "ok": True,
        "source": inspection["source"],
        "intent": intent,
        "inspection_summary": {
            "layouts": inspection["table"]["layouts"],
            "row_count": inspection["table"]["row_count"],
            "column_count": inspection["table"]["column_count"],
            "domain_signals": inspection["domain_signals"],
        },
        "candidates": selected,
        "auto_selection": {
            "allowed": auto_allowed,
            "selected_template_id": top["template_id"] if auto_allowed and top else None,
            "top_score": top["score"] if top else None,
            "margin": round(margin, 4),
            "required_score": AUTO_SCORE_THRESHOLD,
            "required_margin": AUTO_MARGIN_THRESHOLD,
            "gate_reasons": gate_reasons,
        },
        "rejected_template_count": len(rejected),
        "engine_home": str(root),
    }


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def build_plan(
    path: str | Path,
    *,
    template_id: str,
    claim: str,
    evidence_role: str,
    target_output: str = "editable Origin figure and publication exports",
    intent: str = "",
    x_title: str | None = None,
    y_title: str | None = None,
    palette_id: str | None = None,
    mapping: dict[str, Any] | None = None,
    engine_home: str | Path | None = None,
) -> dict[str, Any]:
    """Freeze a selected template preparation into a source-bound render plan."""
    if not claim.strip():
        raise EditaPlotError("claim_required", "A one-sentence figure claim is required.")
    root = bootstrap_engine(engine_home)
    try:
        from origin_sciplot.palette_catalog import get_palette, palette_to_dict
        from origin_sciplot.scientific_workflow import (
            apply_scientific_palette_override,
            apply_scientific_text_overrides,
        )
        from origin_sciplot.template_service import TemplateServiceError, TemplateServiceRegistry
    except Exception as exc:  # noqa: BLE001
        raise EditaPlotError("engine_import_failed", f"Could not import template services: {exc}") from exc

    registry = TemplateServiceRegistry()
    try:
        service = registry.get(template_id)
        prepared = service.prepare(path)
        if mapping is not None:
            assignments = mapping.get("assignments")
            if not isinstance(assignments, dict):
                raise EditaPlotError("mapping_invalid", "Mapping JSON needs an assignments object.")
            context = str(mapping.get("energy_kind") or mapping.get("plot_mode") or "")
            prepared = service.confirm_mapping(
                prepared,
                assignments={str(key): str(value) for key, value in assignments.items()},
                energy_kind=context,
            )
    except TemplateServiceError as exc:
        raise EditaPlotError(exc.code, str(exc)) from exc

    worker_mapping = service.worker_mapping(prepared)
    frozen_payload = prepared.payload
    axis_title_overrides = {
        key: value for key, value in (("x_title", x_title), ("y_title", y_title)) if value is not None
    }
    if axis_title_overrides:
        if template_id == "xps":
            raise EditaPlotError(
                "text_overrides_unsupported",
                "Axis-title overrides are currently available for scientific-table templates only.",
            )
        try:
            frozen_payload = apply_scientific_text_overrides(
                frozen_payload,
                x_title=x_title,
                y_title=y_title,
            )
        except Exception as exc:  # noqa: BLE001 - normalize engine validation errors
            code = getattr(exc, "code", "text_overrides_invalid")
            raise EditaPlotError(code, str(exc)) from exc
    palette_contract: dict[str, Any] = {}
    if palette_id is not None:
        if template_id == "xps":
            raise EditaPlotError(
                "palette_override_unsupported",
                "XPS keeps its verified component-colour contract.",
            )
        try:
            frozen_payload = apply_scientific_palette_override(
                frozen_payload,
                palette_id=palette_id,
            )
            palette_contract = palette_to_dict(get_palette(palette_id))
        except Exception as exc:  # noqa: BLE001 - normalize engine validation errors
            code = getattr(exc, "code", "palette_invalid")
            raise EditaPlotError(code, str(exc)) from exc
    plot_spec = getattr(frozen_payload, "plot_spec", None)
    display_transform = getattr(plot_spec, "display_transform", "identity") if plot_spec else "identity"
    if hasattr(plot_spec, "visual_profile"):
        display_transform = plot_spec.visual_profile

    summary_facts = [list(item) for item in prepared.summary.facts]
    if plot_spec is not None and axis_title_overrides:
        for fact in summary_facts:
            if fact[0] == "X 轴":
                fact[1] = plot_spec.x_title
            elif fact[0] == "Y 轴":
                fact[1] = plot_spec.y_title

    plan: dict[str, Any] = {
        "plan_version": PLAN_VERSION,
        "product": "EditaPlot",
        "support_level": "verified" if template_id in VERIFIED_TEMPLATE_IDS else "experimental",
        "source": {
            "path": prepared.source_path,
            "sha256": getattr(prepared.payload, "source_sha256", _sha256(Path(prepared.source_path))),
            "size_bytes": prepared.source_size_bytes,
            "format": prepared.source_format,
            "sheet": prepared.source_sheet,
            "columns": list(prepared.source_columns),
            "row_count": prepared.row_count,
        },
        "figure_contract": {
            "core_conclusion": claim.strip(),
            "evidence_role": evidence_role.strip() or "unspecified",
            "user_intent": intent.strip(),
            "target_output": target_output.strip(),
            "axis_title_overrides": axis_title_overrides,
            "palette": palette_contract,
        },
        "template": {
            "id": template_id,
            "name": service.manifest.name,
            "renderer_template_id": prepared.renderer_template_id,
            "plan_digest": getattr(frozen_payload, "plan_digest", prepared.plan_digest),
            "confidence": float(prepared.confidence),
            "requires_confirmation": bool(prepared.requires_confirmation),
            "summary": {
                "heading": prepared.summary.heading,
                "facts": summary_facts,
                "roles": [list(item) for item in prepared.summary.roles],
                "components": list(prepared.summary.components),
                "warnings": list(prepared.summary.warnings),
            },
            "display_transform_or_profile": display_transform,
            "worker_mapping": _serialize(worker_mapping),
        },
        "execution": {
            "engine_home": str(root),
            "keep_origin_open": True,
            "requires_manual_origin_start_confirmation": True,
            "required_outputs": ["opju", "png", "pdf", "tif", "origin_verify_report"],
        },
        "can_render": bool(template_id in VERIFIED_TEMPLATE_IDS and not prepared.requires_confirmation),
        "blocked_reasons": (
            ["column_mapping_confirmation_required"] if prepared.requires_confirmation else []
        ),
    }
    plan["plan_hash"] = _json_hash(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("plan_version") != PLAN_VERSION:
        raise EditaPlotError("plan_version_unsupported", "Unsupported render-plan version.")
    expected_hash = plan.get("plan_hash")
    payload = dict(plan)
    payload.pop("plan_hash", None)
    if not isinstance(expected_hash, str) or expected_hash != _json_hash(payload):
        raise EditaPlotError("plan_hash_mismatch", "The render plan was modified after creation.")
    if not plan.get("can_render"):
        raise EditaPlotError(
            "plan_blocked",
            "The render plan still requires confirmation.",
            blocked_reasons=plan.get("blocked_reasons", []),
        )
    source = Path(str(plan["source"]["path"]))
    if not source.is_file():
        raise EditaPlotError("source_missing", "The planned source file no longer exists.")
    if _sha256(source) != str(plan["source"]["sha256"]):
        raise EditaPlotError("source_changed", "The source file changed after planning.")


def build_worker_command(
    plan: dict[str, Any],
    *,
    engine_home: str | Path | None = None,
    python_executable: str | Path | None = None,
    output_dir: str | Path | None = None,
    close_origin: bool = False,
) -> tuple[list[str], dict[str, str], Path]:
    validate_plan(plan)
    root = bootstrap_engine(engine_home or plan["execution"].get("engine_home"))
    python = str(python_executable or os.environ.get("EDITAPLOT_PYTHON") or sys.executable)
    command = [
        python,
        "-m",
        "origin_sciplot.workers.run_template_worker",
        "--template-id",
        str(plan["template"]["id"]),
        "--input-file",
        str(plan["source"]["path"]),
        "--expected-plan-digest",
        str(plan["template"]["plan_digest"]),
        "--close-origin" if close_origin else "--keep-origin-open",
    ]
    if output_dir:
        command.extend(("--output-dir", str(Path(output_dir).resolve())))
    mapping = plan["template"].get("worker_mapping")
    if mapping:
        command.extend(("--column-mapping-json", json.dumps(mapping, ensure_ascii=False)))
    text_overrides = plan.get("figure_contract", {}).get("axis_title_overrides")
    if text_overrides:
        command.extend(("--text-overrides-json", json.dumps(text_overrides, ensure_ascii=False)))
    palette = plan.get("figure_contract", {}).get("palette")
    if isinstance(palette, dict) and palette.get("palette_id"):
        command.extend(("--palette-id", str(palette["palette_id"])))
    env = dict(os.environ)
    source_path = str(root / "src")
    env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return command, env, root


def _medical_panel_layout(panel_count: int, hero_panel: int | None) -> dict[str, Any]:
    """Freeze a compact publication layout without touching panel pixels."""
    if hero_panel is not None and panel_count in {3, 5}:
        rows = 2 if panel_count == 3 else 3
        columns = 2
        slots = [
            {
                "panel_index": hero_panel,
                "row": 0,
                "column": 0,
                "row_span": 1,
                "column_span": 2,
            }
        ]
        remaining = [index for index in range(panel_count) if index != hero_panel]
        for slot_index, panel_index in enumerate(remaining):
            slots.append(
                {
                    "panel_index": panel_index,
                    "row": 1 + slot_index // 2,
                    "column": slot_index % 2,
                    "row_span": 1,
                    "column_span": 1,
                }
            )
        profile = "hero-wide"
    else:
        columns = 2 if panel_count <= 4 else 3
        rows = int(math.ceil(panel_count / columns))
        slots = [
            {
                "panel_index": index,
                "row": index // columns,
                "column": index % columns,
                "row_span": 1,
                "column_span": 1,
            }
            for index in range(panel_count)
        ]
        profile = f"grid-{rows}x{columns}"
    panel_width_cm = 8.4
    panel_height_cm = 6.4
    gap_cm = 0.45
    outer_margin_cm = 0.70
    return {
        "profile": profile,
        "rows": rows,
        "columns": columns,
        "slots": slots,
        "page_width_cm": round(
            columns * panel_width_cm + (columns - 1) * gap_cm + 2 * outer_margin_cm,
            2,
        ),
        "page_height_cm": round(
            rows * panel_height_cm + (rows - 1) * gap_cm + 2 * outer_margin_cm,
            2,
        ),
        "panel_gap_cm": gap_cm,
        "outer_margin_cm": outer_margin_cm,
        "panel_label_size_pt": 18.0,
        "caption_size_pt": 14.0,
    }


def _medical_image_signature_ok(path: Path) -> bool:
    with path.open("rb") as stream:
        header = stream.read(8)
    suffix = path.suffix.casefold()
    if suffix == ".png":
        return header == b"\x89PNG\r\n\x1a\n"
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    return False


def build_medical_panel_plan(
    config_path: str | Path,
    *,
    claim: str,
    title: str = "Medical imaging & AI evidence",
) -> dict[str, Any]:
    """Validate and freeze a deidentification-aware multi-panel layout plan.

    This is deliberately a composition gate, not a new Origin renderer.  It
    accepts only verified quantitative Origin outputs and user-attested,
    deidentified image panels.  It never OCRs, crops, windows, resamples, or
    modifies medical images.
    """
    config_file = Path(config_path).expanduser().resolve()
    config = load_json(config_file)
    panels = config.get("panels")
    if not isinstance(panels, list) or not 2 <= len(panels) <= 9:
        raise EditaPlotError(
            "medical_panel_count",
            "A medical panel plan needs 2 to 9 panel objects.",
        )
    hero_raw = config.get("hero_panel")
    hero_panel = None if hero_raw is None else int(hero_raw)
    if hero_panel is not None and not 0 <= hero_panel < len(panels):
        raise EditaPlotError("medical_hero_panel", "hero_panel is outside the panel list.")

    blocked: list[str] = []
    panel_records: list[dict[str, Any]] = []
    image_count = 0
    quantitative_count = 0
    for index, raw in enumerate(panels):
        if not isinstance(raw, dict):
            raise EditaPlotError("medical_panel_object", f"Panel {index + 1} must be an object.")
        kind = str(raw.get("kind", "")).strip().casefold()
        panel_title = str(raw.get("title", "")).strip()
        evidence_role = str(raw.get("evidence_role", "")).strip()
        source_value = raw.get("source")
        if kind not in {"quantitative", "image"}:
            raise EditaPlotError(
                "medical_panel_kind",
                f"Panel {index + 1} kind must be quantitative or image.",
            )
        if not panel_title or not evidence_role or not isinstance(source_value, str):
            raise EditaPlotError(
                "medical_panel_metadata",
                f"Panel {index + 1} needs title, evidence_role, and source.",
            )
        source_candidate = Path(source_value).expanduser()
        source = (
            source_candidate if source_candidate.is_absolute() else config_file.parent / source_candidate
        ).resolve()
        record: dict[str, Any] = {
            "index": index,
            "label": chr(ord("A") + index),
            "kind": kind,
            "title": panel_title,
            "evidence_role": evidence_role,
            "source": str(source),
        }
        if kind == "quantitative":
            quantitative_count += 1
            verification = verify_output(source)
            report_path = source / "origin_verify_report.json"
            report = load_json(report_path) if report_path.is_file() else {}
            template_id = str(report.get("template_id", ""))
            if not verification["programmatic_pass"]:
                blocked.append(f"panel_{index + 1}_origin_verification_failed")
            if template_id not in VERIFIED_TEMPLATE_IDS:
                blocked.append(f"panel_{index + 1}_route_not_verified")
            if str(raw.get("human_visual_qa", "")).casefold() != "pass":
                blocked.append(f"panel_{index + 1}_human_visual_qa_required")
            artifacts = verification["artifacts"]
            record.update(
                {
                    "template_id": template_id,
                    "origin_programmatic_pass": bool(verification["programmatic_pass"]),
                    "human_visual_qa": str(raw.get("human_visual_qa", "")),
                    "preview_png": artifacts["png"]["path"],
                    "preview_sha256": _sha256(Path(artifacts["png"]["path"]))
                    if artifacts["png"]["ok"]
                    else None,
                    "editable_opju": artifacts["opju"]["path"],
                    "opju_sha256": _sha256(Path(artifacts["opju"]["path"]))
                    if artifacts["opju"]["ok"]
                    else None,
                    "origin_report_sha256": _sha256(report_path) if report_path.is_file() else None,
                }
            )
        else:
            image_count += 1
            if not source.is_file():
                raise EditaPlotError(
                    "medical_image_missing",
                    f"Image panel source does not exist: {source}",
                )
            if source.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                raise EditaPlotError(
                    "medical_image_format",
                    "Medical image panels must be PNG, JPEG, or TIFF.",
                )
            if not _medical_image_signature_ok(source):
                raise EditaPlotError(
                    "medical_image_signature",
                    "Medical image content does not match its PNG, JPEG, or TIFF extension.",
                )
            if raw.get("deidentified") is not True:
                blocked.append(f"panel_{index + 1}_deidentification_attestation_required")
            if raw.get("burned_in_text_checked") is not True:
                blocked.append(f"panel_{index + 1}_burned_in_text_check_required")
            modality = str(raw.get("modality", "")).strip()
            plane = str(raw.get("plane", "")).strip()
            display_parameters = str(raw.get("display_parameters", "")).strip()
            if not modality or not plane or not display_parameters:
                blocked.append(f"panel_{index + 1}_imaging_metadata_required")
            record.update(
                {
                    "sha256": _sha256(source),
                    "deidentified": raw.get("deidentified") is True,
                    "burned_in_text_checked": raw.get("burned_in_text_checked") is True,
                    "modality": modality,
                    "plane": plane,
                    "display_parameters": display_parameters,
                    "scale_bar": str(raw.get("scale_bar", "not supplied")),
                    "annotation_meaning": str(raw.get("annotation_meaning", "none")),
                    "pixel_transform": "none_in_panel_planner",
                }
            )
        panel_records.append(record)

    shared_legend = bool(config.get("shared_legend", False))
    if shared_legend and config.get("shared_semantics_confirmed") is not True:
        blocked.append("shared_legend_semantics_confirmation_required")
    if len({item["evidence_role"].casefold() for item in panel_records}) != len(panel_records):
        blocked.append("each_panel_needs_unique_evidence_role")
    condition_color_map = config.get("condition_color_map")
    valid_condition_color_map = bool(condition_color_map) and isinstance(condition_color_map, dict)
    if valid_condition_color_map:
        valid_condition_color_map = all(
            str(condition).strip() and str(color).strip() for condition, color in condition_color_map.items()
        )
    if quantitative_count > 1 and not valid_condition_color_map:
        blocked.append("condition_color_map_required_for_multiple_quantitative_panels")
    layout = _medical_panel_layout(len(panel_records), hero_panel)
    payload: dict[str, Any] = {
        "plan_version": MEDICAL_PANEL_PLAN_VERSION,
        "product": "EditaPlot",
        "plan_type": "medical_multi_panel_composition",
        "support_level": "verified_inputs_planning_only",
        "title": title.strip() or "Medical imaging & AI evidence",
        "claim": claim.strip(),
        "config": {
            "path": str(config_file),
            "sha256": _sha256(config_file),
        },
        "panel_count": len(panel_records),
        "quantitative_panel_count": quantitative_count,
        "image_panel_count": image_count,
        "panels": panel_records,
        "layout": layout,
        "semantic_contract": {
            "condition_color_map": condition_color_map if valid_condition_color_map else {},
            "shared_legend": shared_legend,
            "shared_semantics_confirmed": config.get("shared_semantics_confirmed") is True,
            "each_panel_has_unique_evidence_role": len(
                {item["evidence_role"].casefold() for item in panel_records}
            )
            == len(panel_records),
        },
        "deidentification_gate": {
            "automatic_phi_detection_performed": False,
            "user_attestation_required": image_count > 0,
            "all_image_attestations_pass": not any(
                "deidentification" in item or "burned_in_text" in item for item in blocked
            ),
        },
        "composition_backend": {
            "status": "layout_plan_only",
            "origin_subprojects_remain_editable": True,
            "merged_origin_opju_claimed": False,
            "medical_image_processing_performed": False,
        },
        "can_compose": not blocked and bool(claim.strip()),
        "blocked_reasons": list(
            dict.fromkeys(blocked or (["core_claim_required"] if not claim.strip() else []))
        ),
    }
    payload["plan_hash"] = _json_hash(payload)
    return payload


def _managed_python(root: Path) -> Path:
    scripts = "Scripts" if platform.system() == "Windows" else "bin"
    executable = "python.exe" if platform.system() == "Windows" else "python"
    return root / MANAGED_ENV_DIRECTORY / scripts / executable


def repair_environment(*, engine_home: str | Path | None = None) -> dict[str, Any]:
    """Create a project-local runtime and install only the audited Python dependencies.

    This routine never installs, patches, licenses, or launches Origin.  A valid
    licensed Origin installation remains a manual prerequisite for rendering.
    """

    if sys.version_info < (3, 10):  # noqa: UP036 - keep a structured error for direct script use
        raise EditaPlotError(
            "python_version_unrepairable",
            "Python 3.10 or newer must be installed before automatic dependency repair.",
        )
    if platform.system() != "Windows":
        raise EditaPlotError(
            "windows_required",
            "EditaPlot rendering is supported on Windows only.",
        )
    root = bootstrap_engine(engine_home)
    env_root = root / MANAGED_ENV_DIRECTORY
    python = _managed_python(root)
    actions: list[dict[str, Any]] = []
    if not python.is_file():
        command = [sys.executable, "-m", "venv", str(env_root)]
        completed = subprocess.run(  # noqa: S603 - fixed interpreter/module invocation
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        actions.append({"action": "create_project_venv", "returncode": completed.returncode})
        if completed.returncode != 0 or not python.is_file():
            raise EditaPlotError(
                "venv_creation_failed",
                "Could not create the project-local EditaPlot environment.",
                returncode=completed.returncode,
            )

    constraints = Path(__file__).with_name("requirements-runtime.lock")
    if not constraints.is_file():
        raise EditaPlotError(
            "dependency_lock_missing",
            "The audited dependency lock is missing; refusing an unpinned repair.",
        )

    install_command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--constraint",
        str(constraints),
        *[spec for _module, spec in RUNTIME_DEPENDENCIES],
    ]
    completed = subprocess.run(  # noqa: S603 - fixed managed interpreter/package allowlist
        install_command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    actions.append({"action": "install_audited_runtime_dependencies", "returncode": completed.returncode})
    if completed.returncode != 0:
        raise EditaPlotError(
            "dependency_install_failed",
            "Could not install the audited Python dependencies in the project-local environment.",
            returncode=completed.returncode,
        )
    return {
        "schema_version": "1.0",
        "ok": True,
        "managed_environment": str(env_root),
        "python_executable": str(python),
        "actions": actions,
        "installed_specs": [spec for _module, spec in RUNTIME_DEPENDENCIES],
        "constraint_file": str(constraints),
        "origin_installation_modified": False,
        "next_step": (
            "Run doctor again with the returned python_executable, then manually confirm "
            "licensed Origin starts before render."
        ),
    }


def doctor(*, engine_home: str | Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(
        {
            "name": "python_version",
            "ok": python_ok,
            "value": platform.python_version(),
            "required": ">=3.10",
        }
    )
    windows = platform.system() == "Windows"
    checks.append({"name": "windows", "ok": windows, "value": platform.platform()})
    try:
        root = bootstrap_engine(engine_home)
        engine_ok = True
        checks.append({"name": "engine", "ok": True, "value": str(root)})
    except EditaPlotError as exc:
        root = None
        engine_ok = False
        checks.append({"name": "engine", "ok": False, "value": str(exc)})

    dependencies = tuple(module for module, _spec in RUNTIME_DEPENDENCIES)
    expected_versions = {module: spec.partition("==")[2] for module, spec in RUNTIME_DEPENDENCIES}
    dependency_state: dict[str, bool] = {}
    for name in dependencies:
        available = importlib.util.find_spec(name) is not None
        version = None
        if available and importlib_metadata is not None:
            package_name = {"yaml": "PyYAML", "PIL": "pillow"}.get(name, name)
            try:
                version = importlib_metadata.version(package_name)
            except importlib_metadata.PackageNotFoundError:
                version = "unknown"
        dependency_state[name] = bool(available and version == expected_versions[name])
        checks.append(
            {
                "name": f"python_dependency:{name}",
                "ok": dependency_state[name],
                "value": version,
                "required": expected_versions[name],
            }
        )

    ready_analysis = (
        python_ok
        and engine_ok
        and all(dependency_state[name] for name in dependencies if name != "originpro")
    )
    ready_render = ready_analysis and windows and dependency_state["originpro"]
    missing_dependencies = [name for name in dependencies if not dependency_state[name]]
    repair_python_ok = sys.version_info[:2] == (3, 10)
    checks.append(
        {
            "name": "automatic_repair_python",
            "ok": repair_python_ok,
            "value": platform.python_version(),
            "required": "CPython 3.10.x verified lock",
        }
    )
    repairable = bool(repair_python_ok and windows and engine_ok and missing_dependencies)
    manual_blockers: list[str] = []
    if not python_ok:
        manual_blockers.append("install_python_3_10_or_newer")
    if not windows:
        manual_blockers.append("use_supported_windows_host")
    if not engine_ok:
        manual_blockers.append("provide_editaplot_engine_home")
    if missing_dependencies and python_ok and not repair_python_ok:
        manual_blockers.append("automatic_repair_requires_verified_cpython_3_10")
    if not dependency_state.get("originpro", False):
        manual_blockers.append(
            "python_originpro_package_can_be_repaired_but_licensed_origin_must_be_installed_manually"
        )
    return {
        "schema_version": "1.0",
        "ok": ready_analysis,
        "ready_for_analysis": ready_analysis,
        "ready_for_render": ready_render,
        "manual_origin_launch_confirmation": "required_before_render",
        "missing_python_dependencies": missing_dependencies,
        "automatic_repair": {
            "available": repairable,
            "scope": "project_local_python_dependencies_only",
            "managed_environment": str((root / MANAGED_ENV_DIRECTORY) if root else MANAGED_ENV_DIRECTORY),
            "origin_installation_modified": False,
        },
        "manual_blockers": manual_blockers,
        "checks": checks,
    }


def catalog(*, engine_home: str | Path | None = None) -> dict[str, Any]:
    root = bootstrap_engine(engine_home)
    try:
        from origin_sciplot.template_registry import TemplateRegistry
    except Exception as exc:  # noqa: BLE001
        raise EditaPlotError("engine_import_failed", f"Could not import template registry: {exc}") from exc
    templates = []
    for manifest in TemplateRegistry().implemented():
        templates.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "family": manifest.family,
                "support_level": "verified" if manifest.id in VERIFIED_TEMPLATE_IDS else "experimental",
                "description": manifest.description,
                "required_columns": list(manifest.data_guide.required_columns),
                "optional_columns": list(manifest.data_guide.optional_columns),
                "accepted_layouts": list(manifest.data_guide.accepted_layouts),
                "examples": [
                    {"id": item.id, "name": item.name, "description": item.description}
                    for item in manifest.examples
                ],
            }
        )
    return {"schema_version": "1.0", "ok": True, "engine_home": str(root), "templates": templates}


def palette_catalog(
    *,
    engine_home: str | Path | None = None,
    public_only: bool = True,
) -> dict[str, Any]:
    root = bootstrap_engine(engine_home)
    try:
        from origin_sciplot.palette_catalog import list_palettes, palette_to_dict
    except Exception as exc:  # noqa: BLE001
        raise EditaPlotError("engine_import_failed", f"Could not import palette catalog: {exc}") from exc
    palettes = [palette_to_dict(item) for item in list_palettes(public_only=public_only)]
    return {
        "schema_version": "1.0",
        "ok": True,
        "engine_home": str(root),
        "public_only": public_only,
        "palette_count": len(palettes),
        "palettes": palettes,
    }


def _font_readback_audit(report: dict[str, Any]) -> dict[str, Any]:
    expected_codes: list[int] = []
    actual_codes: dict[str, int] = {}

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                canonical = str(key).casefold()
                if canonical == "font_code_expected" and isinstance(item, (int, float)):
                    expected_codes.append(int(round(float(item))))
                elif isinstance(item, (int, float)) and (
                    canonical == "font_code"
                    or canonical.endswith(".font")
                    or canonical.endswith(".font_code")
                    or canonical.endswith("_font_code")
                ):
                    actual_codes[child] = int(round(float(item)))
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(
        {
            "origin_axis_state": report.get("origin_axis_state"),
            "origin_text_state": report.get("origin_text_state"),
        }
    )
    unique_expected = sorted(set(expected_codes))
    mismatches = {
        path: code
        for path, code in actual_codes.items()
        if len(unique_expected) != 1 or code != unique_expected[0]
    }
    return {
        "ok": bool(actual_codes) and len(unique_expected) == 1 and not mismatches,
        "expected_font_codes": unique_expected,
        "actual_font_codes": actual_codes,
        "mismatches": mismatches,
    }


def verify_output(path: str | Path) -> dict[str, Any]:
    output = Path(path).resolve()
    if not output.is_dir():
        raise EditaPlotError("output_not_found", "The Origin output directory does not exist.")
    expected = {
        "opju": output / "result.opju",
        "png": output / "result.png",
        "pdf": output / "result.pdf",
        "tif": output / "result.tif",
        "origin_verify_report": output / "origin_verify_report.json",
        "validation_report": output / "validation_report.json",
    }
    artifacts: dict[str, Any] = {}
    all_nonempty = True
    for name, file in expected.items():
        exists = file.is_file()
        size = file.stat().st_size if exists else 0
        ok = exists and size > 0
        all_nonempty = all_nonempty and ok
        artifacts[name] = {"path": str(file), "exists": exists, "size_bytes": size, "ok": ok}

    readback_valid = False
    readback_keys: list[str] = []
    semantic_checks: dict[str, Any] = {
        "axis_state_present": False,
        "text_state_present": False,
        "exports_confirmed": False,
        "source_data_not_modified": False,
        "font_readback": {"ok": False},
    }
    report_path = expected["origin_verify_report"]
    if report_path.is_file() and report_path.stat().st_size:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            readback_valid = isinstance(report, dict) and bool(report)
            readback_keys = sorted(str(key) for key in report) if isinstance(report, dict) else []
            if isinstance(report, dict):
                exports = report.get("exports")
                semantic_checks = {
                    "axis_state_present": isinstance(report.get("origin_axis_state"), dict)
                    and bool(report.get("origin_axis_state")),
                    "text_state_present": isinstance(report.get("origin_text_state"), dict)
                    and bool(report.get("origin_text_state")),
                    "exports_confirmed": isinstance(exports, dict)
                    and all(bool(exports.get(name)) for name in ("png", "pdf", "tif")),
                    "source_data_not_modified": report.get("source_data_modified") is False,
                    "font_readback": _font_readback_audit(report),
                }
        except (OSError, json.JSONDecodeError):
            readback_valid = False

    semantic_pass = (
        semantic_checks["axis_state_present"]
        and semantic_checks["text_state_present"]
        and semantic_checks["exports_confirmed"]
        and semantic_checks["source_data_not_modified"]
        and bool(semantic_checks["font_readback"].get("ok"))
    )
    programmatic_pass = all_nonempty and readback_valid and semantic_pass
    return {
        "schema_version": "1.0",
        "ok": programmatic_pass,
        "output_directory": str(output),
        "programmatic_pass": programmatic_pass,
        "origin_readback_valid": readback_valid,
        "origin_readback_top_level_keys": readback_keys,
        "semantic_checks": semantic_checks,
        "artifacts": artifacts,
        "human_visual_qa": {
            "status": "pending",
            "required_checks": [
                "axis direction and ticks",
                "title and label clipping",
                "font and line-weight readability",
                "color semantics",
                "unexpected Origin objects",
                "scientific transform matches contract",
            ],
        },
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditaPlotError("json_read_failed", f"Could not read JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise EditaPlotError("json_object_required", "Expected a JSON object.")
    return payload


def summarize_paths(items: Iterable[Path]) -> list[str]:
    return [str(item.resolve()) for item in items]


__all__ = [
    "EditaPlotError",
    "bootstrap_engine",
    "build_plan",
    "build_medical_panel_plan",
    "build_worker_command",
    "catalog",
    "doctor",
    "inspect_data",
    "load_json",
    "recommend_charts",
    "resolve_engine_home",
    "validate_plan",
    "verify_output",
    "write_json",
]
