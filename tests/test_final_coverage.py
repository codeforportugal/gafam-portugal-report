"""Últimos ramos para 100%."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gafam_contratos.classify import load_concelho_map
from gafam_contratos.lexicon import Keyword, is_rejected_false_friend, load_lexicon
from gafam_contratos.load_base import load_contracts, load_modifications, load_notices
from gafam_contratos.load_prr import _col as prr_col
from gafam_contratos.load_prr import load_prr_flags
from gafam_contratos.load_pt2030 import _col as pt_col
from gafam_contratos.load_pt2030 import load_pt2030
from gafam_contratos.models import PressLink, Record, SourceMeta
from gafam_contratos.paths import data_dir
from gafam_contratos.pipeline import _run_full
from gafam_contratos.press import build_queries, filter_articles, load_press_domains
from gafam_contratos.report import _fmt_date, build_report_payload, render_html
from gafam_contratos.sciproj import _parse_html_rows, sciproj_source


def test_lexicon_reject_loop_no_hit():
    keywords = [
        Keyword("Excel", "Microsoft", "match"),
        Keyword("meta", "", "reject"),
    ]
    assert is_rejected_false_friend("meta do plano", keywords)
    assert not is_rejected_false_friend("texto limpo", keywords)


def test_contracts_skip_bad_year_and_amount(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    path = tmp_path / "c.xlsx"
    pd.DataFrame(
        {
            "idContrato": ["1", "2", "3", "4"],
            "objectoContrato": ["Excel", "Excel", "Excel", "Excel"],
            "descContrato": ["", "", "", ""],
            "adjudicante": ["U", "U", "U", "U"],
            "precoContratual": ["10", "xyz", "20", None],
            "localExecucao": ["Portugal, Lisboa, Lisboa"] * 4,
            "dataCelebracaoContrato": [
                "15/03/2021",
                "15/03/2025",
                "15/03/2025",
                "15/03/2025",
            ],
            "cpv": ["", "", "", ""],
        }
    ).to_excel(path, index=False)
    rows = load_contracts(path, keywords, cmap, {}, set())
    assert len(rows) == 1
    assert rows[0].amount_eur == 20

    path2 = tmp_path / "c2.xlsx"
    pd.DataFrame(
        {
            "idContrato": ["9"],
            "objectoContrato": ["Excel"],
            "descContrato": [""],
            "adjudicante": ["Município de Faro"],
            "precoContratual": ["15"],
            "localExecucao": [""],
            "dataCelebracaoContrato": ["15/03/2025"],
            "cpv": [""],
        }
    ).to_excel(path2, index=False)
    inferred = load_contracts(path2, keywords, cmap, {}, set())
    assert len(inferred) == 1
    assert inferred[0].place == "Faro"


def test_notices_skip_paths(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    path = tmp_path / "n.xlsx"
    pd.DataFrame(
        {
            "nAnuncio": ["1", "2", "3"],
            "descricaoAnuncio": ["papel", "iPhone", "iPhone"],
            "designacaoEntidade": ["M", "M", "M"],
            "nifEntidade": ["1", "2", "3"],
            "PrecoBase": [1, None, 5],
            "dataPublicacao": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "CPVs": ["", "", ""],
            "url": ["", "", ""],
        }
    ).to_excel(path, index=False)
    rows = load_notices(path, keywords, cmap)
    assert len(rows) == 1


def test_mods_json_wrapped_and_empty_cid(tmp_path: Path):
    path = tmp_path / "m.json"
    path.write_text(
        '{"data":[{"idContrato":"","modifContratoPrecoAlterado":1},'
        '{"idContrato":"2","modifContratoPrecoAlterado":3}]}',
        encoding="utf-8",
    )
    assert load_modifications(path) == {"2": 3.0}


def test_prr_and_pt_col_substring():
    frame = pd.DataFrame({"Objeto do Contrato XYZ": ["a"], "Valor Total": [1]})
    assert prr_col(frame, "objeto") is not None
    assert prr_col(frame, "zzz") is None
    assert pt_col(frame, "valor") is not None
    assert pt_col(frame, "zzz") is None


def test_prr_hit_adds_nif(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    path = tmp_path / "p.xlsx"
    pd.DataFrame(
        {
            "idContrato": [""],
            "NIF": ["123456789"],
            "Objeto": ["Licença Excel"],
            "Valor": [10],
        }
    ).to_excel(path, index=False)
    assert "123456789" in load_prr_flags(path, keywords)


def test_pt2030_skips(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    path = tmp_path / "g.xlsx"
    pd.DataFrame(
        {
            "Código da Operação | Operation Code": ["A", "B", "C", "D"],
            "Nome do Beneficiário | Beneficiary s name": ["U", "U", "U", "U"],
            "Nome da operação | Name of the operation": [
                "papel",
                "Excel",
                "Excel",
                "Excel",
            ],
            "Finalidade da operação | Purpose of the Operation": ["", "", "", ""],
            "Data Início | Start Date": [
                "2025-01-01",
                "2021-01-01",
                "2025-01-01",
                "2025-01-01",
            ],
            "Fundo Total Aprovado | Total Approved Fund [€ - EUR]": [
                1,
                1,
                None,
                None,
            ],
            "Custo Total da Operação | Total Cost of the Operation [€ - EUR]": [
                1,
                1,
                None,
                9,
            ],
            "NUTS II | NUTS 2": ["Norte"] * 4,
        }
    ).to_excel(path, index=False)
    rows = load_pt2030(path, keywords, cmap)
    assert len(rows) == 1
    assert rows[0].source_id == "D"
    assert rows[0].amount_eur == 9


def test_pipeline_prr_resolve_fails(monkeypatch, tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    domains = load_press_domains(data_dir() / "press_domains.txt")

    monkeypatch.setattr(
        "gafam_contratos.pipeline.download_year_file",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.resolve_resource_urls",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no")),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.cached_get",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no")),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.search_sciproj",
        lambda *a, **k: ([], {}),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.gather_press",
        lambda *a, **k: ([], {}),
    )
    monkeypatch.setattr("gafam_contratos.pipeline.cache_dir", lambda: tmp_path)
    records, sources, skipped, press, errors = _run_full(
        keywords,
        cmap,
        domains,
        sleeper=lambda _s: None,
    )
    assert records == []
    assert sources
    _ = skipped, press, errors


def test_build_queries_empty_and_fmt_date():
    assert build_queries([]) == []
    assert _fmt_date("2025-01-02") == "02-01-2025"
    assert _fmt_date("nodate") == "nodate"


def test_press_note_empty_errors_many_links():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    press = [
        PressLink("t", f"https://x/{i}", "2025-01-01", "Excel", "U", ["arquivo.pt"])
        for i in range(10)
    ]
    payload = build_report_payload(
        records=[],
        sources=[SourceMeta("s", "p", "t", "u", "f", "l", "c", "d")],
        keywords=keywords,
        press=press,
        press_errors={},
        skipped={},
    )
    assert payload["press_note"] == ""
    html = render_html(payload)
    assert "Na imprensa" not in html


def test_filter_requires_buyer_or_proc():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    domains = {"publico.pt"}
    links = filter_articles(
        [
            {
                "title": "Excel sozinho",
                "url": "https://www.publico.pt/z",
                "date": "20250301",
                "snippet": "Excel",
                "origin": "arquivo.pt",
            }
        ],
        product="Excel",
        buyer="Universidade Inexistente XYZ",
        keywords=keywords,
        domains=domains,
    )
    assert links == []


def test_sciproj_bad_json_and_source():
    rows = _parse_html_rows(
        '<script type="application/ld+json">{bad</script><div>Azure 10 €</div>'
    )
    assert rows
    assert sciproj_source().publisher.startswith("FCT")


def test_col_partial_key_match():
    from gafam_contratos.load_base import _col, _split_regions

    frame = pd.DataFrame({"Preço Contratual Final": [1]})
    assert _col(frame, "preço contratual") is not None
    from gafam_contratos.load_pt2030 import _col as pt

    exact = pd.DataFrame({"nome da operação": ["x"]})
    assert pt(exact, "nome da operação") == "nome da operação"
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    parts = _split_regions(
        "Portugal, Lisboa, Lisboa|Portugal, Porto, Porto",
        100,
        cmap,
    )
    assert len(parts) == 2


def test_notices_wrong_year(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    path = tmp_path / "ny.xlsx"
    pd.DataFrame(
        {
            "nAnuncio": ["9"],
            "descricaoAnuncio": ["iPhone"],
            "designacaoEntidade": ["M"],
            "nifEntidade": ["1"],
            "PrecoBase": [5],
            "dataPublicacao": ["2021-01-01"],
            "CPVs": [""],
            "url": [""],
        }
    ).to_excel(path, index=False)
    assert load_notices(path, keywords, cmap) == []


def test_build_queries_skips_duplicate_product_buyer():
    records = [
        Record(
            source_id="1",
            channel="committed",
            buyer="Universidade",
            excerpt="Excel",
            amount_eur=20,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel",
        ),
        Record(
            source_id="2",
            channel="committed",
            buyer="Universidade",
            excerpt="Excel",
            amount_eur=10,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel",
        ),
    ]
    assert len(build_queries(records)) == 1


def test_prr_hit_with_cid_no_nif(tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    path = tmp_path / "pn.xlsx"
    pd.DataFrame(
        {
            "idContrato": ["555"],
            "NIF": [""],
            "Objeto": ["Excel"],
            "Valor": [1],
        }
    ).to_excel(path, index=False)
    flags = load_prr_flags(path, keywords)
    assert "555" in flags


def test_date_wrong_year_and_merge_duplicate_source():
    from gafam_contratos.press import _date_ok, merge_press

    assert _date_ok("20210301120000") is None
    a = PressLink("t", "https://x", "2025-01-01", "Excel", "U", ["arquivo.pt"])
    b = PressLink("t", "https://x", "2025-01-01", "Excel", "U", ["arquivo.pt"])
    merged = merge_press([a, b])
    assert merged[0].sources == ["arquivo.pt"]


def test_sciproj_json_list_payload():
    rows = _parse_html_rows('<script type="application/ld+json">[]</script>')
    assert rows == []


def test_pipeline_prr_without_xlsx(monkeypatch, tmp_path: Path):
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    domains = load_press_domains(data_dir() / "press_domains.txt")
    monkeypatch.setattr(
        "gafam_contratos.pipeline.download_year_file",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.resolve_resource_urls",
        lambda *a, **k: [{"format": "json", "url": "https://x", "title": "x"}],
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.cached_get",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no")),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.search_sciproj",
        lambda *a, **k: ([], {}),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.gather_press",
        lambda *a, **k: ([], {}),
    )
    monkeypatch.setattr("gafam_contratos.pipeline.cache_dir", lambda: tmp_path)
    records, *_rest = _run_full(keywords, cmap, domains, sleeper=lambda _s: None)
    assert records == []
