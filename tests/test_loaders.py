import json
from pathlib import Path

from gafam_contratos.classify import load_concelho_map
from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.load_base import (
    load_contracts,
    load_modifications,
    load_notices,
    match_text,
    resolve_resource_urls,
)
from gafam_contratos.load_prr import load_prr_flags, prr_source
from gafam_contratos.load_pt2030 import load_pt2030, pt2030_source
from gafam_contratos.paths import data_dir, fixtures_dir


def test_fixture_loaders():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    cmap = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    fix = fixtures_dir()
    mods = load_modifications(fix / "modificacoes.xlsx")
    assert mods["1001"] == 12000.0
    prr = load_prr_flags(fix / "prr.xlsx", keywords)
    assert "1001" in prr
    contracts = load_contracts(fix / "contratos.xlsx", keywords, cmap, mods, prr)
    assert any(c.source_id == "1001" and c.amount_eur == 12000 for c in contracts)
    assert any(c.source_id == "1002" and c.headline is False for c in contracts)
    notices = load_notices(fix / "anuncios.xlsx", keywords, cmap)
    assert notices and notices[0].channel == "requested"
    grants = load_pt2030(fix / "pt2030.xlsx", keywords, cmap)
    assert any(g.headline is False for g in grants)
    assert match_text("Excel", keywords) is not None
    assert pt2030_source().id == "pt2030"
    assert prr_source().id == "prr-contratos"


def test_load_modifications_json(tmp_path: Path):
    path = tmp_path / "mods.json"
    path.write_text(
        json.dumps([{"idContrato": "9", "modifContratoPrecoAlterado": 11}]),
        encoding="utf-8",
    )
    assert load_modifications(path)["9"] == 11.0


def test_resolve_resource_urls(monkeypatch):
    payload = {
        "resources": [
            {"title": "contratos2025.xlsx", "format": "xlsx", "url": "https://x/a.xlsx"}
        ]
    }

    def fake_get(url: str, **kwargs: object) -> bytes:
        _ = url, kwargs
        return json.dumps(payload).encode()

    monkeypatch.setattr("gafam_contratos.load_base.http_get", fake_get)
    rows = resolve_resource_urls("slug")
    assert rows[0]["title"].startswith("contratos")
