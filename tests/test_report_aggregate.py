from gafam_contratos.aggregate import (
    breakdowns,
    national_once,
    national_totals,
    prr_subtotal,
)
from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.models import PressLink, Record, SourceMeta
from gafam_contratos.paths import data_dir
from gafam_contratos.report import build_report_payload, render_html, validate_report


def _rec(**kwargs: object) -> Record:
    base = {
        "source_id": "1",
        "channel": "committed",
        "buyer": "U",
        "excerpt": "Excel",
        "amount_eur": 10.0,
        "region": "Norte",
        "category": "ensino superior",
        "vendor": "Microsoft",
        "fundos": "",
        "year": 2025,
        "headline": True,
        "product": "Excel",
    }
    base.update(kwargs)
    return Record(**base)  # type: ignore[arg-type]


def test_aggregates_and_html():
    records = [
        _rec(),
        _rec(source_id="2", fundos="PRR", amount_eur=5),
        _rec(source_id="3", channel="requested", amount_eur=3),
        _rec(source_id="4", channel="grant", amount_eur=7),
        _rec(source_id="5", channel="sciproj", amount_eur=2),
        _rec(source_id="6", headline=False, amount_eur=100),
    ]
    assert national_totals(records)["2025"]["committed"] == 15.0
    assert prr_subtotal(records)["2025"] == 5.0
    assert breakdowns(records)["committed_by_region"]["2025"]["Norte"] == 15.0
    assert national_once(records) == records
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    payload = build_report_payload(
        records=records,
        sources=[
            SourceMeta("s", "p", "t", "u", "f", "l", "c", "2026-01-01"),
        ],
        keywords=keywords,
        press=[
            PressLink("t", "https://x", "2025-01-01", "Excel", "U", ["arquivo.pt"]),
        ],
        press_errors={"gdelt": "down"},
        skipped={"sem montante": 1},
    )
    validate_report(payload)
    html = render_html(payload)
    assert "contrato assinado" in html
    assert "Falhou" in html
