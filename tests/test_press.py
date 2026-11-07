from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.models import PressLink, Record
from gafam_contratos.paths import data_dir
from gafam_contratos.press import (
    build_queries,
    filter_articles,
    gather_press,
    load_press_domains,
    merge_press,
)


def test_filter_keeps_dated_product_and_drops_uncertain():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    domains = load_press_domains(data_dir() / "press_domains.txt")
    articles = [
        {
            "title": "Universidade compra Excel",
            "url": "https://www.publico.pt/a",
            "date": "20250301120000",
            "snippet": "contrato de aquisição Excel",
            "origin": "arquivo.pt",
        },
        {
            "title": "Sem data",
            "url": "https://www.publico.pt/b",
            "date": "",
            "snippet": "Excel contrato",
            "origin": "arquivo.pt",
        },
        {
            "title": "Meta vaga",
            "url": "https://www.publico.pt/c",
            "date": "20250301120000",
            "snippet": "atingir a meta",
            "origin": "arquivo.pt",
        },
        {
            "title": "Universidade de Lisboa adopta Excel",
            "url": "https://www.publico.pt/d",
            "date": "20250401120000",
            "snippet": "nova ferramenta na reitoria",
            "origin": "arquivo.pt",
        },
        {
            "title": "Excel em tag",
            "url": "https://www.publico.pt/tag/excel",
            "date": "20250401120000",
            "snippet": "contrato Excel",
            "origin": "arquivo.pt",
        },
    ]
    links = filter_articles(
        articles,
        product="Excel",
        buyer="Universidade de Lisboa",
        keywords=keywords,
        domains=domains,
    )
    assert len(links) == 2
    assert {link.url.rsplit("/", 1)[-1] for link in links} == {"a", "d"}


def test_merge_and_queries():
    records = [
        Record(
            source_id="1",
            channel="committed",
            buyer="Universidade de Lisboa",
            excerpt="Excel",
            amount_eur=10,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel",
        )
    ]
    queries = build_queries(records)
    assert queries
    a = PressLink("t", "https://x.pt/1", "2025-01-01", "Excel", "U", ["arquivo.pt"])
    b = PressLink("t2", "https://x.pt/1", "2025-01-02", "Excel", "U", ["gdelt"])
    merged = merge_press([a, b])
    assert len(merged) == 1
    assert set(merged[0].sources) == {"arquivo.pt", "gdelt"}


def test_fetch_gdelt_empty_body(monkeypatch):
    from gafam_contratos.press import fetch_gdelt

    monkeypatch.setattr(
        "gafam_contratos.press.http_get",
        lambda *a, **k: b"",
    )
    assert fetch_gdelt("Excel") == []


def test_fetch_gdelt_rate_limit_body(monkeypatch):
    from gafam_contratos.press import fetch_gdelt

    monkeypatch.setattr(
        "gafam_contratos.press.http_get",
        lambda *a, **k: b"Please limit requests to one every 5 seconds",
    )
    try:
        fetch_gdelt("Excel")
        raise AssertionError("expected OSError")
    except OSError as exc:
        assert "429" in str(exc)


def test_gather_press_with_stubs():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    domains = load_press_domains(data_dir() / "press_domains.txt")
    records = [
        Record(
            source_id="1",
            channel="committed",
            buyer="Universidade de Lisboa",
            excerpt="Excel",
            amount_eur=10,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel",
        )
    ]

    def arquivo(query: str, **kwargs: object) -> list[dict[str, str]]:
        _ = query, kwargs
        return [
            {
                "title": "Excel contrato",
                "url": "https://www.publico.pt/ok",
                "date": "20250301",
                "snippet": "aquisição Excel universidade",
                "origin": "arquivo.pt",
            }
        ]

    def gdelt(query: str, **kwargs: object) -> list[dict[str, str]]:
        _ = query, kwargs
        raise OSError("down")

    links, errors = gather_press(
        records,
        keywords,
        domains,
        arquivo_fetch=arquivo,
        gdelt_fetch=gdelt,
        sleeper=lambda _s: None,
    )
    assert links
    assert "gdelt" in errors


def test_build_gdelt_queries_unique_products():
    records = [
        Record(
            source_id=str(i),
            channel="committed",
            buyer=f"Entidade {i}",
            excerpt="Excel",
            amount_eur=1000 - i,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel" if i < 2 else f"Product{i}",
        )
        for i in range(6)
    ]
    from gafam_contratos.press import build_gdelt_queries

    qs = build_gdelt_queries(records, limit=3)
    assert len(qs) == 3
    assert qs[0][0].startswith("Excel sourcecountry:Portugal")
    assert build_gdelt_queries(records, limit=99)  # no early break when under limit
    assert build_gdelt_queries([], limit=1) == []


def test_gather_press_stops_origin_after_error():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    domains = load_press_domains(data_dir() / "press_domains.txt")
    records = [
        Record(
            source_id=str(i),
            channel="committed",
            buyer=f"Entidade {i}",
            excerpt="Excel",
            amount_eur=1000 - i,
            region="Norte",
            category="ensino superior",
            vendor="Microsoft",
            fundos="",
            year=2025,
            headline=True,
            product="Excel",
        )
        for i in range(3)
    ]
    calls = {"arquivo": 0, "gdelt": 0}

    def arquivo(query: str, **kwargs: object) -> list[dict[str, str]]:
        _ = query, kwargs
        calls["arquivo"] += 1
        message = "arquivo down"
        raise OSError(message)

    def gdelt(query: str, **kwargs: object) -> list[dict[str, str]]:
        _ = query, kwargs
        calls["gdelt"] += 1
        message = "gdelt down"
        raise OSError(message)

    links, errors = gather_press(
        records,
        keywords,
        domains,
        arquivo_fetch=arquivo,
        gdelt_fetch=gdelt,
        sleeper=lambda _s: None,
    )
    assert links == []
    assert calls["arquivo"] == 1
    assert calls["gdelt"] == 1
    assert "arquivo.pt" in errors
    assert "gdelt" in errors
