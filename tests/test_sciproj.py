from gafam_contratos.lexicon import load_lexicon
from gafam_contratos.paths import data_dir
from gafam_contratos.sciproj import sciproj_terms_from_keywords, search_sciproj


def test_sciproj_keeps_amount_and_skips_uncertain():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    html = (
        "<html><body>"
        "<div>Projecto Azure cloud 12.000,00 €</div>"
        + ("<!-- pad -->" * 80)
        + "<div>Outro texto sem produto GAFAM 500 €</div>"
        "</body></html>"
    )

    def fetcher(url: str, **kwargs: object) -> bytes:
        _ = url, kwargs
        return html.encode("utf-8")

    kept, skipped = search_sciproj(
        ["Azure"],
        keywords,
        fetcher=fetcher,
        sleeper=lambda _s: None,
    )
    assert any(r.product == "Azure" for r in kept)
    assert skipped["correspondência incerta"] >= 1
    assert sciproj_terms_from_keywords(keywords)


def test_sciproj_skips_without_amount_and_fetch_error():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    html = """
    <script type="application/ld+json">
    {"name": "Azure research", "description": "Azure cloud", "funder": "FCT"}
    </script>
    """

    def fetcher(url: str, **kwargs: object) -> bytes:
        _ = kwargs
        if "fail" in url:
            raise OSError("down")
        return html.encode("utf-8")

    kept, skipped = search_sciproj(["Azure"], keywords, fetcher=fetcher)
    assert kept == []
    assert skipped["sem montante"] >= 1
    kept2, _ = search_sciproj(["fail"], keywords, fetcher=fetcher)
    assert kept2 == []
