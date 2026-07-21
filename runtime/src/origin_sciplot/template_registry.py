"""Template manifest discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .project_paths import templates_dir


@dataclass(frozen=True)
class TemplateExample:
    """A neutral, bundled teaching dataset declared by a template."""

    id: str
    name: str
    file: str
    description: str
    directory: Path

    @property
    def path(self) -> Path:
        return self.directory / self.file


@dataclass(frozen=True)
class TemplateDataGuide:
    """Human-readable input guidance shown before a file is selected."""

    headline: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    accepted_layouts: tuple[str, ...]
    aliases: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class TemplateManifest:
    id: str
    name: str
    category: str
    version: str
    description: str
    requires_origin: bool
    runner: str
    schema: str
    example: str
    preview: str | None
    outputs: tuple[str, ...]
    status: str
    visibility: str
    workflow: str | None
    service: str | None
    renderer_adapters: dict[str, str]
    family: str
    examples: tuple[TemplateExample, ...]
    blank_template: str | None
    data_guide: TemplateDataGuide
    directory: Path
    raw: dict[str, Any]

    @property
    def runner_path(self) -> Path:
        return self.directory / self.runner

    @property
    def schema_path(self) -> Path:
        return self.directory / self.schema

    @property
    def example_path(self) -> Path:
        return self.directory / self.example

    @property
    def blank_template_path(self) -> Path | None:
        if not self.blank_template:
            return None
        return self.directory / self.blank_template

    @property
    def preview_path(self) -> Path | None:
        if not self.preview:
            return None
        return self.directory / self.preview

    @property
    def service_path(self) -> Path | None:
        if not self.service:
            return None
        return self.directory / self.service


class TemplateRegistryError(RuntimeError):
    """Raised when template discovery fails."""


def _manifest_from_yaml(path: Path) -> TemplateManifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = [
        "id",
        "name",
        "category",
        "version",
        "description",
        "requires_origin",
        "runner",
        "schema",
        "example",
        "outputs",
        "status",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise TemplateRegistryError(f"{path} is missing manifest keys: {', '.join(missing)}")
    example_entries = data.get("examples") or [
        {
            "id": "standard",
            "name_zh": "标准教学样例",
            "file": str(data["example"]),
            "description_zh": "用于查看本模板要求的数据结构和真实预览。",
        }
    ]
    examples: list[TemplateExample] = []
    for index, entry in enumerate(example_entries, start=1):
        if not isinstance(entry, dict) or not entry.get("file"):
            raise TemplateRegistryError(f"{path} has an invalid examples entry at index {index}")
        examples.append(
            TemplateExample(
                id=str(entry.get("id") or f"example_{index}"),
                name=str(entry.get("name_zh") or entry.get("name") or f"教学样例 {index}"),
                file=str(entry["file"]),
                description=str(
                    entry.get("description_zh")
                    or entry.get("description")
                    or "用于查看该模板的数据结构。"
                ),
                directory=path.parent,
            )
        )

    guide_data = data.get("data_guide") or {}
    if not isinstance(guide_data, dict):
        raise TemplateRegistryError(f"{path} data_guide must be a mapping")
    guide = TemplateDataGuide(
        headline=str(
            guide_data.get("headline_zh")
            or guide_data.get("headline")
            or data["description"]
        ),
        required_columns=tuple(str(item) for item in guide_data.get("required_columns", ())),
        optional_columns=tuple(str(item) for item in guide_data.get("optional_columns", ())),
        accepted_layouts=tuple(str(item) for item in guide_data.get("accepted_layouts", ())),
        aliases=tuple(str(item) for item in guide_data.get("aliases", ())),
        notes=tuple(
            str(item)
            for item in (guide_data.get("notes_zh") or guide_data.get("notes") or ())
        ),
    )

    return TemplateManifest(
        id=str(data["id"]),
        name=str(data["name"]),
        category=str(data["category"]),
        version=str(data["version"]),
        description=str(data["description"]),
        requires_origin=bool(data["requires_origin"]),
        runner=str(data["runner"]),
        schema=str(data["schema"]),
        example=str(data["example"]),
        preview=str(data["preview"]) if data.get("preview") else None,
        outputs=tuple(str(item) for item in data["outputs"]),
        status=str(data["status"]),
        visibility=str(data.get("visibility", "public")),
        workflow=str(data["workflow"]) if data.get("workflow") else None,
        service=str(data["service"]) if data.get("service") else None,
        renderer_adapters={
            str(profile): str(template_id)
            for profile, template_id in (data.get("renderer_adapters") or {}).items()
        },
        family=str(data.get("family") or data["category"]),
        examples=tuple(examples),
        blank_template=(str(data["blank_template"]) if data.get("blank_template") else None),
        data_guide=guide,
        directory=path.parent,
        raw=data,
    )


class TemplateRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or templates_dir()
        self._templates: dict[str, TemplateManifest] = {}
        self.reload()

    def reload(self) -> None:
        self._templates.clear()
        if not self.root.exists():
            return
        for manifest_path in sorted(self.root.glob("*/manifest.yaml")):
            manifest = _manifest_from_yaml(manifest_path)
            if manifest.id in self._templates:
                raise TemplateRegistryError(f"duplicate template id: {manifest.id}")
            self._templates[manifest.id] = manifest

    def implemented(self) -> list[TemplateManifest]:
        templates = [
            item
            for item in self._templates.values()
            if item.status == "implemented" and item.visibility == "public"
        ]
        return sorted(
            templates,
            key=lambda item: (int(item.raw.get("ui_order", 1000)), item.name, item.id),
        )

    def internal_implemented(self) -> list[TemplateManifest]:
        return [
            item
            for item in self._templates.values()
            if item.status == "implemented" and item.visibility == "internal"
        ]

    def get(self, template_id: str) -> TemplateManifest:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise TemplateRegistryError(f"unknown template id: {template_id}") from exc
