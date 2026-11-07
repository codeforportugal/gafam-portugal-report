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
                    "title": '<img src=x onerror=alert(1)>',
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
    assert "Portugal no dia 0" in html_out
    assert "Portugal à noite" not in html_out
    assert "Pedido ao mercado fica no cartão" not in html_out
    assert "pedido estava" in html_out or "sem pedido ao mercado" in html_out
    assert "Cinco anos com Google, Amazon, Facebook, Apple, Microsoft" in html_out
    assert "Na imprensa" not in html_out
    assert "yearLabels.map((y, i)" in html_out
    assert "Por fornecedor · 2022–2026" in html_out
    assert "indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y" in html_out
    assert "210 - t * 185" in html_out
    assert "Assinatura VS pedidos" in html_out
    assert "Fontes e ficheiros" not in html_out
    assert ">Fontes<" in html_out or "Fontes</h2>" in html_out
    assert "As algemas das Big Techs" in html_out
    assert "algema-grid" in html_out
    assert "algema-stack" in html_out
    assert "algema-vendor" in html_out
    assert "Google Cloud" in html_out
    assert "Android" in html_out
    assert "contratos nacionais" in html_out
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
    assert "16 concelhos" in html_out
    assert "grants" in html_out
    assert "Município de Leiria" in html_out
    assert "100 maiores" in html_out
    assert "mapLeiria" in html_out
    assert "As Big Tech quem mandam" in html_out
    assert "Assinatura VS Pedidos" in html_out
    assert "Uso nos conselhos" in html_out
    assert "As algemas das Big Techs" in html_out
    assert "Top 100 das maiores algemas" in html_out
    assert "€ contratado GAFAM" in html_out
    assert "anos de algemas" in html_out or "ano de algemas" in html_out
    assert "algema-grid" in html_out
    assert "algema-stack" in html_out
    assert "Google Cloud" in html_out
    assert "contratos no top 100 ·" not in html_out
    assert "algema-note" not in html_out
    assert "Gerado em" not in html_out
    assert "remixicon" in html_out
    assert "Office 365" in html_out and "Teams" in html_out
    assert "Pedrógão Grande é concelho" not in html_out
    assert 'id="dots"' in html_out
    assert 'class="slide' in html_out
    assert "concelhos_leiria.geojson" in html_out
    assert "Realização: code for portugal" in html_out
    assert 'class="cfp-bar"' in html_out
    assert 'href="../assets/favicon.png"' in html_out
    assert "cc-by-sa.png" in html_out
    assert "#72e123" in html_out


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
    assert "Sem Microsoft / Google no top 100" in html_out


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
    assert "pedido estava 10% maior" in html_out
    assert "pedido estava 20% menor" in html_out
    assert "pedido ao nível do contrato" in html_out
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
