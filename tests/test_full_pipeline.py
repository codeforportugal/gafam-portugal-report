"""Cobre a corrida --full com rede simulada."""

from __future__ import annotations

import json
from pathlib import Path

from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.load_base import download_year_file
from gafam_contratos.paths import data_dir, fixtures_dir
from gafam_contratos.pipeline import run
from gafam_contratos.press import fetch_arquivo, fetch_gdelt
from gafam_contratos.sciproj import sciproj_source, search_sciproj


def test_download_year_file(tmp_path: Path, monkeypatch):
    resources = [
        {
            "title": "contratos2025.xlsx",
            "format": "xlsx",
            "url": "https://dados.gov.pt/fake/contratos2025.xlsx",
        }
    ]
    monkeypatch.setattr(
        "gafam_contratos.load_base.resolve_resource_urls",
        lambda *a, **k: resources,
    )
    monkeypatch.setattr(
        "gafam_contratos.load_base.cached_get",
        lambda url, cache, name=None, **kw: Path(cache) / (name or "x.xlsx"),
    )
    path = download_year_file("slug", 2025, tmp_path, "contratos")
    assert "contratos2025" in path.name


def test_download_year_file_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "gafam_contratos.load_base.resolve_resource_urls",
        lambda *a, **k: [],
    )
    try:
        download_year_file("slug", 2025, tmp_path, "contratos")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_fetch_arquivo_and_gdelt(monkeypatch):
    arquivo_payload = {
        "response_items": [
            {
                "title": "t",
                "originalURL": "https://publico.pt/x",
                "tstamp": "20250301",
                "snippet": "Excel",
            }
        ]
    }
    gdelt_payload = {
        "articles": [
            {
                "title": "t2",
                "url": "https://eco.sapo.pt/y",
                "seendate": "20260901T120000Z",
            }
        ]
    }

    def fake_get(url: str, **kwargs: object) -> bytes:
        _ = kwargs
        if "arquivo" in url:
            return json.dumps(arquivo_payload).encode()
        return json.dumps(gdelt_payload).encode()

    monkeypatch.setattr("gafam_contratos.press.http_get", fake_get)
    assert fetch_arquivo("Excel")[0]["origin"] == "arquivo.pt"
    assert fetch_gdelt("Azure")[0]["origin"] == "gdelt"


def test_run_full_mocked(tmp_path: Path, monkeypatch):
    fix = fixtures_dir()

    def fake_download(dataset: str, year: int, cache: Path, prefix: str, **kw: object):
        _ = dataset, cache, kw
        if year != 2025:
            raise FileNotFoundError(year)
        mapping = {
            "contratos": fix / "contratos.xlsx",
            "anuncios": fix / "anuncios.xlsx",
            "modcontrats": fix / "modificacoes.xlsx",
        }
        return mapping[prefix]

    monkeypatch.setattr("gafam_contratos.pipeline.download_year_file", fake_download)
    monkeypatch.setattr(
        "gafam_contratos.pipeline.cached_get",
        lambda url, cache, name=None, **kw: (
            fix / "prr.xlsx" if name == "prr.xlsx" else fix / "pt2030.xlsx"
        ),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.resolve_resource_urls",
        lambda *a, **k: [
            {"format": "xlsx", "url": "https://x/prr.xlsx", "title": "prr"}
        ],
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.search_sciproj",
        lambda *a, **k: ([], {"sem montante": 1, "correspondência incerta": 0}),
    )
    monkeypatch.setattr(
        "gafam_contratos.pipeline.gather_press",
        lambda *a, **k: ([], {}),
    )
    out = run(full=True, out_dir=tmp_path, sleeper=lambda _s: None)
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert data["totals"]["2025"]["committed"] == 19000.0
    assert sciproj_source().id == "sciproj"


def test_sciproj_ldjson():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    html = """
    <script type="application/ld+json">
    {"name": "Azure research", "funding": "1000", "description": "Azure cloud", "funder": "FCT"}
    </script>
    """

    def fetcher(url: str, **kwargs: object) -> bytes:
        _ = url, kwargs
        return html.encode()

    kept, skipped = search_sciproj(["Azure"], keywords, fetcher=fetcher)
    assert kept and kept[0].amount_eur == 1000
    _ = skipped
