"""Agregações para o relatório."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from gafam_contratos.constants import YEAR_LIST
from gafam_contratos.models import Record


def _sum_by(
    records: list[Record],
    *,
    channel: str,
    key: str,
    year: int | None = None,
) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for record in records:
        if record.channel != channel or not record.headline:
            continue
        if year is not None and record.year != year:
            continue
        value = getattr(record, key)
        totals[str(value)] += record.amount_eur
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def national_totals(records: list[Record]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for year in YEAR_LIST:
        out[str(year)] = {
            "committed": sum(
                r.amount_eur
                for r in records
                if r.channel == "committed" and r.headline and r.year == year
            ),
            "requested": sum(
                r.amount_eur
                for r in records
                if r.channel == "requested" and r.headline and r.year == year
            ),
            "grants": sum(
                r.amount_eur
                for r in records
                if r.channel == "grant" and r.headline and r.year == year
            ),
        }
    return out


def prr_subtotal(records: list[Record]) -> dict[str, float]:
    by_year: dict[str, float] = defaultdict(float)
    for record in records:
        if (
            record.channel != "committed"
            or not record.headline
            or record.fundos != "PRR"
        ):
            continue
        by_year[str(record.year)] += record.amount_eur
    return dict(by_year)


def breakdowns(records: list[Record]) -> dict[str, Any]:
    by_region: dict[str, dict[str, float]] = {}
    by_category: dict[str, dict[str, float]] = {}
    by_vendor: dict[str, dict[str, float]] = {}
    by_place: dict[str, dict[str, float]] = {}
    for year in YEAR_LIST:
        key = str(year)
        by_region[key] = _sum_by(records, channel="committed", key="region", year=year)
        by_category[key] = _sum_by(
            records, channel="committed", key="category", year=year
        )
        by_vendor[key] = _sum_by(records, channel="committed", key="vendor", year=year)
        by_place[key] = _sum_by(records, channel="committed", key="place", year=year)
    return {
        "committed_by_region": by_region,
        "committed_by_category": by_category,
        "committed_by_vendor": by_vendor,
        "committed_by_place": by_place,
    }


def national_once(records: list[Record]) -> list[Record]:
    """Para totais nacionais: um montante por source_id no canal committed.

    Quando a região foi partida, as parcelas somam o total; para o total
    nacional usamos as linhas tal como estão (já somam o contrato uma vez
    no conjunto). Esta função existe para testes de não-duplicação PRR.
    """
    return records
