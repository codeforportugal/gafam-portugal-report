"""Parsing de montantes e datas em formatos portugueses / Excel."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

_EXCEL_EPOCH = datetime(1899, 12, 30)


def parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number != number:  # NaN
            return None
        return number
    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return None
    text = text.replace("€", "").replace(" ", "").replace("\xa0", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (_EXCEL_EPOCH + timedelta(days=int(value))).date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    if text.replace(".", "", 1).isdigit():
        return (_EXCEL_EPOCH + timedelta(days=int(float(text)))).date()
    return None


def format_eur(amount: float) -> str:
    """Formato continental: 1 234,56 €."""
    sign = "-" if amount < 0 else ""
    absolute = abs(amount)
    whole, frac = f"{absolute:.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    grouped = " ".join(reversed(groups))
    return f"{sign}{grouped},{frac} €"


def format_eur_compact(amount: float) -> str:
    """Montante curto para cartões: floor em inteiros (54 milhões €, 537 mil €)."""
    sign = "-" if amount < 0 else ""
    absolute = abs(amount)
    if absolute >= 1_000_000:
        n = max(1, int(absolute // 1_000_000))
        unit = "milhão" if n == 1 else "milhões"
        return f"{sign}{n} {unit} €"
    if absolute >= 1_000:
        n = max(1, int(absolute // 1_000))
        return f"{sign}{n} mil €"
    return f"{sign}{int(absolute)} €"


def year_in_scope(value: date | None, years: set[int] | frozenset[int]) -> bool:
    return value is not None and value.year in years
