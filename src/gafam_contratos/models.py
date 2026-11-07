"""Registos normalizados."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Record:
    source_id: str
    channel: str  # committed | requested | grant | sciproj
    buyer: str
    excerpt: str
    amount_eur: float
    region: str
    category: str
    vendor: str
    fundos: str
    year: int
    headline: bool
    product: str = ""
    url: str = ""
    place: str = ""
    district: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PressLink:
    title: str
    url: str
    date: str
    product: str
    buyer: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceMeta:
    id: str
    publisher: str
    title: str
    url: str
    file_name: str
    licence: str
    coverage: str
    updated: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
