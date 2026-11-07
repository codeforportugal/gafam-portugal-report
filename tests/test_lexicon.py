from pathlib import Path

from gafam_contratos.lexicon import (
    find_match,
    fold,
    is_rejected_false_friend,
    keywords_for_report,
    load_lexicon,
)
from gafam_contratos.paths import data_dir


def test_fold_strips_accents():
    assert fold("Excelência") == "excelencia"


def test_excelencia_does_not_match_excel():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    assert find_match("Projecto de excelência académica", keywords) is None
    assert is_rejected_false_friend("Projecto de excelência académica", keywords)


def test_excel_matches():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    hit = find_match("Aquisição de Microsoft Excel", keywords)
    assert hit is not None
    assert hit.term == "Excel"
    assert hit.vendor == "Microsoft"


def test_bare_meta_rejected():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    assert find_match("atingir a meta do plano", keywords) is None
    assert is_rejected_false_friend("atingir a meta do plano", keywords)


def test_meta_platforms_matches():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    hit = find_match("Contrato Meta Platforms", keywords)
    assert hit is not None
    assert hit.term == "Meta Platforms"


def test_azure_preferred_over_microsoft_brand():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    hit = find_match("Cloud Microsoft Azure", keywords)
    assert hit is not None
    assert hit.term == "Azure"


def test_exchange_hardware_rejected_software_kept():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    assert (
        find_match(
            "AQUISIÇÃO DE SERVIÇOS DE EXCHANGE DE 05EA COCKPIT HUD CAMERAS",
            keywords,
        )
        is None
    )
    assert (
        find_match("CLAFA - DMSA - GTF16-AD-EXCHANGE 12EA LEFRA P/N 182900-3", keywords)
        is None
    )
    assert find_match("A32 - AD - EXCHANGE BEACONS VADR P/N DK120", keywords) is None
    assert find_match("SERVIÇO PARA O EXCHANGE DE 02EA COMMON COLOR", keywords) is None
    hit = find_match(
        "Aquisição de caixas de correio eletrónico do tipo Exchange Online Microsoft",
        keywords,
    )
    assert hit is not None
    assert hit.term == "Exchange"
    # bare Exchange without software/hardware markers still matches
    bare = find_match("Migração para Exchange", keywords)
    assert bare is not None and bare.term == "Exchange"


def test_keywords_for_report(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    rows = keywords_for_report(keywords)
    assert any(r["kind"] == "match" for r in rows)
    assert any(r["kind"] == "reject" for r in rows)
    _ = tmp_path
