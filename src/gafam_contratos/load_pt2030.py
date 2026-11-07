"""Operações Portugal 2030."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gafam_contratos.amounts import parse_amount, parse_date, year_in_scope
from gafam_contratos.classify import classify_institution, region_from_local
from gafam_contratos.columns import pick_column
from gafam_contratos.constants import YEARS
from gafam_contratos.lexicon import Keyword, find_match
from gafam_contratos.models import Record, SourceMeta

PT2030_URL = (
    "https://portugal2030.pt/wp-content/uploads/sites/3/2026/10/"
    "PT2030-Lista-Operacoes-a-Publicar_30-set-2026.xlsx"
)
_col = pick_column


def load_pt2030(
    path: Path,
    keywords: list[Keyword],
    concelho_map: dict[str, str],
) -> list[Record]:
    frame = pd.read_excel(path)
    code_col = _col(frame, "código da operação", "operation code", "codigo")
    name_col = _col(frame, "nome da operação", "name of the operation")
    purpose_col = _col(frame, "finalidade da operação", "purpose")
    buyer_col = _col(frame, "nome do beneficiário", "beneficiary")
    fund_col = _col(frame, "fundo total aprovado", "total approved fund")
    cost_col = _col(frame, "custo total da operação", "total cost")
    start_col = _col(frame, "data início", "start date")
    nuts_col = _col(frame, "nuts ii", "nuts 2")
    records: list[Record] = []
    for _, row in frame.iterrows():
        nome = str(row[name_col] if name_col else "")
        purpose = str(row[purpose_col] if purpose_col else "")
        buyer = str(row[buyer_col] if buyer_col else "")
        text = " ".join(part for part in (nome, purpose, buyer) if part)
        hit = find_match(text, keywords)
        if hit is None:
            continue
        when = parse_date(row[start_col] if start_col else None)
        if not year_in_scope(when, YEARS):
            continue
        amount = parse_amount(row[fund_col] if fund_col else None)
        if amount is None:
            amount = parse_amount(row[cost_col] if cost_col else None)
        if amount is None:
            continue
        category = classify_institution(buyer)
        headline = category != "privado"
        nuts = str(row[nuts_col] if nuts_col else "")
        region = region_from_local(nuts, concelho_map)
        oid = str(row[code_col]).strip() if code_col else f"g-{len(records)}"
        records.append(
            Record(
                source_id=oid,
                channel="grant",
                buyer=buyer,
                excerpt=hit.excerpt,
                amount_eur=amount,
                region=region,
                category=category,
                vendor=hit.vendor,
                fundos="",
                year=when.year if when else 0,
                headline=headline,
                product=hit.term,
            )
        )
    return records


def pt2030_source() -> SourceMeta:
    return SourceMeta(
        id="pt2030",
        publisher="Agência para o Desenvolvimento e Coesão",
        title="Lista de Operações Aprovadas Portugal 2030",
        url=PT2030_URL,
        file_name="PT2030-Lista-Operacoes-a-Publicar_30-set-2026.xlsx",
        licence="Não especificada",
        coverage="Operações com início em 2022–2026",
        updated="2026-09-30",
    )
