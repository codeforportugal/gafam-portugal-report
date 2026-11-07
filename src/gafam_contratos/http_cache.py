"""Descargas com cache local e retries Fibonacci."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path

from gafam_contratos.retry import http_get


def cached_get(
    url: str,
    cache_dir: Path,
    *,
    name: str | None = None,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
    timeout: float = 120.0,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        suffix = Path(url.split("?", 1)[0]).suffix or ".bin"
        name = f"{digest}{suffix}"
    target = cache_dir / name
    if target.exists() and target.stat().st_size > 0:
        return target
    payload = http_get(url, timeout=timeout, sleeps=sleeps, sleeper=sleeper)
    target.write_bytes(payload)
    return target
