import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gafam_contratos.paths import schema_path
from gafam_contratos.pipeline import run

BRAZILIAN = ("você", "contato", "registro", "usuário", "gerenciando")
LABELS = ("contrato assinado", "pedido ao mercado")


def test_brand_dir_falls_back_without_commons(monkeypatch, tmp_path: Path):
    from gafam_contratos import report

    lone = tmp_path / "repo"
    lone.mkdir()
    monkeypatch.setattr(report, "project_root", lambda: lone)
    assert report._brand_dir() == report.data_dir() / "brand"


def test_acores_page_uses_region(tmp_path: Path):
    from gafam_contratos.lexicon import load_lexicon
    from gafam_contratos.models import Record, SourceMeta
    from gafam_contratos.paths import data_dir
    from gafam_contratos.pipeline import _write_area_reports

    _write_area_reports(
        tmp_path,
        records=[
            Record(
                source_id="1",
                channel="committed",
                buyer="Governo Regional dos Açores",
                excerpt="Azure",
                amount_eur=10,
                region="Açores",
                category="administração regional",
                vendor="Microsoft",
                fundos="",
                year=2025,
                headline=True,
                product="Azure",
            )
        ],
        sources=[
            SourceMeta(
                id="base-contratos",
                publisher="IMPIC",
                title="Portal Base",
                url="https://dados.gov.pt/x",
                file_name="x",
                licence="DP",
                coverage="2022–2026",
                updated="2026-01-01",
            )
        ],
        keywords=load_lexicon(data_dir() / "lexicon.yml"),
        skipped={},
        root_data=data_dir(),
    )
    html = (tmp_path / "acores" / "index.html").read_text(encoding="utf-8")
    assert "Governo Regional dos Açores" in html
    assert "id='mapLeiria'" in html or 'id="mapLeiria"' in html
    fontes = html.split('data-title="Fontes"', 1)[1]
    assert "Contagem das algemas" in fontes
    assert "Contagem das algemas" not in html.split('data-title="Fontes"', 1)[0]


def test_fixture_pipeline(tmp_path: Path):
    out = run(full=False, out_dir=tmp_path)
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)

    totals = data["totals"]
    assert totals["2025"]["committed"] == 19000.0
    assert totals["2025"]["requested"] == 8000.0
    assert totals["2025"]["grants"] == 50000.0
    assert totals["2026"]["committed"] == 25000.0
    assert data["prr"]["2025"] == 12000.0

    # Framework ceiling and private grant excluded from headline sums
    assert all(
        not (r["source_id"] == "1002" and r["headline"]) for r in data["records"]
    )
    private = [r for r in data["records"] if r["source_id"] == "LISBOA-FEDER-0002"]
    assert private and private[0]["headline"] is False

    html = (out / "index.html").read_text(encoding="utf-8")
    for label in LABELS:
        assert label in html
    for word in BRAZILIAN:
        assert word not in html.lower()
    assert 'id="chartYears"' in html
    assert 'id="mapRegion"' in html
    assert "O que procurámos" in html
    assert "As algemas" in html
    assert "Pedidos ao mercado ficam fora da conta" in html
    assert "uscode.house.gov/us/usc/t18/s2713" in html
    assert "anos com contratos assinados no setor público, 2022–2026" in html
    assert "cortar esses serviços" not in html
    assert "algema-grid" in html
    assert "Realização: code for portugal" in html
    assert (
        (out / "assets" / "favicon.png").exists()
        and (out / "assets" / "cc-by-sa.png").exists()
        and (out / "assets" / "agplv3.png").exists()
    )
    assert "Rejeitadas" not in html
    assert "Classroom" in html
    assert "apoio aprovado" in html
    assert (
        (out / "contratos.csv").exists()
        and (out / "anuncios.csv").exists()
        and (out / "pt2030.csv").exists()
    )
    assert (out / "leiria" / "index.html").exists()
    assert (out / "porto" / "index.html").exists() and (
        out / "acores" / "acores.geojson"
    ).exists()
    assert not (out / "norte" / "index.html").exists()
    assert (
        'href="porto/"' in html
        and 'href="acores/"' in html
        and 'href="norte/"' not in html
    )
    assert "Abrir Leiria" not in html
    leiria_html = (out / "leiria" / "index.html").read_text(encoding="utf-8")
    assert "Distrito de Leiria" in leiria_html
    assert "Município de Leiria" in leiria_html
    assert "100 maiores" in leiria_html
    assert "mapLeiria" in leiria_html
    assert (out / "leiria" / "leiria.geojson").exists()
    assert (out / "porto" / "porto.geojson").exists()
    assert "As algemas" in leiria_html
    assert "uscode.house.gov/us/usc/t50/s1702" in leiria_html
    assert "anos com contratos assinados no setor público, 2022–2026" in leiria_html
    assert "O que foi assinado e o que foi pedido" in leiria_html
    assert "Onde o corte seria mais grave" in leiria_html
    assert set(totals) >= {"2022", "2023", "2024", "2025", "2026"}
