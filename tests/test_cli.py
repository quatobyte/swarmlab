from swarmlab.cli import main


def test_run_headless_prints_rtf_and_writes_replay(m0_match, tmp_path, capsys):
    replay = tmp_path / "m0.swr"
    assert main(["run", str(m0_match), "--headless", "--duration", "2",
                 "--replay", str(replay)]) == 0
    out = capsys.readouterr().out
    assert "RTF =" in out and "Реплей:" in out and replay.is_file()
    assert main(["replay", str(replay)]) == 0
    out = capsys.readouterr().out
    assert "совпадает" in out and "кадров 20" in out


def test_run_without_replay(m0_match, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["run", str(m0_match), "--duration", "1", "--no-replay"]) == 0
    assert not (tmp_path / "replays").exists()


def test_bench_show_without_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARMLAB_HOME", str(tmp_path))
    assert main(["bench", "--show"]) == 1


def test_bad_config_returns_error(m0_match, capsys):
    assert main(["run", str(m0_match), "--set", "world.n_hives=7"]) != 0


def test_serve_without_web_dir_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("swarmlab.server.app.default_config",
                        lambda root=None: _no_web_config(tmp_path))
    assert main(["serve", "--root", str(tmp_path)]) == 1
    assert "Нет папки вьюера" in capsys.readouterr().err


def _no_web_config(tmp_path):
    from swarmlab.server.app import ServerConfig

    return ServerConfig(root=tmp_path, configs=tmp_path, replays=tmp_path, logs=tmp_path,
                        web=tmp_path / "web")
