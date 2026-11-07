"""Léxico GAFAM e correspondência sem ambiguidade."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_WORD = r"(?<!\w){term}(?!\w)"


@dataclass(frozen=True, slots=True)
class Keyword:
    pattern: str
    vendor: str
    kind: str  # "match" | "reject"


@dataclass(frozen=True, slots=True)
class MatchHit:
    term: str
    vendor: str
    excerpt: str


def fold(text: str) -> str:
    """Minúsculas sem acentos."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def load_lexicon(path: Path) -> list[Keyword]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    keywords: list[Keyword] = []
    match_block = raw.get("match") or {}
    for vendor, terms in match_block.items():
        for term in terms:
            keywords.append(
                Keyword(pattern=str(term), vendor=str(vendor), kind="match")
            )
    for term in raw.get("reject") or []:
        keywords.append(Keyword(pattern=str(term), vendor="", kind="reject"))
    return keywords


def _compile(term: str) -> re.Pattern[str]:
    escaped = re.escape(fold(term))
    return re.compile(_WORD.format(term=escaped), re.IGNORECASE)


def find_match(text: str, keywords: list[Keyword]) -> MatchHit | None:
    """Devolve a primeira correspondência inequívoca, ou None.

    Termos de rejeição (excelência, meta nua, office nu) nunca contam
    como produto GAFAM. A fronteira de palavra impede que «excelência»
    active «Excel».
    """
    folded = fold(text)
    brands = {"microsoft", "google", "apple", "amazon"}
    # Prefer longer / multi-word products; brand-only names last.
    candidates = sorted(
        (kw for kw in keywords if kw.kind == "match"),
        key=lambda kw: (
            fold(kw.pattern) in brands,
            -len(kw.pattern),
        ),
    )
    for kw in candidates:
        found = _compile(kw.pattern).search(folded)
        if found is None:
            continue
        if fold(kw.pattern) == "exchange" and _exchange_is_false_friend(folded):
            continue
        start = max(0, found.start() - 40)
        end = min(len(text), found.end() + 40)
        excerpt = text[start:end].strip()
        return MatchHit(term=kw.pattern, vendor=kw.vendor, excerpt=excerpt)
    return None


_EXCHANGE_HARDWARE = (
    "cockpit",
    "hud",
    "beacon",
    "beacons",
    "p/n",
    "clafa",
    "gtf",
    "actuator",
    "rotary",
    "flap",
    "leading edge",
    "multi-function",
    "vadr",
    "lefra",
    "camera",
    "cameras",
)
_EXCHANGE_SOFTWARE = (
    "microsoft",
    "exchange online",
    "exchange server",
    "office 365",
    "microsoft 365",
    "outlook",
    "mailbox",
    "caixa de correio",
    "correio eletronico",
    "licenciamento",
)


def _exchange_is_false_friend(folded: str) -> bool:
    """«Exchange» aeronáutico / peças ≠ Microsoft Exchange."""
    if any(token in folded for token in _EXCHANGE_SOFTWARE):
        return False
    if any(token in folded for token in _EXCHANGE_HARDWARE):
        return True
    if re.search(r"\b\d+\s*ea\b", folded):
        return True
    return False


def is_rejected_false_friend(text: str, keywords: list[Keyword]) -> bool:
    """Verdadeiro se o texto só tem um falso amigo rejeitado, sem match."""
    if find_match(text, keywords) is not None:
        return False
    folded = fold(text)
    for kw in keywords:
        if kw.kind != "reject":
            continue
        if _compile(kw.pattern).search(folded) is not None:
            return True
    return False


def keywords_for_report(keywords: list[Keyword]) -> list[dict[str, str]]:
    return [
        {"pattern": kw.pattern, "vendor": kw.vendor, "kind": kw.kind} for kw in keywords
    ]
