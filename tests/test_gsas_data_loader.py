from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = PRODUCT_ROOT / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.data_loader import DataLoadError, load_table  # noqa: E402


def test_loads_documented_gsas_ii_powder_csv_with_metadata_prefix(tmp_path: Path) -> None:
    source = tmp_path / "powder.csv"
    source.write_text(
        "\n".join(
            [
                '"Histogram","PWDR sample"',
                '"Instparm: Type","PXC"',
                '"Instparm: Lam",1.5406',
                '"Samparm: Temperature",298.15',
                '"x","y_obs","weight","y_calc","y_bkg","Q"',
                "20,101,0.04,99,12,1.42",
                "21,115,0.04,113,13,1.49",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    before = source.read_bytes()

    loaded = load_table(source)

    assert loaded.source_profile == "gsas_ii_powder_csv"
    assert loaded.header_row_number == 5
    assert loaded.columns == ("x", "y_obs", "weight", "y_calc", "y_bkg", "Q")
    assert loaded.metadata[0] == ("Histogram", "PWDR sample")
    assert len(loaded.frame) == 2
    assert loaded.source_sha256 == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before


def test_loads_sparse_gsas_ii_publication_csv_without_inventing_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "publication.csv"
    source.write_text(
        "\n".join(
            [
                "Used,X (2theta),Obs,Calc,Bkg,Diff,Phase alpha,tick-pos,diff/sigma,Axis-limits",
                "1,20,101,99,12,-8,20.4,alpha,0.2,20",
                "1,21,115,113,13,-7,21.3,-1.5,0.3,80",
                "1,22,120,118,13,-6",
                "1,23,119,118,13,-5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_table(source)

    assert loaded.source_profile == "gsas_ii_publication_csv"
    assert loaded.header_row_number == 1
    assert loaded.frame.loc[2, "Phase alpha"] == ""
    assert loaded.frame.loc[3, "Axis-limits"] == ""
    assert tuple(loaded.frame["Obs"]) == ("101", "115", "120", "119")


def test_generic_ragged_csv_remains_an_error(tmp_path: Path) -> None:
    source = tmp_path / "generic.csv"
    source.write_text("X,A,B\n1,2,3\n2,4\n", encoding="utf-8")

    with pytest.raises(DataLoadError) as error:
        load_table(source)

    assert error.value.code == "malformed_row"


def test_unrelated_metadata_prefix_is_not_silently_skipped(tmp_path: Path) -> None:
    source = tmp_path / "unknown.csv"
    source.write_text(
        '"Title","notes"\n"x","y_obs","weight","y_calc","y_bkg","Q"\n1,2,3,4,5,6\n',
        encoding="utf-8",
    )

    with pytest.raises(DataLoadError) as error:
        load_table(source)

    assert error.value.code == "malformed_row"
