"""Caminhos do projecto."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return project_root() / "data"


def schema_path() -> Path:
    return project_root() / "schema" / "report.schema.json"


def reports_dir() -> Path:
    return project_root() / "reports"


def fixtures_dir() -> Path:
    return project_root() / "tests" / "fixtures"


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
