"""SciPROJ: só mantém linhas com montante e match inequívoco."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from urllib.parse import quote_plus

from gafam_contratos.amounts import parse_amount
from gafam_contratos.classify import classify_institution
from gafam_contratos.lexicon import Keyword, find_match
from gafam_contratos.models import Record, SourceMeta
from gafam_contratos.retry import http_get

SCIPROJ_SEARCH = "https://sciproj.ptcris.pt/"


def sciproj_source() -> SourceMeta:
    return SourceMeta(
        id="sciproj",
        publisher="FCT / PTCRIS",
        title="Portal SciPROJ",
        url="https://sciproj.ptcris.pt/",
        file_name="pesquisa HTML",
        licence="Acesso público",
        coverage="Financiamento científico 2025–2026 (melhor esforço)",
        updated="2026-11-06",
    )


def _parse_html_rows(html: str) -> list[dict[str, str]]:
    """Extrai blocos simples título/montante do HTML público, se existirem."""
    rows: list[dict[str, str]] = []
    # Tenta JSON embutido
    for match in re.finditer(
        r"<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>",
        html,
        re.DOTALL,
    ):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "name" in payload:
            rows.append(
                {
                    "title": str(payload.get("name") or ""),
                    "amount": str(
                        payload.get("funding") or payload.get("amount") or ""
                    ),
                    "org": str(payload.get("funder") or ""),
                    "text": str(
                        payload.get("description") or payload.get("name") or ""
                    ),
                }
            )
    # Fallback: cartões com euro
    for block in re.finditer(r"([\d\s\.\,]+)\s*€", html):
        start = max(0, block.start() - 200)
        end = min(len(html), block.end() + 200)
        chunk = re.sub(r"<[^>]+>", " ", html[start:end])
        chunk = re.sub(r"\s+", " ", chunk).strip()
        rows.append(
            {
                "title": chunk[:120],
                "amount": block.group(1),
                "org": "",
                "text": chunk,
            }
        )
    return rows


def search_sciproj(
    terms: Sequence[str],
    keywords: list[Keyword],
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
    fetcher: Callable[..., bytes] | None = None,
) -> tuple[list[Record], dict[str, int]]:
    """Devolve registos mantidos e contagens de salto."""
    skipped = {"sem montante": 0, "correspondência incerta": 0}
    kept: list[Record] = []
    get = fetcher or http_get
    for term in terms:
        url = f"{SCIPROJ_SEARCH}?s={quote_plus(term)}"
        try:
            raw = get(url, sleeps=sleeps, sleeper=sleeper, timeout=60.0)
        except (OSError, ValueError) as exc:
            _ = exc
            continue
        html = raw.decode("utf-8", errors="replace")
        for row in _parse_html_rows(html):
            text = row.get("text") or row.get("title") or ""
            hit = find_match(text, keywords)
            if hit is None:
                skipped["correspondência incerta"] += 1
                continue
            amount = parse_amount(row.get("amount"))
            if amount is None:
                skipped["sem montante"] += 1
                continue
            org = row.get("org") or "SciPROJ"
            kept.append(
                Record(
                    source_id=f"sciproj-{len(kept)}",
                    channel="sciproj",
                    buyer=org,
                    excerpt=hit.excerpt,
                    amount_eur=amount,
                    region="sem local",
                    category=classify_institution(org),
                    vendor=hit.vendor,
                    fundos="",
                    year=2025,
                    headline=True,
                    product=hit.term,
                )
            )
    return kept, skipped


def sciproj_terms_from_keywords(keywords: list[Keyword], limit: int = 10) -> list[str]:
    terms = [kw.pattern for kw in keywords if kw.kind == "match"]
    # Prefer distinctive multi-word / brand terms
    terms.sort(key=lambda t: (len(t.split()), len(t)), reverse=True)
    return terms[:limit]
