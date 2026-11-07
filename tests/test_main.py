from gafam_contratos.__main__ import main


def test_main_fixture(monkeypatch, tmp_path):
    calls: list[bool] = []

    def fake_run(*, full: bool = False, **kwargs: object):
        _ = kwargs
        calls.append(full)
        return tmp_path

    monkeypatch.setattr("gafam_contratos.__main__.run", fake_run)
    assert main([]) == 0
    assert main(["--full"]) == 0
    assert calls == [False, True]
