"""HTTP GET com retries Fibonacci (1, 2, 3, 5, 8, 13, 21, 34).

Só reintenta timeouts, erros de ligação e HTTP 408/429/5xx.
Não há jitter; GDELT pede ainda um intervalo mínimo à parte (ver press.py).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

T = TypeVar("T")

RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
FIBONACCI_WAITS: tuple[int, ...] = (1, 2, 3, 5, 8, 13, 21, 34)


def fibonacci_waits(count: int = 8) -> tuple[int, ...]:
    """Devolve as primeiras *count* esperas Fibonacci a partir de 1, 2."""
    if count <= 0:
        return ()
    waits: list[int] = []
    a, b = 1, 2
    for _ in range(count):
        waits.append(a)
        a, b = b, a + b
    return tuple(waits)


def should_retry_status(status: int) -> bool:
    return status in RETRY_STATUS


def retry_call(
    operation: Callable[[], T],
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> T:
    """Tenta *operation*; após falha retriável espera a sequência Fibonacci."""
    waits = list(sleeps if sleeps is not None else FIBONACCI_WAITS)
    sleep_fn = sleeper if sleeper is not None else _default_sleep
    last_error: BaseException | None = None
    attempt = 0
    while True:
        try:
            return operation()
        except HTTPError as exc:
            last_error = exc
            if not should_retry_status(exc.code):
                raise
        except (TimeoutError, URLError, ConnectionError, OSError) as exc:
            last_error = exc
        if attempt >= len(waits):
            break
        sleep_fn(float(waits[attempt]))
        attempt += 1
    if last_error is None:  # pragma: no cover
        message = "retry_call failed without an error"
        raise RuntimeError(message)
    raise last_error


def http_get(
    url: str,
    *,
    timeout: float = 60.0,
    headers: dict[str, str] | None = None,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> bytes:
    """GET com retries Fibonacci."""

    def _fetch() -> bytes:
        req = Request(  # noqa: S310 — URLs públicas controladas pelo chamador
            url,
            headers=headers or {"User-Agent": "gafam-contratos/0.1"},
            method="GET",
        )
        with urlopen(req, timeout=timeout) as response:  # noqa: S310  # nosec B310
            return bytes(response.read())

    return retry_call(_fetch, sleeps=sleeps, sleeper=sleeper)


def iter_spaced(
    items: Sequence[T],
    *,
    min_gap_seconds: float,
    sleeper: Callable[[float], None] | None = None,
    initial_gap_seconds: float = 0.0,
) -> Iterator[T]:
    """Cede itens com intervalo mínimo entre eles (ex.: GDELT)."""
    sleep_fn = sleeper if sleeper is not None else _default_sleep
    first = True
    for item in items:
        if first:
            if initial_gap_seconds > 0:
                sleep_fn(initial_gap_seconds)
        else:
            sleep_fn(min_gap_seconds)
        first = False
        yield item


def _default_sleep(seconds: float) -> None:  # pragma: no cover
    import time

    time.sleep(seconds)
