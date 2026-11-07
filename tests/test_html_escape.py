from gafam_contratos.report import _esc, _safe_href, render_html


def _base_payload(**overrides):
    payload = {
        "totals": {
            str(year): {"committed": 0.0, "requested": 0.0, "grants": 0.0}
            for year in (2022, 2023, 2024, 2025, 2026)
        },
    }
    payload.update(
        {
            "keywords": [
                {"pattern": "<b>Excel</b>", "vendor": "Microsoft", "kind": "match"},
                {"pattern": "meta", "vendor": "", "kind": "reject"},
            ],
            "press": [
                {
                    "title": "<img src=x onerror=alert(1)>",
                    "url": "javascript:evil()",
                    "date": "2025-01-02",
                    "product": "Excel",
                    "buyer": "U<script>",
                    "sources": ["arquivo.pt"],
                }
            ],
            "press_note": "<em>nota</em>",
            "press_errors": {},
            "skipped": {"sem montante": 1},
            "sciproj": {"total": 0.0, "count": 0},
            "private_grants_count": 0,
            "sources": [
                {
                    "id": "s",
                    "publisher": "P",
                    "title": "T<script>",
                    "url": "https://dados.gov.pt/x",
                    "file_name": "f.xlsx",
                    "licence": "L",
                    "coverage": "c",
                    "updated": "2026-01-01",
                }
            ],
            "breakdowns": {
                "committed_by_region": {"2025": {"Norte": 1.0}},
                "committed_by_category": {"2025": {"ensino superior": 1.0}},
                "committed_by_vendor": {"2025": {"Microsoft": 1.0}},
                "committed_by_place": {"2025": {"Leiria": 1.0}},
            },
            "prr": {},
            "generated_at": "2026-01-01T00:00:00+00:00",
            "records": [],
        }
    )
    payload["totals"]["2025"] = {"committed": 1.0, "requested": 0.0, "grants": 0.0}
    payload.update(overrides)
    return payload


def test_esc_and_safe_href():
    assert "&lt;script&gt;" in _esc("<script>")
    assert _safe_href("javascript:alert(1)") == "#"
    assert _safe_href("https://example.com/a?b=1").startswith("https://")


def test_render_escapes_injected_fields():
    html_out = render_html(_base_payload())
    assert "<b>Excel</b>" not in html_out
    assert "<img src=x" not in html_out
    assert 'href="javascript:evil()"' not in html_out
    assert "javascript:evil()" not in html_out
    assert "&lt;b&gt;Excel&lt;/b&gt;" in html_out
    # press titles live only in embedded JSON (escaped as \\u003c)
    assert "\\u003cimg" in html_out or "&lt;img" in html_out
    assert 'href="https://dados.gov.pt/x"' in html_out
    assert "Rejeitadas" not in html_out
    assert "mapRegion" in html_out
    assert "scroll-snap" in html_out
    assert "Cloud Act" in html_out
    assert "antes de ela se tornar uma crise" not in html_out
    assert "Onde o corte seria mais grave" in html_out
    assert "Esta conta é só dinheiro público" in html_out
    assert "Portugal à noite" not in html_out
    assert "Pedido ao mercado fica no cartão" not in html_out
    assert (
        "sem pedido ao mercado" in html_out
        and "pedido estava" not in html_out
        and "Não some" not in html_out
    )
    assert "Cinco anos de contratos assinados" in html_out
    assert "Na imprensa" not in html_out
    assert "yearLabels.map((y, i)" in html_out
    assert "Quem levou os contratos" in html_out
    assert "indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y" in html_out
    assert "210 - t * 185" in html_out
    assert "O que foi assinado e o que foi pedido" in html_out
    assert "Fontes e ficheiros" not in html_out
    assert ">Fontes<" in html_out or "Fontes</h2>" in html_out
    assert "As algemas" in html_out
    assert "cortar esses serviços" not in html_out
    assert "class='algema-grid'" not in html_out
    assert "Estes produtos não aparecem nos contratos assinados" in html_out
    assert "Portal Base" in html_out
    assert "0 anos de algemas" not in html_out
    assert "do país" in html_out
    assert "github.com/codeforportugal/gafam-portugal-report" in html_out
    assert "remixicon" in html_out
    assert "contratos no top 100 ·" not in html_out
    assert "algema-note" not in html_out
    assert "Gerado em" not in html_out
    assert "Realização: code for portugal" in html_out
    assert "codefor.pt" in html_out
    assert 'class="cfp-bar"' in html_out
    assert "cc-by-sa.png" in html_out
    assert "agplv3.png" in html_out
    assert "#010101" in html_out
    assert "#fd5288" in html_out
    assert "family=Inter" in html_out
    assert "Courier+Prime" in html_out
    assert 'href="assets/favicon.png"' in html_out


def test_render_private_grants_note_and_sciproj_section():
    html_out = render_html(
        _base_payload(
            private_grants_count=3,
            sciproj={"total": 10.0, "count": 1},
            skipped={"sem montante": 2},
        )
    )
    assert "Há 3 apoios" not in html_out
    assert "Portugal 2030" not in html_out
    assert "Na imprensa" not in html_out


def test_render_leiria_scope():
    html_out = render_html(
        _base_payload(
            records=[
                {
                    "source_id": "1",
                    "channel": "committed",
                    "buyer": "Município de Leiria",
                    "excerpt": "Excel",
                    "amount_eur": 100.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2025,
                    "headline": True,
                    "product": "Excel",
                    "url": "",
                },
                {
                    "source_id": "2",
                    "channel": "committed",
                    "buyer": "Município de Leiria",
                    "excerpt": "Office 365",
                    "amount_eur": 500.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2025,
                    "headline": True,
                    "product": "Office 365",
                    "url": "",
                },
                {
                    "source_id": "3",
                    "channel": "committed",
                    "buyer": "Município de Peniche",
                    "excerpt": "Teams",
                    "amount_eur": 50.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Peniche",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2024,
                    "headline": True,
                    "product": "Teams",
                    "url": "",
                },
                {
                    "source_id": "4",
                    "channel": "committed",
                    "buyer": "Município de Leiria",
                    "excerpt": "Microsoft brand",
                    "amount_eur": 80.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2023,
                    "headline": True,
                    "product": "Microsoft",
                    "url": "",
                },
            ]
        ),
        scope="leiria",
    )
    assert "Distrito de Leiria" in html_out
    assert "Cloud Act" in html_out
    assert "apoios (grants)" not in html_out
    assert "Município de Leiria" in html_out
    assert "100 maiores" in html_out
    assert "mapLeiria" in html_out
    assert "Quem levou os contratos" in html_out
    assert "O que foi assinado e o que foi pedido" in html_out
    assert "Onde o corte seria mais grave" in html_out
    assert "concelhos mais escuros" in html_out
    assert "Esta conta é só dinheiro público" in html_out
    assert "Uso nos conselhos" not in html_out
    assert "As algemas" in html_out
    assert "cortar esses serviços" not in html_out
    assert "Os 100 maiores contratos" in html_out
    assert "contrato assinado" in html_out
    assert "anos de algemas" in html_out or "ano de algemas" in html_out
    assert "algema-grid" in html_out
    assert "algema-stack" in html_out
    assert "Google Cloud" not in html_out
    assert "0 anos de algemas" not in html_out
    assert "Microsoft aparece em vários anos" in html_out
    assert "github.com/codeforportugal/gafam-portugal-report" in html_out
    assert "contratos no top 100 ·" not in html_out
    assert "algema-note" not in html_out
    assert "Gerado em" not in html_out
    assert "remixicon" in html_out
    assert "Office 365" in html_out and "Teams" in html_out
    assert "Pedrógão Grande é concelho" not in html_out
    assert 'id="dots"' in html_out
    assert 'class="slide' in html_out
    assert "leiria.geojson" in html_out
    assert "['#f4ea15', '#eb5423', '#010101']" in html_out
    assert "i <= 3" in html_out
    assert 'class="slide slide--end" id="s6" data-title="Fontes"' in html_out
    assert "Realização: code for portugal" in html_out
    assert 'class="cfp-bar"' in html_out
    assert 'href="../assets/favicon.png"' in html_out
    assert "cc-by-sa.png" in html_out
    assert "#72e123" in html_out


def test_algema_lead_names_both_vendors():
    html_out = render_html(
        _base_payload(
            records=[
                {
                    "source_id": "m",
                    "channel": "committed",
                    "buyer": "Câmara",
                    "excerpt": "Office 365",
                    "amount_eur": 10.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2025,
                    "headline": True,
                    "product": "Office 365",
                    "url": "",
                },
                {
                    "source_id": "z",
                    "channel": "committed",
                    "buyer": "Câmara",
                    "excerpt": "",
                    "amount_eur": 1.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "",
                    "fundos": "",
                    "year": 0,
                    "headline": True,
                    "product": "",
                    "url": "",
                },
                {
                    "source_id": "g",
                    "channel": "committed",
                    "buyer": "Câmara",
                    "excerpt": "Google Cloud",
                    "amount_eur": 8.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Google",
                    "fundos": "",
                    "year": 2024,
                    "headline": True,
                    "product": "Google Cloud",
                    "url": "",
                },
            ]
        )
    )
    assert "Microsoft e Google aparecem em vários anos" in html_out
    assert "Google Cloud" in html_out
    assert "0 anos de algemas" not in html_out


def test_render_leiria_lockin_empty_focus():
    html_out = render_html(
        _base_payload(
            records=[
                {
                    "source_id": "9",
                    "channel": "committed",
                    "buyer": "Município de Leiria",
                    "excerpt": "Excel",
                    "amount_eur": 10.0,
                    "region": "Centro",
                    "district": "Leiria",
                    "place": "Leiria",
                    "category": "administração local",
                    "vendor": "Microsoft",
                    "fundos": "",
                    "year": 2025,
                    "headline": True,
                    "product": "Excel",
                    "url": "",
                }
            ]
        ),
        scope="leiria",
    )
    assert "Estes produtos não aparecem nos contratos assinados" in html_out
    assert "Portal Base" in html_out


def test_year_card_pedido_percentage():
    payload = _base_payload()
    payload["totals"]["2026"] = {
        "committed": 54_071_735.04,
        "requested": 0.0,
        "grants": 0.0,
    }
    payload["totals"]["2025"] = {
        "committed": 100.0,
        "requested": 110.0,
        "grants": 0.0,
    }
    payload["totals"]["2024"] = {
        "committed": 100.0,
        "requested": 80.0,
        "grants": 0.0,
    }
    payload["totals"]["2023"] = {
        "committed": 50.0,
        "requested": 50.0,
        "grants": 0.0,
    }
    payload["totals"]["2022"] = {
        "committed": 0.0,
        "requested": 12.0,
        "grants": 0.0,
    }
    html_out = render_html(payload)
    assert "54 milhões €" in html_out
    assert "pedido 10% acima do contrato" in html_out
    assert "pedido 20% abaixo do contrato" in html_out
    assert "pedido igual ao contrato" in html_out
    assert "só pedido ao mercado" in html_out


def test_lockin_from_top_edge_years():
    from gafam_contratos.report import _lockin_from_top

    rows = _lockin_from_top(
        [
            {
                "product": "",
                "vendor": "",
                "year": 0,
                "amount_eur": 10,
            },
            {
                "product": "Excel",
                "vendor": "Microsoft",
                "year": 2024,
                "amount_eur": 5,
            },
            {
                "product": "Excel",
                "vendor": "Microsoft",
                "year": 2025,
                "amount_eur": 7,
            },
        ]
    )
    by_product = {r[0]: r for r in rows}
    assert by_product["—"][3] == 0 and by_product["—"][4] == 0
    assert by_product["Excel"][3] == 2 and by_product["Excel"][4] == 2
