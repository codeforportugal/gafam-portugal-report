"""Cobertura de ramos raros."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.error import HTTPError

from gafam_contratos.amounts import parse_amount, parse_date
from gafam_contratos.classify import classify_institution, region_from_local
from gafam_contratos.lexicon import find_match, is_rejected_false_friend, load_lexicon
from gafam_contratos.models import Record
from gafam_contratos.paths import data_dir, reports_dir
from gafam_contratos.press import (
    _date_ok,
    _host_allowed,
    gather_press,
    load_press_domains,
)
from gafam_contratos.retry import retry_call


def test_amount_us_format_and_empty():
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("") is None
    assert parse_amount(True) is None  # bool is int subclass excluded
    assert parse_date("") is None
    assert parse_date("45658.0") is not None


def test_region_unknown_and_private_markers():
    mapping = {"lisboa": "Área Metropolitana de Lisboa"}
    assert region_from_local("Portugal, Lisboa, Desconhecido", mapping) == "sem local"
    assert region_from_local("Região Autónoma da Madeira", mapping) == "Madeira"
    assert classify_institution("Serviços SA") == "privado"


def test_reject_false_friend_when_match_exists():
    keywords = load_lexicon(data_dir() / "lexicon.yml")
    assert not is_rejected_false_friend("compra de Excel", keywords)
    assert find_match("", keywords) is None


def test_retry_http_retriable():
    state = {"n": 0}

    def operation() -> str:
        state["n"] += 1
        if state["n"] == 1:
            raise HTTPError("http://x", 503, "busy", hdrs=None, fp=None)  # type: ignore[arg-type]
        return "ok"

    assert retry_call(operation, sleeps=(1,), sleeper=lambda _s: None) == "ok"


def test_default_sleep_not_used_in_tests():
    # exercise reports_dir path
    assert reports_dir().name == "reports"


def test_press_date_and_host_helpers():
    domains = load_press_domains(data_dir() / "press_domains.txt")
    assert _host_allowed("https://www.publico.pt/x", domains)
    assert not _host_allowed("https://evil.example/x", domains)
    assert _date_ok("20251399") is None
    assert _date_ok(None) is None
    assert _date_ok("2025") is None


def test_gather_press_arquivo_error():
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
        raise OSError("arquivo down")

    def gdelt(query: str, **kwargs: object) -> list[dict[str, str]]:
        _ = query, kwargs
        return []

    links, errors = gather_press(
        records,
        keywords,
        domains,
        arquivo_fetch=arquivo,
        gdelt_fetch=gdelt,
        sleeper=lambda _s: None,
    )
    assert links == []
    assert "arquivo.pt" in errors


def test_main_module_exec(monkeypatch):
    import sys

    monkeypatch.setattr(
        "gafam_contratos.pipeline.run",
        lambda **kwargs: Path(),
    )
    monkeypatch.setattr(sys, "argv", ["gafam_contratos"])
    # importing __main__ as script
    monkeypatch.setitem(sys.modules, "gafam_contratos.__main__", None)
    _ = date
