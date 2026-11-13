"""Запуск раннера: префикс команды и чистое окружение (M9b, ARCHITECTURE §3.4).

Идут на любой ОС: вместо песочницы — обёртка на Python, которая записывает свои аргументы и
окружение и запускает остальную команду с теми же stdin/stdout. Проверки самой песочницы
nsjail в Linux-контейнере ещё предстоит добавить по критериям M9b.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from swarmlab.core.config import RunnerConfig
from swarmlab.core.module import TeamSpec
from swarmlab.core.runner_host import (
    DISABLED,
    ProcessLink,
    RunnerLaunch,
    TeamLog,
    package_root,
    runner_env,
)

WRAPPER = '''
import json, os, subprocess, sys
out, rest = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
with open(out, "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "env": dict(os.environ)}, f)
sys.exit(subprocess.call(rest))
'''


def test_command_without_prefix_is_plain_runner(tmp_path: Path) -> None:
    script = tmp_path / "hive.py"
    assert RunnerLaunch().command("py", script) == ["py", "-m", "swarmlab.runner"]


def test_prefix_placeholders_are_substituted(tmp_path: Path) -> None:
    script = tmp_path / "sub" / "hive.py"
    launch = RunnerLaunch(("jail", "--ro", "{script}", "--dir={script_dir}", "--py", "{python}",
                           "--"))
    cmd = launch.command("/usr/bin/python3", script)
    assert cmd == ["jail", "--ro", str(script.resolve()), f"--dir={script.parent.resolve()}",
                   "--py", "/usr/bin/python3", "--", "/usr/bin/python3", "-m", "swarmlab.runner"]
    assert launch.command("py", script, ["probe.py"])[-2:] == ["py", "probe.py"]


def test_launch_message_round_trip() -> None:
    assert RunnerLaunch.from_message(None) is None
    assert RunnerLaunch.from_message({"prefix": []}) is None
    launch = RunnerLaunch(("a", "{script}"))
    assert RunnerLaunch.from_message(launch.to_message()) == launch


def test_runner_env_has_no_server_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWARMLAB_SECRET_KEY", "очень секретно")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/swarmlab.db")
    env = runner_env()
    assert env["PYTHONHASHSEED"] == "0"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert Path(env["PYTHONPATH"]) == package_root()
    assert (package_root() / "swarmlab" / "__init__.py").is_file()
    allowed = {"PYTHONHASHSEED", "PYTHONIOENCODING", "PYTHONUNBUFFERED", "PYTHONPATH",
               "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    assert set(env) <= allowed
    assert "очень секретно" not in json.dumps(env, ensure_ascii=False)


def _link(tmp_path: Path, launch: RunnerLaunch | None) -> ProcessLink:
    script = tmp_path / "scripts" / "hive.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("def loop(self):\n    pass\n", encoding="utf-8")
    # Модуля с таким именем нет ни в одной ветке: раннер ответит ready{ok: false} — этого
    # достаточно, чтобы проверить запуск и рукопожатие через префикс.
    return ProcessLink(TeamSpec(team=1, name="hive1", script=script), module="no-such-module",
                       seed=1, cfg=RunnerConfig(), options={}, log=TeamLog(None),
                       launch=launch)


def test_runner_starts_through_prefix_with_clean_env(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWARMLAB_SECRET_KEY", "очень секретно")
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(WRAPPER, encoding="utf-8")
    record = tmp_path / "record.json"
    launch = RunnerLaunch((sys.executable, str(wrapper), str(record), "{script}", "--"))
    link = _link(tmp_path, launch)
    try:
        link.start()
        assert not link.poll_ready(time.monotonic() + 30)
        assert link.state == DISABLED
        assert "no-such-module" in (link.load_error or "")  # ответ раннера прошёл через префикс
    finally:
        link.close()
    seen = json.loads(record.read_text(encoding="utf-8"))
    script = (tmp_path / "scripts" / "hive.py").resolve()
    assert seen["argv"][:3] == [str(record), str(script), "--"]
    assert seen["argv"][3:] == [sys.executable, "-m", "swarmlab.runner"]
    assert "SWARMLAB_SECRET_KEY" not in seen["env"]
    assert seen["env"]["PYTHONHASHSEED"] == "0"


def test_runner_without_prefix_does_not_inherit_secrets(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Локальный режим: запуск как раньше, но окружение тоже чистое."""
    monkeypatch.setenv("SWARMLAB_SECRET_KEY", "очень секретно")
    seen: dict[str, object] = {}
    real_popen = __import__("subprocess").Popen

    def spy(cmd: list[str], **kw: object) -> object:
        seen["cmd"], seen["env"] = cmd, kw.get("env")
        return real_popen(cmd, **kw)

    monkeypatch.setattr("swarmlab.core.runner_host.subprocess.Popen", spy)
    link = _link(tmp_path, None)
    try:
        link.start()
        link.poll_ready(time.monotonic() + 30)
    finally:
        link.close()
    assert seen["cmd"] == [sys.executable, "-m", "swarmlab.runner"]
    env = seen["env"]
    assert isinstance(env, dict) and "SWARMLAB_SECRET_KEY" not in env
    assert os.environ["SWARMLAB_SECRET_KEY"] == "очень секретно"
