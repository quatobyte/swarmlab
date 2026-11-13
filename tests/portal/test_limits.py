"""Портал M9b: лимиты матчей, очередь, простой без зрителей, лимиты серий (DECISIONS №94).

В `master` нет модуля, поэтому процесс матча — подставной воркер (`fake_worker.py`) с тем же
каналом; конфиги — модуль-заглушка `fake` (ядро модуль не загружает до воркера). Настоящие
матчи под песочницей — в ветке модуля.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import msgpack
import pytest
from websockets.sync.client import connect

from swarmlab.server import app as app_module
from swarmlab.server.accounts import load_settings
from swarmlab.server.app import SeriesProcess
from swarmlab.server.public import check_sandbox

from .conftest import ROOT, Client, Portal

FAKE_WORKER = Path(__file__).with_name("fake_worker.py")
PROFILE = "# профиль-заглушка\nfake:\n  world:\n    map_size: 100.0\n  pool:\n    max: 10\n"


def _configs(root: Path) -> None:
    cfg = root / "configs"
    (cfg / "matches").mkdir(parents=True)
    (cfg / "fake").mkdir()
    (cfg / "profiles").mkdir()
    (cfg / "fake" / "defaults.yaml").write_text("{}\n", encoding="utf-8")
    for name in ("small", "medium", "large"):
        (cfg / "profiles" / f"{name}.yaml").write_text(PROFILE, encoding="utf-8")
    (cfg / "matches" / "demo.yaml").write_text(
        "# матч-заглушка\nmodule: fake\nseed: 1\nprofile: small\nduration_s: 60\n",
        encoding="utf-8")


@pytest.fixture
def make(make_portal, monkeypatch):
    monkeypatch.setattr(app_module, "WORKER_ARGS", [str(FAKE_WORKER)])

    def build(**settings: Any) -> Portal:
        p = make_portal(**settings)
        _configs(p.cfg.root)
        return p

    return build


def _start(c: Client, *overrides: str) -> tuple[int, Any]:
    return c.json("POST", "/api/matches", {"match": "demo.yaml", "overrides": list(overrides)})


def _wait(c: Client, mid: str, state: str, timeout: float = 20) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        info = c.json("GET", f"/api/matches/{mid}")[1]
        if info["state"] == state:
            return info
        assert time.monotonic() < deadline, f"{mid}: {info['state']} вместо {state}"
        time.sleep(0.05)


def _uid(portal: Portal, client: Client) -> int:
    email = client.json("GET", "/api/me")[1]["email"]
    return int(portal.portal.db.one("SELECT id FROM users WHERE email = ?", (email,))["id"])


def _ws(portal: Portal, c: Client, mid: str):
    return connect(f"{portal.ws}/ws/matches/{mid}", open_timeout=10,
                   additional_headers={"Cookie": c.cookie_header(), "Origin": portal.base})


# ====================================================================== матчи


def test_second_match_of_same_user_replaces_only_his_first(make):
    p = make()
    a, b = p.user("a@b.ru"), p.user("b@b.ru")
    m1 = _start(a)[1]["id"]
    mb = _start(b)[1]["id"]
    _wait(a, m1, "running")
    _wait(b, mb, "running")
    m2 = _start(a)[1]["id"]
    _wait(a, m1, "stopped")
    _wait(a, m2, "running")
    assert _wait(b, mb, "running")["queue"] is None  # чужой матч не вытеснен


def test_fifth_match_waits_in_queue_with_number_and_starts_when_slot_frees(make):
    p = make(limits={"register_per_ip": 100})
    users = [p.user(f"u{i}@b.ru") for i in range(6)]
    mids = [_start(u)[1]["id"] for u in users]
    for u, mid in zip(users[:4], mids[:4], strict=True):
        _wait(u, mid, "running")
    fifth, sixth = _wait(users[4], mids[4], "queued"), _wait(users[5], mids[5], "queued")
    assert (fifth["queue"], sixth["queue"]) == (1, 2)
    assert p.app.state.manager.active() == 4
    # Номер в очереди видит и зритель (WS): пакет status {state: queued, queue}.
    with _ws(p, users[4], mids[4]) as ws:
        st = msgpack.unpackb(ws.recv(timeout=10), raw=False)
        assert (st["t"], st["state"], st["queue"]) == ("status", "queued", 1)
        # Место освободилось — пятый стартует сам, шестой — первый в очереди.
        assert users[0].json("POST", f"/api/matches/{mids[0]}/stop")[0] == 200
        _wait(users[4], mids[4], "running")
        states = []
        while "running" not in states:
            states.append(msgpack.unpackb(ws.recv(timeout=10), raw=False).get("state"))
        assert "starting" in states
    assert _wait(users[5], mids[5], "queued")["queue"] == 1
    assert p.app.state.manager.active() == 4


def test_user_replacing_own_match_keeps_place_at_front(make):
    p = make(matches={"total": 1})
    a, b = p.user("a@b.ru"), p.user("b@b.ru")
    m1 = _start(a)[1]["id"]
    _wait(a, m1, "running")
    mb = _start(b)[1]["id"]
    assert _wait(b, mb, "queued")["queue"] == 1
    m2 = _start(a)[1]["id"]  # вытесняет свой m1: место m1 — его новому матчу
    _wait(a, m2, "running")
    _wait(a, m1, "stopped")
    assert _wait(b, mb, "queued")["queue"] == 1
    # Свой матч из очереди тоже вытесняется новым (снят, не начавшись).
    a2 = _start(b)[1]["id"]
    assert _wait(b, mb, "stopped")["replay"] is None
    assert _wait(b, a2, "queued")["queue"] == 1


def test_stop_of_queued_match_removes_it_from_queue(make):
    p = make(matches={"total": 1})
    a, b, c = p.user("a@b.ru"), p.user("b@b.ru"), p.user("c@b.ru")
    ma = _start(a)[1]["id"]
    _wait(a, ma, "running")
    mb, mc = _start(b)[1]["id"], _start(c)[1]["id"]
    assert _wait(c, mc, "queued")["queue"] == 2
    assert b.json("POST", f"/api/matches/{mb}/stop")[1]["state"] == "stopped"
    assert _wait(c, mc, "queued")["queue"] == 1
    assert p.app.state.manager.active() == 1


@pytest.mark.parametrize("override, part", [
    ("profile=large", "Профиль large"),
    ("world.map_size=1000", "задаёт профиль"),
    ("overrides.pool.max=500", "задаёт профиль"),
    ("world={map_size: 1000}", "задаёт профиль"),
    ("runner.budget_ms=1000", "нельзя менять"),
    ("runner={hard_timeout_ms: 100000}", "нельзя менять"),
    ("timing.decision_hz=100", "нельзя менять"),
    ("module=other", ""),  # другого модуля нет — 400 уже на сборке конфига
])
def test_disallowed_profile_or_locked_keys_are_400(make, override, part):
    p = make()
    a = p.user("a@b.ru")
    code, data = _start(a, override)
    assert code == 400 and part in str(data["detail"]), data
    assert not p.app.state.manager.matches  # процесс не запускался


def test_allowed_overrides_on_portal(make):
    p = make()
    a = p.user("a@b.ru")
    code, data = _start(a, "profile=medium", "duration_s=30", "world.extra=1",
                        "enemies.spiders.enabled=false")
    assert code == 200, data
    _wait(a, data["id"], "running")


def test_match_without_viewers_stops_after_idle_time(make):
    p = make(matches={"idle_stop_s": 0.6})
    a = p.user("a@b.ru")
    mid = _start(a)[1]["id"]
    _wait(a, mid, "running")
    t0 = time.monotonic()
    _wait(a, mid, "stopped", timeout=10)
    assert time.monotonic() - t0 >= 0.3


def test_viewer_keeps_match_alive_queued_place_without_viewers_is_dropped(make):
    p = make(matches={"idle_stop_s": 0.6, "total": 1})
    a, b = p.user("a@b.ru"), p.user("b@b.ru")
    ma = _start(a)[1]["id"]
    with _ws(p, a, ma):
        _wait(a, ma, "running")
        mb = _start(b)[1]["id"]
        assert _wait(b, mb, "queued")["queue"] == 1
        _wait(b, mb, "stopped", timeout=10)  # место в очереди без зрителей — снято
        time.sleep(1.0)
        assert _wait(a, ma, "running")["viewers"] == 1  # со зрителем матч идёт
    _wait(a, ma, "stopped", timeout=10)  # зритель ушёл — через idle_stop_s остановлен
    assert not p.app.state.manager.queue


def test_runner_sandbox_prefix_and_user_folders_go_to_worker(make, tmp_path, monkeypatch):
    record = tmp_path / "start.jsonl"
    monkeypatch.setenv("SWARMLAB_FAKE_WORKER_RECORD", str(record))
    prefix = ["jail", "--ro", "{script}", "--"]
    p = make(sandbox={"runner_prefix": prefix})
    a = p.user("a@b.ru")
    _wait(a, _start(a)[1]["id"], "running")
    start = json.loads(record.read_text(encoding="utf-8").splitlines()[-1])
    assert start["runner_launch"] == {"prefix": prefix}
    uid = _uid(p, a)
    assert any(Path(d).parts[-2:] == (str(uid), "scripts") for d in start["script_dirs"])


# ====================================================================== серии


def test_series_over_n_or_jobs_is_400(make):
    p = make()
    a = p.user("a@b.ru")
    code, data = a.json("POST", "/api/series", {"match": "demo.yaml", "n": 11})
    assert code == 400 and "до 10" in data["detail"]
    code, data = a.json("POST", "/api/series", {"match": "demo.yaml", "n": 5, "jobs": 2})
    assert code == 400 and "не больше 1" in data["detail"]
    code, data = a.json("POST", "/api/series", {"match": "demo.yaml", "n": 5,
                                                "overrides": ["profile=large"]})
    assert code == 400 and "Профиль large" in data["detail"]
    assert a.json("GET", "/api/series") == (200, [])


def test_second_series_on_server_is_409(make, tmp_path):
    p = make()
    a, b = p.user("a@b.ru"), p.user("b@b.ru")
    busy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        p.app.state.series.running["20261111-120000-a"] = SeriesProcess(
            id="20261111-120000-a", dir=tmp_path / "a-series", proc=busy)
        code, data = b.json("POST", "/api/series", {"match": "demo.yaml", "n": 3})
        assert code == 409 and "Уже идёт серия" in data["detail"]
        assert "20261111" not in data["detail"]  # чужую серию не называем
    finally:
        busy.kill()
        busy.wait()
    del a


def test_portal_series_runs_with_one_job_user_folders_and_sandbox(make, monkeypatch):
    p = make(sandbox={"runner_prefix": ["jail", "{script}", "--"]})
    a = p.user("a@b.ru")
    folder = p.cfg.data / "users" / str(_uid(p, a)) / "series" / "s1"
    folder.mkdir(parents=True)
    (folder / "series.json").write_text(json.dumps({"id": "s1", "state": "finished",
                                                    "matches": []}), encoding="utf-8")
    seen: dict[str, list[str]] = {}
    real = subprocess.Popen

    def spy(cmd, **kw):
        seen["cmd"] = cmd
        hello = json.dumps({"t": "start", "id": "s1", "dir": str(folder)})
        return real([sys.executable, "-c", f"print({hello!r})"], **kw)

    monkeypatch.setattr(app_module.subprocess, "Popen", spy)
    code, data = a.json("POST", "/api/series", {"match": "demo.yaml", "n": 3})
    assert code == 200, data
    cmd = seen["cmd"]
    assert cmd[cmd.index("--jobs") + 1] == "1"
    assert Path(cmd[cmd.index("--out") + 1]) == folder.parent
    assert json.loads(cmd[cmd.index("--runner-prefix-json") + 1]) == ["jail", "{script}", "--"]
    assert cmd.count("--script-dir") == 3
    # Серии другого пользователя не видны.
    b = p.user("b@b.ru")
    assert b.json("GET", "/api/series") == (200, [])
    assert b.json("GET", "/api/series/s1")[0] == 404
    assert [s["id"] for s in a.json("GET", "/api/series")[1]] == ["s1"]


# ====================================================================== локальный режим


def test_local_mode_has_no_queue_no_limits_new_match_replaces_old(make):
    p = make(public=False)
    c = p.client()
    m1 = _start(c, "runner.budget_ms=50", "profile=large")[1]["id"]
    _wait(c, m1, "running")
    m2 = _start(c)[1]["id"]
    _wait(c, m1, "stopped")
    assert _wait(c, m2, "running")["queue"] is None
    assert p.app.state.manager.limits is None and not p.app.state.manager.queue


# ====================================================================== песочница


def test_public_yaml_wraps_runner_in_nsjail_config_from_repo():
    prefix = load_settings().sandbox.runner_prefix
    assert prefix[0] == "nsjail" and prefix[-1] == "--" and "{script}" in prefix
    cfg = prefix[prefix.index("--config") + 1]
    assert cfg == "/app/docker/runner.nsjail.cfg"  # путь в образе (Dockerfile: COPY . /app)
    assert (ROOT / "docker" / "runner.nsjail.cfg").is_file()


def test_portal_does_not_start_without_sandbox_program():
    s = load_settings().model_copy(deep=True)
    s.sandbox.runner_prefix = ["definitely-no-such-sandbox-binary", "--"]
    problem = check_sandbox(s)
    assert problem and "не найдена" in problem and "runner_prefix: []" in problem
    s.sandbox.runner_prefix = []
    assert check_sandbox(s) is None
