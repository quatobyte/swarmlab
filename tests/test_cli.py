from swarmlab.cli import main


def test_run_headless_prints_rtf(m0_match, capsys):
    assert main(["run", str(m0_match), "--headless", "--duration", "2"]) == 0
    out = capsys.readouterr().out
    assert "RTF =" in out


def test_bad_config_returns_error(m0_match, capsys):
    assert main(["run", str(m0_match), "--set", "world.n_hives=7"]) != 0


def test_stubs_exit_nonzero(capsys):
    for cmd in ("bench", "replay", "serve"):
        assert main([cmd]) == 1
