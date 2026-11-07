from urllib.error import HTTPError

from gafam_contratos.retry import (
    fibonacci_waits,
    http_get,
    iter_spaced,
    retry_call,
    should_retry_status,
)


def test_fibonacci_waits():
    assert fibonacci_waits(0) == ()
    assert fibonacci_waits(8) == (1, 2, 3, 5, 8, 13, 21, 34)


def test_should_retry_status():
    assert should_retry_status(429)
    assert should_retry_status(503)
    assert not should_retry_status(404)


def test_retry_succeeds_after_timeouts():
    sleeps: list[float] = []
    state = {"n": 0}

    def operation() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise TimeoutError("slow")
        return "ok"

    assert retry_call(operation, sleeps=(1, 2, 3), sleeper=sleeps.append) == "ok"
    assert sleeps == [1.0, 2.0]


def test_retry_stops_on_404():
    def operation() -> None:
        raise HTTPError("http://x", 404, "no", hdrs=None, fp=None)  # type: ignore[arg-type]

    try:
        retry_call(operation, sleeps=(1,), sleeper=lambda _s: None)
        raise AssertionError("expected HTTPError")
    except HTTPError as exc:
        assert exc.code == 404


def test_retry_exhausts_waits():
    sleeps: list[float] = []

    def operation() -> None:
        raise TimeoutError("still")

    try:
        retry_call(operation, sleeps=(1, 2), sleeper=sleeps.append)
        raise AssertionError("expected TimeoutError")
    except TimeoutError:
        assert sleeps == [1.0, 2.0]


def test_retry_empty_sleeps_raises_last_error():
    try:
        retry_call(lambda: (_ for _ in ()).throw(TimeoutError("x")), sleeps=())
        raise AssertionError("expected TimeoutError")
    except TimeoutError:
        pass


def test_http_get_uses_retry(monkeypatch):
    calls: list[str] = []

    class FakeResp:
        def read(self) -> bytes:
            return b"body"

        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: object, timeout: float = 0) -> FakeResp:
        _ = timeout
        calls.append(str(getattr(req, "full_url", req)))
        return FakeResp()

    monkeypatch.setattr("gafam_contratos.retry.urlopen", fake_urlopen)
    assert http_get("https://example.pt/x", sleeper=lambda _s: None) == b"body"
    assert calls


def test_iter_spaced():
    gaps: list[float] = []
    items = list(iter_spaced([1, 2, 3], min_gap_seconds=5.0, sleeper=gaps.append))
    assert items == [1, 2, 3]
    assert gaps == [5.0, 5.0]
