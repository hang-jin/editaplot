"""Scientific-display contracts for the original, synthetic gallery tables."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from tools import generate_showcase_data as showcase


def _read_table(path: Path) -> tuple[list[str], np.ndarray]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        headers = next(reader)
        return headers, np.asarray(list(reader), dtype=float)


@pytest.mark.parametrize("response_column", [1, 2, 3])
def test_scatter_observations_do_not_form_periodic_residual_stripes(
    tmp_path, monkeypatch, response_column
):
    monkeypatch.setattr(showcase, "OUTPUT", tmp_path)
    showcase.generate_scatter()
    _headers, data = _read_table(tmp_path / "scatter_dense.csv")
    x, response = data[:, 0], data[:, response_column]

    # Remove only the intended broad group trend. A sinusoidal teaching
    # fixture produces strongly correlated residuals and visible stripes.
    slope, intercept = np.polyfit(x, response, 1)
    residuals = response - (slope * x + intercept)
    correlations = [
        abs(np.corrcoef(residuals[:-lag], residuals[lag:])[0, 1])
        for lag in range(1, 13)
    ]
    assert max(correlations) < 0.35
    assert np.std(residuals) > 0.35


def test_scatter_preserves_three_dense_reproducible_groups(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "OUTPUT", tmp_path)
    showcase.generate_scatter()
    first = (tmp_path / "scatter_dense.csv").read_bytes()
    headers, data = _read_table(tmp_path / "scatter_dense.csv")
    showcase.generate_scatter()

    assert (tmp_path / "scatter_dense.csv").read_bytes() == first
    assert headers == ["Independent variable", "Response A", "Response B", "Response C"]
    assert data.shape == (240, 4)
    assert np.isfinite(data).all()
    assert np.all(np.diff(data[:, 0]) > 0)
    assert set(tmp_path.iterdir()) == {tmp_path / "scatter_dense.csv"}


def test_comparable_line_groups_share_explicit_sd_definition(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, "OUTPUT", tmp_path)
    showcase.generate_line_error()
    headers, data = _read_table(tmp_path / "line_error.csv")

    assert headers == ["Time (h)", "Control", "Control_SD", "Treatment", "Treatment_SD"]
    assert data.shape == (13, 5)
    assert np.isfinite(data).all()
    assert np.all(data[:, [2, 4]] > 0)
    assert set(tmp_path.iterdir()) == {tmp_path / "line_error.csv"}
