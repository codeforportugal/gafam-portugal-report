from pathlib import Path
import zipfile

from gafam_contratos.load_base import _read_table
import pandas as pd


def test_read_table_zip(tmp_path: Path):
    xlsx = tmp_path / "inner.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(xlsx, index=False)
    zipped = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.write(xlsx, arcname="inner.xlsx")
    frame = _read_table(zipped)
    assert list(frame.columns) == ["a"]


def test_read_table_empty_zip(tmp_path: Path):
    zipped = tmp_path / "empty.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("readme.txt", "no table")
    try:
        _read_table(zipped)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
