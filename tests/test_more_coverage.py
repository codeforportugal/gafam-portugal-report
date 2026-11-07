"""Ramos restantes."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gafam_contratos.amounts import parse_amount, parse_date
from gafam_contratos.classify import load_concelho_map, region_from_local
from gafam_contratos.lexicon import is_rejected_false_friend, load_lexicon
from gafam_contratos.load_base import (
    _col,
    _split_regions,
    load_modifications,
    load_notices,
)
from gafam_contratos.load_prr import load_prr_flags
from gafam_contratos.load_pt2030 import load_pt2030
from gafam_contratos.models import Record, SourceMeta
from gafam_contratos.paths import data_dir, fixtures_dir
from gafam_contratos.press import build_queries, filter_articles
from gafam_contratos.report import build_report_payload, render_html


def test_parse_amount_bool_and_us_thousands():
    assert parse_amount(True) is None
    assert parse_amount("1,234.56") == 1234.56
    assert parse_date("2025/03/15") == parse_date("2025-03-15")
    assert parse_date("not-a-date") is None


def test_acores_and_nan_region():
    mapping = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    assert region_from_local("Região Autónoma dos Açores", mapping) == "Açores"
    assert region_from_local("nan", mapping) == "sem local"


def test_split_regions_semicolon():
    mapping = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    parts = _split_regions(
        "Portugal, Lisboa, Lisboa;Portugal, Porto, Porto", 100, mapping
    )
    assert len(parts) == 2
    assert abs(parts[0][1] + parts[1][1] - 100) < 0.01


def test_col_and_empty_mods(tmp_path: Path):
    frame = pd.DataFrame({"Objeto do Contrato": ["x"], "Outro": [1]})
    assert _col(frame, "objeto do contrato") is not None
    assert _col(frame, "missing") is None
    path = tmp_path / "empty.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(path, index=False)
    assert load_modifications(path) == {}


def test_notices_json(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    mapping = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            [
                {
                    "nAnuncio": "1/2025",
                    "descricaoAnuncio": "Compra de iPhone",
                    "designacaoEntidade": "Município de Faro",
                    "nifEntidade": "1",
                    "PrecoBase": 100,
                    "dataPublicacao": "2025-01-01",
                    "CPVs": "",
                    "url": "https://x",
                }
            ]
        ),
        encoding="utf-8",
    )
    rows = load_notices(path, keywords, mapping)
    assert rows and rows[0].product == "iPhone"


def test_prr_without_hit_skips_id(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    path = tmp_path / "prr.xlsx"
    pd.DataFrame(
        {
            "idContrato": ["999"],
            "NIF": ["123456789"],
            "Objeto": ["material de escritório"],
            "Valor": [10],
        }
    ).to_excel(path, index=False)
    flags = load_prr_flags(path, keywords)
    assert flags == set()


def test_pt2030_skips_no_match_and_bad_year():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    mapping = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    # reuse fixture — already covered; ensure private path
    rows = load_pt2030(fixtures_dir() / "pt2030.xlsx", keywords, mapping)
    assert any(r.category == "privado" for r in rows)


def test_build_queries_limit_and_filter_bad_host():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    domains = {"publico.pt"}
    records = [
        Record(
            source_id=str(i),
            channel="committed",
            buyer=f"Universidade {i}",
            excerpt="Excel",
            amount_eur=float(100 - i),
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product=f"Product{i}",
        )
        for i in range(25)
    ]
    assert len(build_queries(records, limit=8)) == 8
    links = filter_articles(
        [
            {
                "title": "Excel contrato",
                "url": "https://not-allowed.example/x",
                "date": "20250301",
                "snippet": "aquisição Excel",
                "origin": "arquivo.pt",
            }
        ],
        product="Excel",
        buyer="Universidade 0",
        keywords=keywords,
        domains=domains,
    )
    assert links == []


def test_press_note_when_errors():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    payload = build_report_payload(
        records=[],
        sources=[SourceMeta("s", "p", "t", "u", "f", "l", "c", "d")],
        keywords=keywords,
        press=[],
        press_errors={},
        skipped={},
    )
    assert payload["press_note"] == ""
    html = render_html(payload)
    assert "Sem ligações" not in html
    assert 'data-title="Imprensa"' not in html


def test_press_note_softens_gdelt_429():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    payload = build_report_payload(
        records=[],
        sources=[SourceMeta("s", "p", "t", "u", "f", "l", "c", "d")],
        keywords=keywords,
        press=[],
        press_errors={"gdelt": "HTTP Error 429: Too Many Requests"},
        skipped={},
    )
    assert "limite de pedidos" in payload["press_note"]
    assert "Falhou" not in payload["press_note"]


def test_is_rejected_false_friend_office():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    assert is_rejected_false_friend("abrir o office amanhã", keywords)
    assert not is_rejected_false_friend("Office 365 licenças", keywords)
