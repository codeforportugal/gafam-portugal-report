"""Resolução de nomes de colunas em folhas Excel (case-insensitive)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def pick_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    """Devolve o nome real da primeira coluna que casa com *candidates*."""
    lower = {str(c).lower(): c for c in frame.columns}
    for name in candidates:
        key = name.lower()
        if key in lower:
            return str(lower[key])
    for key, original in lower.items():
        for name in candidates:
            if name.lower() in key:
                return str(original)
    return None
