from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from PIL import Image

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.reference_figure import (  # noqa: E402
    ReferenceFigureError,
    ReferenceFigureSpec,
    inspect_reference_image,
    parse_reference_figure_spec,
)


def _write_image(path: Path, image_format: str, *, size: tuple[int, int] = (12, 8)) -> Path:
    Image.new("RGB", size, (31, 90, 132)).save(path, format=image_format)
    return path


def _spec_payload(reference: dict[str, object], *, bound: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "reference": reference,
        "layout": {
            "archetype": "single_chart",
            "aspect_ratio_class": "wide",
            "panels": [
                {
                    "id": "main",
                    "evidence_role": "hero",
                    "coordinate_system": "cartesian_2d",
                    "relative_bbox": [0.0, 0.0, 1.0, 1.0],
                    "shared_axis_group": None,
                }
            ],
        },
        "marks": [
            {
                "id": "observed",
                "panel_id": "main",
                "kind": "symbol",
                "evidence_role": "primary",
                "essential": True,
                "confidence": 0.96,
            },
            {
                "id": "calculated",
                "panel_id": "main",
                "kind": "line",
                "evidence_role": "validation",
                "essential": True,
                "confidence": 0.93,
            },
        ],
        "encodings": [
            {
                "id": "observed_y",
                "mark_id": "observed",
                "channel": "y",
                "semantic_role": "observed_intensity",
                "data_binding": "binding_yobs" if bound else None,
                "confidence": 0.91,
            },
            {
                "id": "calculated_y",
                "mark_id": "calculated",
                "channel": "y",
                "semantic_role": "calculated_intensity",
                "data_binding": "binding_ycalc",
                "confidence": 0.9,
            },
        ],
        "style": {
            "palette_family": "navy_cyan_gold",
            "palette_id": None,
            "line_weight": "medium",
            "marker_density": "dense",
            "fill_transparency": "none",
            "legend_position": "inside",
            "legend_frame": False,
            "grid": "none",
            "background": "white",
            "typography_hierarchy": "publication_informed",
        },
        "text_roles": [
            {
                "id": "x_axis_role",
                "panel_id": "main",
                "role": "x_title",
                "observed_present": True,
                "copy_policy": "user_data_or_confirmation_only",
                "binding_id": "binding_x_title",
                "confidence": 0.89,
            }
        ],
        "essential_features": [
            {
                "id": "observed_curve",
                "feature_role": "primary_measurement",
                "mark_ids": ["observed"],
                "required_encoding_ids": ["observed_y"],
            },
            {
                "id": "calculated_curve",
                "feature_role": "fit_validation",
                "mark_ids": ["calculated"],
                "required_encoding_ids": ["calculated_y"],
            },
        ],
        "confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_contract_sha256": None,
        },
    }


@pytest.mark.parametrize(
    ("suffix", "image_format", "media_type"),
    [
        (".png", "PNG", "image/png"),
        (".jpg", "JPEG", "image/jpeg"),
        (".tif", "TIFF", "image/tiff"),
    ],
)
def test_inspect_reference_image_accepts_supported_single_frame_formats(
    tmp_path: Path,
    suffix: str,
    image_format: str,
    media_type: str,
) -> None:
    source = _write_image(tmp_path / f"private-reference{suffix}", image_format)

    metadata = inspect_reference_image(source)

    assert metadata.media_type == media_type
    assert metadata.pixel_width == 12
    assert metadata.pixel_height == 8
    assert metadata.pixel_count == 96
    assert metadata.frame_count == 1
    assert len(metadata.sha256) == 64
    serialized = metadata.to_dict()
    assert "path" not in serialized
    assert "file_name" not in serialized
    assert "private-reference" not in str(serialized)


def test_inspect_reference_image_checks_file_size_before_decode(tmp_path: Path) -> None:
    source = _write_image(tmp_path / "large.png", "PNG")

    with pytest.raises(ReferenceFigureError) as raised:
        inspect_reference_image(source, max_bytes=source.stat().st_size - 1)

    assert raised.value.code == "reference_image_too_large"
    assert str(source) not in str(raised.value)


def test_inspect_reference_image_enforces_pixel_limit(tmp_path: Path) -> None:
    source = _write_image(tmp_path / "pixels.png", "PNG", size=(11, 10))

    with pytest.raises(ReferenceFigureError) as raised:
        inspect_reference_image(source, max_pixels=100)

    assert raised.value.code == "reference_pixel_limit_exceeded"


def test_inspect_reference_image_rejects_non_image_without_leaking_path(tmp_path: Path) -> None:
    source = tmp_path / "secret-reference.png"
    source.write_bytes(b"not an image")

    with pytest.raises(ReferenceFigureError) as raised:
        inspect_reference_image(source)

    assert raised.value.code == "reference_image_invalid"
    assert str(source) not in str(raised.value)
    assert source.name not in str(raised.value)


def test_inspect_reference_image_rejects_multiframe_tiff(tmp_path: Path) -> None:
    source = tmp_path / "stack.tif"
    frames = [Image.new("RGB", (4, 4), color) for color in ("red", "blue")]
    frames[0].save(source, save_all=True, append_images=frames[1:], format="TIFF")

    with pytest.raises(ReferenceFigureError) as raised:
        inspect_reference_image(source)

    assert raised.value.code == "reference_multiframe_unsupported"


def test_reference_spec_is_canonical_path_free_and_initially_blocked(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())

    spec = parse_reference_figure_spec(payload, image_metadata=metadata)

    assert spec.confirmed is False
    assert len(spec.contract_sha256) == 64
    assert len(spec.spec_sha256) == 64
    assert "path" not in str(spec.to_dict()).casefold()
    assert "ocr_text" not in str(spec.to_dict()).casefold()
    with pytest.raises(ReferenceFigureError) as raised:
        spec.require_renderable()
    assert raised.value.code == "reference_confirmation_required"


def test_reference_spec_hash_is_independent_of_input_key_order(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    reversed_payload = dict(reversed(list(payload.items())))

    first = ReferenceFigureSpec.from_dict(payload)
    second = ReferenceFigureSpec.from_dict(reversed_payload)

    assert first.contract_sha256 == second.contract_sha256
    assert first.spec_sha256 == second.spec_sha256


def test_reference_spec_to_dict_returns_a_detached_copy(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    spec = ReferenceFigureSpec.from_dict(_spec_payload(metadata.to_dict()))
    detached = spec.to_dict()
    detached["layout"]["panels"][0]["id"] = "changed"

    assert spec.to_dict()["layout"]["panels"][0]["id"] == "main"


def test_confirm_binds_current_contract_hash_and_opens_render_gate(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    initial = ReferenceFigureSpec.from_dict(
        _spec_payload(metadata.to_dict()),
        image_metadata=metadata,
    )

    confirmed = initial.confirm()

    assert confirmed.confirmed is True
    assert confirmed.contract_sha256 == initial.contract_sha256
    assert confirmed.spec_sha256 != initial.spec_sha256
    assert (
        confirmed.to_dict()["confirmation"]["confirmed_contract_sha256"]
        == initial.contract_sha256
    )
    confirmed.require_renderable()


def test_unbound_essential_feature_cannot_be_confirmed(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    spec = ReferenceFigureSpec.from_dict(_spec_payload(metadata.to_dict(), bound=False))

    with pytest.raises(ReferenceFigureError) as raised:
        spec.confirm()

    assert raised.value.code == "reference_essential_feature_unbound"


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "code",
        "script",
        "python",
        "labtalk",
        "ocr_text",
        "private_path",
        "absolute_path",
        "render_command",
        "powershell",
        "argv",
    ],
)
def test_reference_spec_rejects_forbidden_fields_recursively(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    payload["style"][forbidden_key] = "untrusted"

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_spec_forbidden_field"


def test_reference_spec_rejects_unknown_fields_with_strict_schema(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    payload["style"]["shadow"] = True

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_spec_schema_invalid"


def test_reference_spec_rejects_raw_text_and_absolute_path_values(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    separator = chr(92)
    payload["text_roles"][0]["render_text"] = (
        "C:" + separator + "private" + separator + "reference.png"
    )

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_spec_schema_invalid"


def test_reference_spec_rejects_mismatched_image_metadata(tmp_path: Path) -> None:
    first = inspect_reference_image(_write_image(tmp_path / "first.png", "PNG"))
    second = inspect_reference_image(
        _write_image(tmp_path / "second.png", "PNG", size=(13, 8))
    )

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(_spec_payload(first.to_dict()), image_metadata=second)

    assert raised.value.code == "reference_metadata_mismatch"


def test_reference_spec_rejects_forged_confirmation_digest(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    payload["confirmation"] = {
        "required": True,
        "confirmed": True,
        "confirmed_contract_sha256": "0" * 64,
    }

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_confirmation_hash_mismatch"


def test_reference_spec_rejects_broken_relational_references(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    payload["marks"][0]["panel_id"] = "missing_panel"

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_mark_panel_missing"


def test_reference_spec_rejects_duplicate_ids(tmp_path: Path) -> None:
    metadata = inspect_reference_image(_write_image(tmp_path / "reference.png", "PNG"))
    payload = _spec_payload(metadata.to_dict())
    duplicate = copy.deepcopy(payload["marks"][0])
    payload["marks"].append(duplicate)

    with pytest.raises(ReferenceFigureError) as raised:
        ReferenceFigureSpec.from_dict(payload)

    assert raised.value.code == "reference_spec_duplicate_id"
