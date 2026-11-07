"""Pesquisa de imprensa via Arquivo.pt e GDELT (sem chave)."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from gafam_contratos.constants import YEARS
from gafam_contratos.lexicon import Keyword, fold
from gafam_contratos.models import PressLink, Record
from gafam_contratos.retry import http_get, iter_spaced

ARQUIVO = "https://arquivo.pt/textsearch"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
PROCUREMENT_WORDS = (
    "contrato",
    "aquisição",
    "aquisicao",
    "concurso",
    "adjudica",
)
# GDELT DOC 2.0: ≥5s between calls; 429 bans the IP if we retry fast. One query.
GDELT_GAP = 180.0
GDELT_WARMUP = 180.0
GDELT_RETRIES = (180,)
GDELT_RATE_MARKERS = ("limit requests", "too many requests", "rate limit")


def load_press_domains(path: Path) -> set[str]:
    domains: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip().lower()
        if stripped and not stripped.startswith("#"):
            domains.add(stripped)
    return domains


def build_queries(records: list[Record], limit: int = 8) -> list[tuple[str, str, str]]:
    """(query, product, buyer) a partir dos maiores contratos headline."""
    committed = [
        r for r in records if r.channel == "committed" and r.headline and r.product
    ]
    committed.sort(key=lambda r: r.amount_eur, reverse=True)
    seen: set[str] = set()
    queries: list[tuple[str, str, str]] = []
    for record in committed:
        if record.product in seen:
            continue
        seen.add(record.product)
        # Consulta curta: buyer longo mata o Arquivo.pt; filtro valida depois.
        query = f"{record.product} Portugal contrato"
        queries.append((query, record.product, record.buyer))
        if len(queries) >= limit:
            break
    return queries


def build_gdelt_queries(
    records: list[Record], limit: int = 1
) -> list[tuple[str, str, str]]:
    """Uma consulta curta para GDELT (DOC 2.0 pede ≥5s; 429 bloqueia o IP)."""
    committed = [
        r for r in records if r.channel == "committed" and r.headline and r.product
    ]
    committed.sort(key=lambda r: r.amount_eur, reverse=True)
    seen: set[str] = set()
    queries: list[tuple[str, str, str]] = []
    for record in committed:
        product = record.product
        if product in seen:
            continue
        seen.add(product)
        query = f"{product} sourcecountry:Portugal"
        queries.append((query, product, record.buyer))
        if len(queries) >= limit:
            break
    return queries


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        return host[4:]
    return host


def _host_allowed(url: str, domains: set[str]) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def _date_ok(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 8:
        year = int(digits[:4])
        month = int(digits[4:6])
        day = int(digits[6:8])
        if year in YEARS:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
    return None


def _text_ok(
    title: str, snippet: str, product: str, buyer: str, keywords: list[Keyword]
) -> bool:
    """Produto no título; comprador ou verbo de contratação no título/snippet."""
    _ = keywords  # lexicon retained for call-site symmetry / future aliases
    title_fold = fold(title)
    blob_fold = fold(f"{title} {snippet}")
    # Título só — snippets do Arquivo trazem chrome (ads/analytics) com marcas.
    if fold(product) not in title_fold:
        return False
    buyer_token = fold(
        buyer.split(",", maxsplit=1)[0].split("(", maxsplit=1)[0].strip()
    )
    has_buyer = bool(buyer_token) and buyer_token[:20] in blob_fold
    has_proc = any(word in blob_fold for word in PROCUREMENT_WORDS)
    return has_buyer or has_proc


def _url_ok(url: str) -> bool:
    low = url.lower()
    if "/tag/" in low or "/amp/" in low:
        return False
    return True


def fetch_arquivo(
    query: str,
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> list[dict[str, str]]:
    url = (
        f"{ARQUIVO}?q={quote_plus(query)}"
        f"&from=20220101000000&to=20261231235959"
        f"&maxItems=50&prettyPrint=false"
    )
    raw = http_get(url, sleeps=sleeps, sleeper=sleeper, timeout=90.0)
    payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
    items = payload.get("response_items") or payload.get("responseItems") or []
    out: list[dict[str, str]] = []
    for item in items:
        out.append(
            {
                "title": str(item.get("title") or item.get("linkToArchive") or ""),
                "url": str(item.get("originalURL") or item.get("linkToArchive") or ""),
                "date": str(item.get("tstamp") or item.get("date") or ""),
                "snippet": str(item.get("snippet") or item.get("title") or ""),
                "origin": "arquivo.pt",
            }
        )
    return out


def fetch_gdelt(
    query: str,
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> list[dict[str, str]]:
    url = (
        f"{GDELT}?query={quote_plus(query)}"
        f"&mode=ArtList&maxrecords=50&format=json&sort=datedesc"
    )
    raw = http_get(url, sleeps=sleeps, sleeper=sleeper, timeout=90.0)
    text = raw.decode("utf-8").strip()
    lowered = text.lower()
    if any(marker in lowered for marker in GDELT_RATE_MARKERS):
        message = "HTTP Error 429: Too Many Requests"
        raise OSError(message)
    if not text or text[0] not in "{[":
        return []
    payload: dict[str, Any] = json.loads(text)
    articles = payload.get("articles") or []
    out: list[dict[str, str]] = []
    for item in articles:
        out.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "date": str(item.get("seendate") or ""),
                "snippet": str(item.get("title") or ""),
                "origin": "gdelt",
            }
        )
    return out


def filter_articles(
    articles: list[dict[str, str]],
    *,
    product: str,
    buyer: str,
    keywords: list[Keyword],
    domains: set[str],
) -> list[PressLink]:
    links: list[PressLink] = []
    for article in articles:
        url = article.get("url") or ""
        title = article.get("title") or ""
        snippet = article.get("snippet") or ""
        if not url or not _host_allowed(url, domains) or not _url_ok(url):
            continue
        dated = _date_ok(article.get("date"))
        if dated is None:
            continue
        if not _text_ok(title, snippet, product, buyer, keywords):
            continue
        links.append(
            PressLink(
                title=title,
                url=url,
                date=dated,
                product=product,
                buyer=buyer,
                sources=[article.get("origin") or ""],
            )
        )
    return links


def merge_press(links: list[PressLink], *, max_links: int = 100) -> list[PressLink]:
    by_url: dict[str, PressLink] = {}
    for link in links:
        existing = by_url.get(link.url)
        if existing is None:
            by_url[link.url] = link
            continue
        for source in link.sources:
            if source and source not in existing.sources:
                existing.sources.append(source)
    merged = sorted(by_url.values(), key=lambda item: item.date, reverse=True)
    return merged[:max_links]


def gather_press(
    records: list[Record],
    keywords: list[Keyword],
    domains: set[str],
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
    arquivo_fetch: Callable[..., list[dict[str, str]]] | None = None,
    gdelt_fetch: Callable[..., list[dict[str, str]]] | None = None,
) -> tuple[list[PressLink], dict[str, str]]:
    """Devolve links e mapa de erros por origem."""
    queries = build_queries(records)
    errors: dict[str, str] = {}
    collected: list[PressLink] = []
    arquivo = arquivo_fetch or fetch_arquivo
    gdelt = gdelt_fetch or fetch_gdelt

    for query, product, buyer in queries:
        try:
            arts = arquivo(query, sleeps=sleeps, sleeper=sleeper)
            collected.extend(
                filter_articles(
                    arts,
                    product=product,
                    buyer=buyer,
                    keywords=keywords,
                    domains=domains,
                )
            )
        except (OSError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
            errors["arquivo.pt"] = str(exc)
            break

    gdelt_queries = build_gdelt_queries(records)
    for query, product, buyer in iter_spaced(
        gdelt_queries,
        min_gap_seconds=GDELT_GAP,
        sleeper=sleeper,
        initial_gap_seconds=GDELT_WARMUP,
    ):
        try:
            arts = gdelt(
                query,
                sleeps=sleeps if sleeps is not None else GDELT_RETRIES,
                sleeper=sleeper,
            )
            collected.extend(
                filter_articles(
                    arts,
                    product=product,
                    buyer=buyer,
                    keywords=keywords,
                    domains=domains,
                )
            )
        except (OSError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
            errors["gdelt"] = str(exc)
            break

    return merge_press(collected), errors
