"""Lista PRR: só marca contratos BASE, não soma euros."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from gafam_contratos.amounts import parse_amount
from gafam_contratos.columns import pick_column
from gafam_contratos.lexicon import Keyword, find_match
from gafam_contratos.models import SourceMeta

PRR_DATASET = "dataset-estrutura-de-missao-prr-contratos-publicos"
_col = pick_column


def _as_id(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", maxsplit=1)[0]
    return text


def load_prr_flags(path: Path, keywords: list[Keyword]) -> set[str]:
    """Ids BASE / NIF de linhas PRR com correspondência GAFAM clara."""
    frame = pd.read_excel(path)
    id_col = _col(
        frame,
        "cd_base_gov",
        "idcontrato",
        "id contrato",
        "nº contrato",
        "numero",
    )
    nif_col = _col(frame, "nif", "nif adjudicante", "nif entidade")
    amount_col = _col(
        frame,
        "montante_contratualizado",
        "valor",
        "montante",
        "preço",
        "preco",
    )
    desc_cols = [
        c
        for c in (
            _col(frame, "sumario"),
            _col(frame, "ds_contrato", "ds contrato"),
            _col(frame, "ds_projeto", "ds projeto"),
            _col(frame, "objeto", "descrição", "descricao", "designação"),
        )
        if c
    ]
    flags: set[str] = set()
    for _, row in frame.iterrows():
        text = " ".join(str(row[c]) for c in desc_cols)
        hit = find_match(text, keywords)
        if hit is None:
            continue
        cid = _as_id(row[id_col]) if id_col else ""
        if cid and cid not in {"0", "nan", "None"}:
            flags.add(cid)
            continue
        nif_raw = str(row[nif_col]).strip() if nif_col else ""
        nif_match = re.search(r"(\d{9})", nif_raw)
        nif = nif_match.group(1) if nif_match else ""
        amount = parse_amount(row[amount_col] if amount_col else None)
        token = hit.term.casefold()
        if nif and amount is not None:
            flags.add(f"{nif}|{amount:.2f}|{token}")
        if nif:
            flags.add(nif)
    return flags


def prr_source() -> SourceMeta:
    return SourceMeta(
        id="prr-contratos",
        publisher="Estrutura de Missão Recuperar Portugal",
        title="Contratos Públicos do PRR",
        url=f"https://dados.gov.pt/pt/datasets/{PRR_DATASET}/",
        file_name="listagem-de-contratos-do-prr.xlsx",
        licence="Aberta",
        coverage="Marca contratos BASE financiados pelo PRR",
        updated="2026-10-23",
    )
