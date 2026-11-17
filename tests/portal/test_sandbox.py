"""Проверка настоящей песочницы nsjail внутри Linux-образа портала."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from swarmlab.core.config import RunnerConfig
from swarmlab.core.module import TeamSpec
from swarmlab.core.runner_host import DISABLED, ProcessLink, RunnerLaunch, TeamLog, runner_env
from swarmlab.server.accounts import load_settings

CONFIG = Path("/app/docker/runner.nsjail.cfg")
NSJAIL = Path("/usr/local/bin/nsjail")
SANDBOX = {"runner_prefix": load_settings().sandbox.runner_prefix}
pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(sys.platform != "linux", reason="nsjail работает только в Linux-контейнере"),
    pytest.mark.skipif(not CONFIG.is_file() or not NSJAIL.is_file(),
                       reason="нужен тестовый Linux-образ с nsjail и /app/docker"),
]


def _run(code: str) -> dict[str, object]:
    result = subprocess.run(
        [str(NSJAIL), "--quiet", "--config", str(CONFIG), "--", sys.executable, "-c", code],
        env=runner_env(), capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_runner_protocol_survives_nsjail(tmp_path: Path) -> None:
    script = tmp_path / "player.py"
    script.write_text("def loop(self):\n    pass\n", encoding="utf-8")
    # nsjail монтирует исходный файл после перехода на внешний uid 100000. В pytest
    # временные родительские папки имеют 0700; дать только право прохода к файлу.
    for parent in (tmp_path, *tuple(p for p in tmp_path.parents if p != Path("/") and
                                     p != Path("/tmp"))):
        parent.chmod(parent.stat().st_mode | 0o111)
    launch = RunnerLaunch((str(NSJAIL), "--quiet", "--config", str(CONFIG),
                           "--bindmount_ro", "{script}", "--"))
    link = ProcessLink(TeamSpec(team=1, name="probe", script=script), module="no-such-module",
                       seed=1, cfg=RunnerConfig(), options={}, log=TeamLog(None), launch=launch)
    try:
        link.start()
        assert not link.poll_ready(time.monotonic() + 30)
        assert link.state == DISABLED, link.log.text()
        assert "no-such-module" in (link.load_error or "")
    finally:
        link.close()


def test_runner_has_separate_uid_and_nsjail_file_capabilities() -> None:
    caps = subprocess.run(["getcap", str(NSJAIL)], capture_output=True, text=True, check=True)
    assert all(cap in caps.stdout for cap in ("cap_setuid", "cap_setgid", "cap_kill"))
    assert _run("import os,json; print(json.dumps({'uid':os.getuid(),'gid':os.getgid()}))") == {
        "uid": 99999, "gid": 99999,
    }
    config = CONFIG.read_text(encoding="utf-8")
    assert config.count('outside_id: "100000"') == 2
    assert "use_newidmap: true" not in config


def test_sandbox_blocks_network_private_files_and_writes(tmp_path: Path) -> None:
    other_user_file = tmp_path / "users" / "other" / "scripts" / "private.py"
    other_user_file.parent.mkdir(parents=True)
    other_user_file.write_text("secret", encoding="utf-8")
    result = _run("""
import json, os, socket
def probe(fn):
    try:
        fn()
    except (OSError, PermissionError):
        return False
    return True
print(json.dumps({
    'network': probe(lambda: socket.create_connection(('1.1.1.1', 80), timeout=1)),
    'database': probe(lambda: open('/data/portal.sqlite', 'rb').read()),
    'other_user': probe(lambda: open(__OTHER_USER__, 'rb').read()),
    'home': probe(lambda: os.listdir('/home/swarmlab')),
    'app': probe(lambda: os.listdir('/app')),
    'write_package': probe(lambda: open('/usr/local/forbidden', 'wb').write(b'x')),
    'write_tmp': probe(lambda: open('/tmp/allowed', 'wb').write(b'x')),
}))
""".replace("__OTHER_USER__", repr(str(other_user_file))))
    assert result == {"network": False, "database": False, "other_user": False, "home": False,
                      "app": False, "write_package": False, "write_tmp": True}


def test_sandbox_limits_memory_processes_and_files() -> None:
    result = _run("""
import json, os, resource
limits = {name: resource.getrlimit(getattr(resource, 'RLIMIT_' + name))[0]
          for name in ('AS', 'NPROC', 'FSIZE', 'CPU')}
children = []
try:
    for _ in range(32):
        pid = os.fork()
        if pid == 0:
            import time
            time.sleep(5)
            os._exit(0)
        children.append(pid)
except OSError:
    pass
finally:
    for pid in children:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
try:
    bytearray(512 * 1024 * 1024)
    oversized_allocation = True
except MemoryError:
    oversized_allocation = False
print(json.dumps({'limits': limits, 'forked': len(children),
                  'oversized_allocation': oversized_allocation}))
""")
    limits = result["limits"]
    assert limits["AS"] <= 512 * 1024 * 1024
    assert limits["NPROC"] <= 16
    assert limits["FSIZE"] <= 16 * 1024 * 1024
    assert limits["CPU"] <= 900
    assert result["forked"] < 16
    assert result["oversized_allocation"] is False


def test_player_cannot_read_private_files_or_use_network_and_match_finishes(make_portal) -> None:
    portal = make_portal(real_matches=True, sandbox=SANDBOX, matches={"idle_stop_s": 30})
    player = portal.user("probe@example.test")
    other = portal.user("other@example.test")
    assert other.json("PUT", "/api/scripts/private.py", {
        "text": "SECRET = 'other user'\n",
    })[0] == 200
    player_id = portal.portal.db.one("SELECT id FROM users WHERE email = ?",
                                     ("probe@example.test",))["id"]
    other_id = portal.portal.db.one("SELECT id FROM users WHERE email = ?",
                                    ("other@example.test",))["id"]
    other_script = portal.cfg.data / "users" / str(other_id) / "scripts" / "private.py"
    code = """
from swarmlab.bees.api import Hive
import socket

class Probe(Hive):
    def loop(self):
        if getattr(self, 'checked', False):
            self.wait(1)
            return
        self.checked = True
        probes = {
            'network': lambda: socket.create_connection(('1.1.1.1', 80), timeout=0.2),
            'database': lambda: open(__DATABASE__, 'rb').read(),
            'other_user': lambda: open(__OTHER_SCRIPT__, 'rb').read(),
            'write_app': lambda: open('/app/forbidden', 'wb').write(b'x'),
            'memory': lambda: bytearray(512 * 1024 * 1024),
        }
        for name, probe in probes.items():
            try:
                probe()
            except (OSError, MemoryError) as exc:
                print('blocked', name, type(exc).__name__)
            else:
                print('escaped', name)
"""
    code = code.replace("__DATABASE__", repr(str(portal.portal.db.path)))
    code = code.replace("__OTHER_SCRIPT__", repr(str(other_script)))
    assert player.json("PUT", "/api/scripts/probe.py", {"text": code})[0] == 200
    script = portal.cfg.data / "users" / str(player_id) / "scripts" / "probe.py"
    for parent in script.parents:
        if parent == Path("/tmp"):
            break
        parent.chmod(parent.stat().st_mode | 0o111)
    response, match = player.json("POST", "/api/matches", {
        "match": "m2_economy.yaml", "overrides": [
            f"hives=[{{script: '{script.as_posix()}'}}]", "duration_s=5",
        ],
    })
    assert response == 200, match
    mid = match["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = player.json("GET", f"/api/matches/{mid}")[1]["state"]
        if state in ("finished", "stopped", "error"):
            break
        time.sleep(0.1)
    assert state == "finished"
    log_folder = portal.cfg.data / "users" / str(player_id) / "logs" / mid
    logs = "\n".join(path.read_text(encoding="utf-8") for path in log_folder.glob("*.log"))
    for name in ("network", "database", "other_user", "write_app", "memory"):
        assert f"blocked {name}" in logs, logs
    assert "escaped" not in logs


def test_real_match_stops_without_viewers_and_keeps_replay(make_portal) -> None:
    portal = make_portal(real_matches=True, sandbox=SANDBOX, matches={"idle_stop_s": 1})
    user = portal.user("sandbox@example.test")
    code, match = user.json("POST", "/api/matches", {
        "match": "m2_economy.yaml", "overrides": ["duration_s=120"],
    })
    assert code == 200, match
    mid = match["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = user.json("GET", f"/api/matches/{mid}")[1]["state"]
        if state in ("stopped", "error"):
            break
        time.sleep(0.1)
    assert state == "stopped"
    while time.monotonic() < deadline:
        if mid in {r["id"] for r in user.json("GET", "/api/replays")[1]}:
            break
        time.sleep(0.1)
    assert mid in {r["id"] for r in user.json("GET", "/api/replays")[1]}
    assert user.raw("GET", f"/api/replays/{mid}")[0] == 200


@pytest.mark.parametrize("body", [
    "while True:\n            pass",
    """for _ in range(32):
            try:
                pid = os.fork()
            except OSError:
                print('fork limit reached')
                break
            if pid == 0:
                import time
                time.sleep(60)
                os._exit(0)
        while True:
            pass""",
])
def test_hostile_runner_restarts_without_stopping_another_match(make_portal, body: str) -> None:
    portal = make_portal(real_matches=True, sandbox=SANDBOX,
                         matches={"total": 2, "idle_stop_s": 30})
    hostile, normal = portal.user("hostile@example.test"), portal.user("normal@example.test")
    code = ("from swarmlab.bees.api import Hive\nimport os\n"
            "class Hostile(Hive):\n    def loop(self):\n        ")
    code += body + "\n"
    assert hostile.json("PUT", "/api/scripts/hostile.py", {"text": code})[0] == 200
    uid = portal.portal.db.one("SELECT id FROM users WHERE email = ?",
                               ("hostile@example.test",))["id"]
    script = portal.cfg.data / "users" / str(uid) / "scripts" / "hostile.py"
    for parent in script.parents:
        if parent == Path("/tmp"):
            break
        parent.chmod(parent.stat().st_mode | 0o111)
    start = {"match": "m2_economy.yaml", "overrides": [
        f"hives=[{{script: '{script.as_posix()}'}}]", "duration_s=5",
    ]}
    code_status, hostile_match = hostile.json("POST", "/api/matches", start)
    assert code_status == 200, hostile_match
    hostile_id = hostile_match["id"]
    try:
        code_status, normal_match = normal.json("POST", "/api/matches", {
            "match": "m2_economy.yaml", "overrides": ["duration_s=5"],
        })
        assert code_status == 200, normal_match
        normal_id = normal_match["id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = normal.json("GET", f"/api/matches/{normal_id}")[1]["state"]
            if state in ("finished", "stopped", "error"):
                break
            time.sleep(0.1)
        assert state == "finished"
        log_folder = portal.cfg.data / "users" / str(uid) / "logs" / hostile_id
        while time.monotonic() < deadline:
            logs = "\n".join(path.read_text(encoding="utf-8")
                             for path in log_folder.glob("*.log"))
            if "перезапускается" in logs:
                break
            time.sleep(0.1)
        assert "перезапускается" in logs
    finally:
        hostile.json("POST", f"/api/matches/{hostile_id}/stop")
        match = portal.app.state.manager.matches[hostile_id]
        until = time.monotonic() + 10
        while not match.exited and time.monotonic() < until:
            time.sleep(0.1)
        assert match.exited
