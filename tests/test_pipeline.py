import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gafam_contratos.paths import schema_path
from gafam_contratos.pipeline import run

BRAZILIAN = ("você", "contato", "registro", "usuário", "gerenciando")
LABELS = ("contrato assinado", "pedido ao mercado")


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
    assert "Palavras-chave" in html
    assert "As algemas das Big Techs" in html
    assert "algema-grid" in html
    assert "Realização: code for portugal" in html
    assert (out / "assets" / "favicon.png").exists()
    assert (out / "assets" / "cc-by-sa.png").exists()
    assert (out / "assets" / "agplv3.png").exists()
    assert "Rejeitadas" not in html
    assert "Classroom" in html
    assert "apoio aprovado" in html
    assert (out / "contratos.csv").exists()
    assert (out / "anuncios.csv").exists()
    assert (out / "pt2030.csv").exists()
    assert (out / "leiria" / "index.html").exists()
    leiria_html = (out / "leiria" / "index.html").read_text(encoding="utf-8")
    assert "Distrito de Leiria" in leiria_html
    assert "Município de Leiria" in leiria_html
    assert "100 maiores" in leiria_html
    assert "mapLeiria" in leiria_html
    assert (out / "leiria" / "concelhos_leiria.geojson").exists()
    assert "As algemas das Big Techs" in leiria_html
    assert "Assinatura VS Pedidos" in leiria_html
    assert set(totals) >= {"2022", "2023", "2024", "2025", "2026"}
