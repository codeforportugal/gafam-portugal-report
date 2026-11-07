from pathlib import Path

import pandas as pd

from gafam_contratos.load_base import _nif_and_name
from gafam_contratos.load_prr import _as_id, load_prr_flags
from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.paths import data_dir


def test_nif_and_name_pipe_format():
    nif, name = _nif_and_name(
        "nifEntContrato=|descEntContrato=Autoridade Tributária e Aduaneira"
    )
    assert name.startswith("Autoridade Tributária")
    assert nif == ""


def test_nif_and_name_classic():
    nif, name = _nif_and_name("500046117 - Universidade de Lisboa")
    assert nif == "500046117"
    assert "Universidade" in name


def test_as_id_variants():
    assert _as_id(None) == ""
    assert _as_id(float("nan")) == ""
    assert _as_id("11531577.0") == "11531577"
    assert _as_id("99.00") == "99"
    assert _as_id("abc") == "abc"


def test_prr_cd_base_gov(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    path = tmp_path / "prr_nat.xlsx"
    pd.DataFrame(
        {
            "cd_contrato": ["x"],
            "sumario": ["Licenciamento Microsoft Azure"],
            "ds_contrato": ["Contrato assinado"],
            "ds_projeto": ["Cloud"],
            "cd_base_gov": [11531577.0],
            "montante_contratualizado": [1000.0],
        }
    ).to_excel(path, index=False)
    assert "11531577" in load_prr_flags(path, keywords)


def test_prr_nif_without_amount(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    path = tmp_path / "prr_nif.xlsx"
    pd.DataFrame(
        {
            "idContrato": ["", "", ""],
            "NIF": ["123456789", "987654321", ""],
            "Objeto": ["Licença Excel", "Licença Azure", "Licença Teams"],
            "Valor": [None, None, None],
        }
    ).to_excel(path, index=False)
    flags = load_prr_flags(path, keywords)
    assert "123456789" in flags
    assert "987654321" in flags
    assert not any("|" in item for item in flags)
