"""Generic template workflow services used by the desktop application."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scientific_preview import ScientificPreviewError, render_scientific_preview_png
from .scientific_workflow import (
    ScientificColumnMapping,
    ScientificPreparation,
    ScientificWorkflowError,
    mapping_context_options,
    prepare_scientific,
    role_options,
)
from .template_registry import TemplateManifest, TemplateRegistry
from .xps_preview import XpsPreviewError, render_xps_preview_png
from .xps_workflow import (
    XpsColumnMapping,
    XpsPreparation,
    XpsWorkflowError,
    prepare_xps,
    select_xps_renderer_template_id,
)


class TemplateServiceError(ValueError):
    """Stable failure raised by a top-level template workflow service."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TemplateConfirmationRequired(TemplateServiceError):
    def __init__(self) -> None:
        super().__init__(
            "mapping_confirmation_required",
            "Confirm the detected column roles before generating a preview or running Origin.",
        )


@dataclass(frozen=True)
class MappingRoleOption:
    key: str
    label: str
    unique: bool


@dataclass(frozen=True)
class ColumnMappingRequest:
    columns: tuple[str, ...]
    role_options: tuple[MappingRoleOption, ...]
    suggested_roles: tuple[tuple[str, str], ...]
    energy_kind: str | None
    energy_kind_options: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    context_label: str | None = None
    context_value: str | None = None
    context_options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TemplateSummary:
    heading: str
    facts: tuple[tuple[str, str], ...]
    roles: tuple[tuple[str, str], ...]
    components: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PreparedTemplate:
    template_id: str
    renderer_template_id: str
    source_path: str
    source_size_bytes: int
    source_format: str
    source_sheet: str | None
    source_columns: tuple[str, ...]
    row_count: int
    confidence: float
    requires_confirmation: bool
    plan_digest: str
    summary: TemplateSummary
    mapping_request: ColumnMappingRequest | None
    payload: Any


class XpsTemplateService:
    """Top-level XPS workflow backed by internal fixed/adaptive renderers."""

    _ROLE_OPTIONS = (
        MappingRoleOption("x", "X 能量", True),
        MappingRoleOption("raw", "Raw / 强度", True),
        MappingRoleOption("background", "Background / 背景", True),
        MappingRoleOption("envelope", "Envelope / 拟合包络", True),
        MappingRoleOption("residual", "Residual / 残差", True),
        MappingRoleOption("component", "Component peak / 分峰", False),
        MappingRoleOption("ignored", "忽略", False),
    )

    def __init__(self, manifest: TemplateManifest) -> None:
        self.manifest = manifest

    @staticmethod
    def _summary(preparation: XpsPreparation) -> TemplateSummary:
        detection = preparation.detection
        roles = preparation.roles
        mode_labels = {
            "scan": "扫描",
            "fit": "拟合",
            "fit_with_residual": "拟合（含残差列）",
        }
        energy_labels = {"binding": "Binding Energy", "kinetic": "Kinetic Energy", "unknown": "Energy"}
        return TemplateSummary(
            heading=f"XPS · {detection.spectrum_region} · {mode_labels[detection.mode]}",
            facts=(
                (
                    "能量类型",
                    f"{energy_labels[detection.energy_kind]} ({detection.energy_kind})",
                ),
                ("谱区", detection.spectrum_region),
                ("模式", f"{mode_labels[detection.mode]} ({detection.mode})"),
                ("内部 Profile", preparation.plot_spec.visual_profile),
            ),
            roles=(
                ("X", roles.x),
                ("Raw", roles.raw or "—"),
                ("Background", roles.background or "—"),
                ("Envelope", roles.envelope or "—"),
                ("Residual", roles.residual or "—"),
            ),
            components=roles.components,
            warnings=preparation.warnings,
        )

    @classmethod
    def _mapping_request(cls, preparation: XpsPreparation) -> ColumnMappingRequest:
        roles = preparation.roles
        assignments = {column: "component" for column in preparation.source_columns}
        assignments[roles.x] = "x"
        if roles.raw:
            assignments[roles.raw] = "raw"
        for role, column in (
            ("background", roles.background),
            ("envelope", roles.envelope),
            ("residual", roles.residual),
        ):
            if column:
                assignments[column] = role
        for column in roles.ignored:
            assignments[column] = "ignored"
        energy_kind = (
            preparation.detection.energy_kind
            if preparation.detection.energy_kind in {"binding", "kinetic"}
            else None
        )
        return ColumnMappingRequest(
            columns=preparation.source_columns,
            role_options=cls._ROLE_OPTIONS,
            suggested_roles=tuple((column, assignments[column]) for column in preparation.source_columns),
            energy_kind=energy_kind,
            energy_kind_options=(("binding", "Binding Energy"), ("kinetic", "Kinetic Energy")),
            reasons=preparation.confirmation_reasons,
            context_label="能量类型",
            context_value=energy_kind,
            context_options=(("binding", "Binding Energy"), ("kinetic", "Kinetic Energy")),
        )

    def _wrap(self, preparation: XpsPreparation) -> PreparedTemplate:
        return PreparedTemplate(
            template_id=self.manifest.id,
            renderer_template_id=select_xps_renderer_template_id(preparation),
            source_path=preparation.source_path,
            source_size_bytes=preparation.source_size_bytes,
            source_format=preparation.source_format,
            source_sheet=preparation.source_sheet,
            source_columns=preparation.source_columns,
            row_count=preparation.row_count,
            confidence=preparation.confidence,
            requires_confirmation=preparation.requires_confirmation,
            plan_digest=preparation.plan_digest,
            summary=self._summary(preparation),
            mapping_request=self._mapping_request(preparation),
            payload=preparation,
        )

    def prepare(self, path: str | Path) -> PreparedTemplate:
        try:
            return self._wrap(prepare_xps(path))
        except XpsWorkflowError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    def confirm_mapping(
        self,
        prepared: PreparedTemplate,
        *,
        assignments: dict[str, str],
        energy_kind: str,
    ) -> PreparedTemplate:
        if energy_kind not in {"binding", "kinetic"}:
            raise TemplateServiceError("mapping_energy_kind", "Select Binding or Kinetic Energy.")
        if set(assignments) != set(prepared.source_columns):
            raise TemplateServiceError(
                "mapping_incomplete", "Every source column must be assigned a role or ignored."
            )
        allowed = {option.key for option in self._ROLE_OPTIONS}
        invalid = next((role for role in assignments.values() if role not in allowed), None)
        if invalid is not None:
            raise TemplateServiceError("mapping_unknown_role", f"Unknown mapping role: {invalid}")

        def unique(role: str, *, required: bool = False) -> str | None:
            matches = [column for column, assigned in assignments.items() if assigned == role]
            if required and len(matches) != 1:
                raise TemplateServiceError(
                    f"mapping_{role}_required", f"Exactly one column must be assigned to {role}."
                )
            if len(matches) > 1:
                raise TemplateServiceError(
                    f"mapping_{role}_conflict", f"Only one column can be assigned to {role}."
                )
            return matches[0] if matches else None

        mapping = XpsColumnMapping(
            x=unique("x", required=True) or "",
            raw=unique("raw", required=True) or "",
            background=unique("background"),
            envelope=unique("envelope"),
            residual=unique("residual"),
            components=tuple(
                column for column in prepared.source_columns if assignments[column] == "component"
            ),
            ignored=tuple(
                column for column in prepared.source_columns if assignments[column] == "ignored"
            ),
            energy_kind=energy_kind,  # type: ignore[arg-type]
        )
        try:
            return self._wrap(prepare_xps(prepared.source_path, column_mapping=mapping))
        except XpsWorkflowError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    def render_preview(self, prepared: PreparedTemplate) -> bytes:
        if prepared.requires_confirmation:
            raise TemplateConfirmationRequired()
        try:
            return render_xps_preview_png(prepared.payload)
        except XpsPreviewError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    @staticmethod
    def worker_mapping(prepared: PreparedTemplate) -> dict[str, object] | None:
        preparation: XpsPreparation = prepared.payload
        return preparation.column_mapping.to_dict() if preparation.column_mapping else None


class ScientificTemplateService:
    """Shared public service for non-XPS scientific table templates."""

    def __init__(self, manifest: TemplateManifest) -> None:
        self.manifest = manifest

    def _summary(self, preparation: ScientificPreparation) -> TemplateSummary:
        spec = preparation.plot_spec
        assignments = dict(preparation.assignments)
        if spec.plot_kind == "trajectory3d":
            return TemplateSummary(
                heading=f"{self.manifest.name} · {len(spec.group_order)} 条轨迹",
                facts=(
                    ("绘图模式", spec.plot_mode),
                    ("图形类型", spec.plot_kind),
                    ("X 轴", spec.x_title),
                    ("Y 轴（真实第三变量）", spec.y_title),
                    ("Z 轴", spec.z_title or "—"),
                ),
                roles=(
                    ("X / Zreal", spec.x_column or "—"),
                    ("Y / 第三变量", spec.y_column or "—"),
                    ("Z / -Zimag", spec.series[0].source_column),
                    ("Series", spec.category_column or "—"),
                ),
                components=spec.group_order,
                warnings=preparation.warnings,
            )
        x_value = spec.category_column or spec.x_column or spec.source_column or "—"
        errors = [column for column, role in assignments.items() if role == "error"]
        facts = (
            ("绘图模式", spec.plot_mode),
            ("图形类型", spec.plot_kind),
            ("X 轴", spec.x_title),
            ("Y 轴", "Feature（输入顺序）" if spec.plot_kind == "shap_summary" else spec.y_title),
        )
        if spec.y2_title:
            facts = (*facts, ("右 Y 轴", spec.y2_title))
        if spec.plot_kind == "sankey":
            roles = (
                ("Source", spec.source_column or "—"),
                ("Target", spec.target_column or "—"),
                ("Value", spec.series[0].source_column),
            )
        elif spec.plot_kind == "shap_summary":
            series = spec.series[0]
            roles = (
                ("Feature", spec.category_column or "—"),
                ("SHAP value", series.source_column),
                ("Feature value / color", series.color_column or "—"),
            )
        else:
            roles = (
                ("X", x_value),
                ("Series", ", ".join(item.source_column for item in spec.series)),
                ("Error", ", ".join(errors) if errors else "—"),
            )
        return TemplateSummary(
            heading=f"{self.manifest.name} · {spec.plot_mode}",
            facts=facts,
            roles=roles,
            components=tuple(item.label for item in spec.series),
            warnings=preparation.warnings,
        )

    def _mapping_request(self, preparation: ScientificPreparation) -> ColumnMappingRequest:
        contexts = mapping_context_options(self.manifest.id)
        role_items = tuple(
            MappingRoleOption(key, label, unique)
            for key, label, unique in role_options(self.manifest.id)
        )
        context_value = preparation.plot_spec.plot_mode if contexts else None
        return ColumnMappingRequest(
            columns=preparation.source_columns,
            role_options=role_items,
            suggested_roles=preparation.assignments,
            energy_kind=context_value,
            energy_kind_options=contexts,
            reasons=preparation.confirmation_reasons,
            context_label="绘图模式" if contexts else None,
            context_value=context_value,
            context_options=contexts,
        )

    def _wrap(self, preparation: ScientificPreparation) -> PreparedTemplate:
        return PreparedTemplate(
            template_id=self.manifest.id,
            renderer_template_id=self.manifest.id,
            source_path=preparation.source_path,
            source_size_bytes=preparation.source_size_bytes,
            source_format=preparation.source_format,
            source_sheet=preparation.source_sheet,
            source_columns=preparation.source_columns,
            row_count=preparation.row_count,
            confidence=preparation.confidence,
            requires_confirmation=preparation.requires_confirmation,
            plan_digest=preparation.plan_digest,
            summary=self._summary(preparation),
            mapping_request=self._mapping_request(preparation),
            payload=preparation,
        )

    def prepare(self, path: str | Path) -> PreparedTemplate:
        try:
            return self._wrap(prepare_scientific(path, self.manifest.id))
        except ScientificWorkflowError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    def confirm_mapping(
        self,
        prepared: PreparedTemplate,
        *,
        assignments: dict[str, str],
        energy_kind: str,
    ) -> PreparedTemplate:
        if set(assignments) != set(prepared.source_columns):
            raise TemplateServiceError(
                "mapping_incomplete", "Every source column must be assigned a role or ignored."
            )
        mapping = ScientificColumnMapping(
            assignments=tuple((column, assignments[column]) for column in prepared.source_columns),
            plot_mode=energy_kind or None,
        )
        try:
            return self._wrap(
                prepare_scientific(
                    prepared.source_path,
                    self.manifest.id,
                    column_mapping=mapping,
                )
            )
        except ScientificWorkflowError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    def render_preview(self, prepared: PreparedTemplate) -> bytes:
        if prepared.requires_confirmation:
            raise TemplateConfirmationRequired()
        try:
            return render_scientific_preview_png(prepared.payload)
        except ScientificPreviewError as exc:
            raise TemplateServiceError(exc.code, str(exc)) from exc

    @staticmethod
    def worker_mapping(prepared: PreparedTemplate) -> dict[str, object] | None:
        preparation: ScientificPreparation = prepared.payload
        if not preparation.mapping_confirmed:
            return None
        return ScientificColumnMapping(
            assignments=preparation.assignments,
            plot_mode=preparation.plot_spec.plot_mode,
        ).to_dict()


class TemplateServiceRegistry:
    """Build workflow services from public template manifests."""

    def __init__(self, registry: TemplateRegistry | None = None) -> None:
        self.registry = registry or TemplateRegistry()
        self._services: dict[str, Any] = {}
        for manifest in self.registry.implemented():
            service_path = manifest.service_path
            if service_path is None or not service_path.is_file():
                raise TemplateServiceError(
                    "workflow_unavailable",
                    f"No local workflow service is registered for {manifest.id}.",
                )
            spec = importlib.util.spec_from_file_location(
                f"origin_sciplot_template_service_{manifest.id}", service_path
            )
            if spec is None or spec.loader is None:
                raise TemplateServiceError(
                    "workflow_load_error", f"Could not load workflow service for {manifest.id}."
                )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            factory = getattr(module, "create_service", None)
            if not callable(factory):
                raise TemplateServiceError(
                    "workflow_factory_missing",
                    f"Template service {service_path.name} must define create_service().",
                )
            self._services[manifest.id] = factory(manifest)

    def implemented(self) -> list[Any]:
        return list(self._services.values())

    def get(self, template_id: str) -> Any:
        try:
            return self._services[template_id]
        except KeyError as exc:
            raise TemplateServiceError("template_unknown", f"Unknown public template: {template_id}") from exc


__all__ = [
    "ColumnMappingRequest",
    "MappingRoleOption",
    "PreparedTemplate",
    "ScientificTemplateService",
    "TemplateConfirmationRequired",
    "TemplateServiceError",
    "TemplateServiceRegistry",
    "TemplateSummary",
    "XpsTemplateService",
]
