from pathlib import Path

from gafam_contratos.http_cache import cached_get


def test_cached_get_writes_and_reuses(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_get(url: str, **kwargs: object) -> bytes:
        _ = url, kwargs
        calls["n"] += 1
        return b"hello"

    monkeypatch.setattr("gafam_contratos.http_cache.http_get", fake_get)
    first = cached_get("https://example.pt/f.xlsx", tmp_path, name="f.xlsx")
    second = cached_get("https://example.pt/f.xlsx", tmp_path, name="f.xlsx")
    assert first == second
    assert first.read_bytes() == b"hello"
    assert calls["n"] == 1
    auto = cached_get("https://example.pt/other.bin", tmp_path)
    assert auto.exists()
