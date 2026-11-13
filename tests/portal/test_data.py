"""Портал M9a: свои данные пользователя — скрипты, проекты, реплеи, матчи; удаление аккаунта."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from swarmlab.core.replay import unpack

from swarmlab.core.module import ScriptAccessError, TeamSpec, check_team_scripts
from swarmlab.server.accounts import Database, ReplaySettings
from swarmlab.server.app import MatchProcess
from swarmlab.server.storage import ReplayStore, user_dir

from .conftest import PASSWORD

CODE = "def loop(self):\n    self.wait(1)  # block:b1\n"
BLOCKS = {"format": 1, "mode": "blocks", "workspace": {"blocks": {"languageVersion": 0,
                                                                  "blocks": [{"id": "b1"}]}}}
PROJECT = {"format": 1, "name": "rival", "created": "2026-11-10T12:00:00", "mode": "python",
           "code": "def loop(self):\n    pass\n", "blocks": None}


def _uid(portal, client) -> int:
    email = client.json("GET", "/api/me")[1]["email"]
    row = portal.portal.db.one("SELECT id FROM users WHERE email = ?", (email,))
    return int(row["id"])


def _fake_replay(portal, uid: int, name: str, size: int = 100) -> Path:
    """Реплей, как после матча (матчей в master нет): строка в базе + файл."""
    store = portal.portal.replays
    store.start(uid, name)
    path = store.file(uid, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    store.finish(uid, name)
    return path


def _fake_match(portal, uid: int, mid: str) -> MatchProcess:
    """Матч без процесса (модуля в master нет): владелец и состояние — как у настоящего."""
    m = MatchProcess(id=mid, match="demo", seed=1, created="2026-11-11T12:00:00",
                     replay=Path("x.swr"), loop=None, owner=uid,  # type: ignore[arg-type]
                     state="running")
    portal.app.state.manager.matches[mid] = m
    return m


def test_user_a_cannot_see_open_change_download_or_delete_data_of_b(portal):
    a, b = portal.user("a@b.ru"), portal.user("b@b.ru")
    ua = _uid(portal, a)
    assert a.json("PUT", "/api/scripts/secret.py", {"text": CODE, "blocks": BLOCKS})[0] == 200
    code, pr = a.json("POST", "/api/projects", PROJECT)
    assert code == 200, pr
    _fake_replay(portal, ua, "demo-s1-20261111-120000")
    _fake_match(portal, ua, "demo-s1-20261111-120000")

    # Списки B — без данных A.
    assert "secret.py" not in {s["name"] for s in b.json("GET", "/api/scripts")[1]}
    assert b.json("GET", "/api/projects")[1] == []
    assert b.json("GET", "/api/replays")[1] == []
    assert b.json("GET", "/api/matches")[1] == []
    # Открыть, скачать, изменить, удалить — 404.
    assert b.json("GET", "/api/scripts/secret.py")[0] == 404
    assert b.json("DELETE", "/api/scripts/secret.py")[0] == 404
    assert b.json("GET", "/api/projects/rival")[0] == 404
    assert b.json("POST", "/api/projects/rival/to-editor", {})[0] == 404
    assert b.json("DELETE", "/api/projects/rival")[0] == 404
    assert b.raw("GET", "/api/replays/demo-s1-20261111-120000")[0] == 404
    assert b.json("POST", "/api/replays/demo-s1-20261111-120000/pin", {"pinned": True})[0] == 404
    assert b.json("DELETE", "/api/replays/demo-s1-20261111-120000")[0] == 404
    assert b.json("GET", "/api/matches/demo-s1-20261111-120000")[0] == 404
    assert b.json("POST", "/api/matches/demo-s1-20261111-120000/stop")[0] == 404
    # «Изменить» под тем же именем — это свой новый файл B, файл A не тронут.
    assert b.json("PUT", "/api/scripts/secret.py", {"text": "# B\n"})[0] == 200
    assert a.json("GET", "/api/scripts/secret.py")[1]["text"] == CODE
    # WS чужого матча — закрыт как несуществующий (4404).
    with connect(f"{portal.ws}/ws/matches/demo-s1-20261111-120000",
                 additional_headers={"Cookie": b.cookie_header()}, open_timeout=10) as ws:
        with pytest.raises(ConnectionClosed) as e:
            ws.recv(timeout=10)
    assert e.value.rcvd.code == 4404

    # Владелец видит всё своё.
    assert a.json("GET", "/api/scripts/secret.py")[0] == 200
    assert a.json("GET", "/api/projects/rival")[0] == 200
    code, _, body = a.raw("GET", "/api/replays/demo-s1-20261111-120000")
    assert code == 200 and len(body) == 100
    assert a.json("GET", "/api/matches/demo-s1-20261111-120000")[1]["state"] == "running"
    assert [m["id"] for m in a.json("GET", "/api/matches")[1]] == ["demo-s1-20261111-120000"]


def test_examples_shared_read_only_own_script_in_user_folder_export_same(portal):
    a = portal.user("a@b.ru")
    names = {s["name"]: s for s in a.json("GET", "/api/scripts")[1]}
    assert names["template.py"]["readonly"] and names["example_a.py"]["readonly"]
    assert "my_local.py" not in names  # скрипт локального режима — не общий пример
    assert a.json("GET", "/api/scripts/example_a.py")[1]["text"].startswith("def loop")
    code, data = a.json("PUT", "/api/scripts/example_a.py", {"text": "# моё\n"})
    assert code == 403 and "справочный" in data["detail"]
    assert a.json("DELETE", "/api/scripts/template.py")[0] == 403
    assert a.json("GET", "/api/scripts/my_local.py")[0] == 404

    code, saved = a.json("PUT", "/api/scripts/my_bees.py", {"text": CODE, "blocks": BLOCKS})
    assert code == 200 and saved["ok"]
    folder = user_dir(portal.cfg.data, _uid(portal, a)) / "scripts"
    assert (folder / "my_bees.py").read_text(encoding="utf-8") == CODE
    assert json.loads((folder / "my_bees.blocks.json").read_text(encoding="utf-8")) == BLOCKS
    assert not (portal.cfg.scripts / "my_bees.py").exists()
    assert saved["path"].startswith("data/users/")  # путь для конфига матча — внутри папки

    assert a.json("POST", "/api/projects", PROJECT)[0] == 200
    code, headers, raw = a.raw("GET", "/api/me/export")
    assert code == 200 and headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert sorted(z.namelist()) == ["projects/rival.swarm", "scripts/my_bees.swarm"]
    swarm = json.loads(z.read("scripts/my_bees.swarm"))
    assert swarm["format"] == 1 and swarm["name"] == "my_bees" and swarm["mode"] == "blocks"
    assert swarm["code"] == CODE and swarm["blocks"] == BLOCKS["workspace"]
    assert json.loads(z.read("projects/rival.swarm")) == PROJECT
    # Тот же .swarm загружается обратно — тот же код и блоки.
    code, _, back = a.raw("POST", "/api/projects", z.read("scripts/my_bees.swarm"),
                       {"Content-Type": "application/octet-stream"})
    assert code == 200
    code, proj = a.json("GET", f"/api/projects/{json.loads(back)['name']}")
    assert proj["code"] == CODE and proj["blocks"] == BLOCKS["workspace"]

    # Проект в редактор — в свою папку; удалить свой скрипт и проект можно.
    code, res = a.json("POST", "/api/projects/rival/to-editor", {})
    assert code == 200 and (folder / res["name"]).is_file()
    assert a.json("DELETE", "/api/scripts/my_bees.py")[0] == 200
    assert not (folder / "my_bees.py").exists() and not (folder / "my_bees.blocks.json").exists()
    assert a.json("DELETE", "/api/projects/rival")[0] == 200
    assert "rival" not in {p["name"] for p in a.json("GET", "/api/projects")[1]}


def test_team_script_outside_allowed_folders_is_refused(tmp_path):
    mine, shared, other = tmp_path / "a", tmp_path / "ex", tmp_path / "b"
    ok = [TeamSpec(0, "A", mine / "x.py"), TeamSpec(1, "B", shared / "example_a.py"),
          TeamSpec(2, "C", None)]
    check_team_scripts(ok, [mine, shared])
    with pytest.raises(ScriptAccessError, match="недоступен"):
        check_team_scripts([TeamSpec(0, "A", other / "x.py")], [mine, shared])
    with pytest.raises(ScriptAccessError):  # выход из папки через ..
        check_team_scripts([TeamSpec(0, "A", mine / ".." / "b" / "x.py")], [mine, shared])


# ====================================================================== реплеи


def _store(tmp_path: Path, clock: list[float], **over: float) -> tuple[ReplayStore, int]:
    db = Database(tmp_path / "db.sqlite")
    uid = int(db.run("INSERT INTO users (email, password_hash, created) VALUES ('a@b.ru', "
                     "'x', 0)").lastrowid)
    return ReplayStore(db, ReplaySettings(**over), tmp_path, clock=lambda: clock[0]), uid


def _match(store: ReplayStore, uid: int, name: str, clock: list[float], size: int = 10) -> None:
    clock[0] += 60
    store.start(uid, name)
    path = store.file(uid, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    store.finish(uid, name)


def test_after_11th_match_10_last_unpinned_kept_pinned_stay(tmp_path):
    clock = [1_000_000.0]
    store, uid = _store(tmp_path, clock)
    _match(store, uid, "m00", clock)
    store.pin(uid, "m00", True)
    for i in range(1, 12):
        _match(store, uid, f"m{i:02d}", clock)
    names = [r["id"] for r in store.list(uid)]
    assert names == [f"m{i:02d}" for i in range(11, 1, -1)] + ["m00"]  # 10 последних + закреплённый
    assert not store.file(uid, "m01").exists()
    # Пишущийся реплей не в списке и очисткой не трогается.
    store.start(uid, "m12")
    assert "m12" not in {r["id"] for r in store.list(uid)}


def test_pin_over_50_or_over_500_mb_is_clear_error(tmp_path):
    clock = [1_000_000.0]
    store, uid = _store(tmp_path, clock)
    for i in range(51):
        _match(store, uid, f"m{i:02d}", clock)
        if i < 50:
            store.pin(uid, f"m{i:02d}", True)
    with pytest.raises(Exception, match="предел \\(50\\)") as e:
        store.pin(uid, "m50", True)
    assert e.value.status == 409
    store.pin(uid, "m00", False)  # открепить одно — место есть
    store.pin(uid, "m50", True)

    store2, uid2 = _store(tmp_path / "mb", clock, pinned_max_mb=1)
    _match(store2, uid2, "big1", clock, size=600 * 1024)
    _match(store2, uid2, "big2", clock, size=600 * 1024)
    store2.pin(uid2, "big1", True)
    with pytest.raises(Exception, match="больше 1 МБ") as e:
        store2.pin(uid2, "big2", True)
    assert e.value.status == 409
    assert store2.usage(uid2)["pinned_count"] == 1


def test_unpinned_older_than_7_days_removed_by_cleanup_and_startup(tmp_path):
    clock = [1_000_000.0]
    store, uid = _store(tmp_path, clock)
    _match(store, uid, "old", clock)
    _match(store, uid, "kept", clock)
    store.pin(uid, "kept", True)
    clock[0] += 7 * 86400 + 120
    _match(store, uid, "new", clock)  # конец матча — очистка
    assert [r["id"] for r in store.list(uid)] == ["new", "kept"]
    assert not store.file(uid, "old").exists()

    # Старт сервера: файл без строки — в список; недописанная строка без файла — прочь.
    orphan = store.file(uid, "orphan")
    orphan.write_bytes(b"\0" * 5)
    os.utime(orphan, (clock[0], clock[0]))
    store.start(uid, "lost")
    store.startup([uid])
    assert {r["id"] for r in store.list(uid)} == {"new", "kept", "orphan"}
    assert store.db.one("SELECT 1 FROM replays WHERE name = 'lost'") is None
    clock[0] += 8 * 86400
    store.startup([uid])
    assert [r["id"] for r in store.list(uid)] == ["kept"]


def test_replays_over_http_pin_quota_message_download_delete(make_portal):
    p = make_portal(replays={"pinned_max_count": 1})
    a = p.user("a@b.ru")
    uid = _uid(p, a)
    _fake_replay(p, uid, "r1")
    _fake_replay(p, uid, "r2")
    code, info = a.json("POST", "/api/replays/r1/pin", {"pinned": True})
    assert code == 200 and info["pinned"]
    code, data = a.json("POST", "/api/replays/r2/pin", {"pinned": True})
    assert code == 409 and "предел (1)" in data["detail"]
    assert a.json("GET", "/api/me")[1]["usage"]["pinned_count"] == 1
    assert a.raw("GET", "/api/replays/r2.swr")[0] == 200
    assert a.json("DELETE", "/api/replays/r2")[0] == 200
    assert [r["id"] for r in a.json("GET", "/api/replays")[1]] == ["r1"]


# ====================================================================== профиль


def test_change_and_delete_account_need_current_password_then_nothing_left(portal):
    a = portal.user("a@b.ru")
    other_device = portal.client()
    assert other_device.login("a@b.ru")[0] == 200
    b = portal.user("b@b.ru")
    uid = _uid(portal, a)

    new = {"current": PASSWORD, "new": "new pass 123"}
    code, data = a.json("POST", "/api/me/password", {**new, "current": "wrong pass"})
    assert code == 403 and "текущий пароль" in data["detail"]
    code, data = a.json("POST", "/api/me/password", {"current": PASSWORD, "new": "short"})
    assert code == 400
    assert a.json("POST", "/api/me/password", new)[0] == 200
    assert a.json("GET", "/api/me")[0] == 200  # эта сессия жива
    assert other_device.json("GET", "/api/me")[0] == 401  # остальные закрыты
    assert portal.client().login("a@b.ru")[0] == 401
    assert portal.client().login("a@b.ru", "new pass 123")[0] == 200

    assert a.json("PUT", "/api/scripts/mine.py", {"text": CODE})[0] == 200
    _fake_replay(portal, uid, "r1")
    m = _fake_match(portal, uid, "live-1")
    folder = user_dir(portal.cfg.data, uid)
    assert folder.is_dir()

    code, data = a.json("DELETE", "/api/me", {"password": "new pass 12"})
    assert code == 403 and "текущий пароль" in data["detail"]
    code, _ = a.json("DELETE", "/api/me", {"password": "new pass 123"})
    assert code == 200
    assert "live-1" not in portal.app.state.manager.matches and m.owner == uid

    conn = sqlite3.connect(portal.cfg.data / "swarmlab.db")
    for table in ("users", "sessions", "replays"):
        col = "id" if table == "users" else "user_id"
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                            (uid,)).fetchone()[0] == 0, table
    assert not folder.exists()
    assert a.json("GET", "/api/me")[0] == 401
    assert portal.client().login("a@b.ru", "new pass 123")[0] == 401
    assert b.json("GET", "/api/me")[0] == 200  # другой пользователь на месте
    # id не переиспользуется: новый аккаунт не получит старую папку.
    c = portal.user("a@b.ru")
    assert _uid(portal, c) != uid


def test_real_bees_match_replay_and_websocket_belong_to_owner(make_portal):
    """Настоящий матч пчёл: приватность потока и реплея проверяется через HTTP и WS."""
    portal = make_portal(real_matches=True)
    a, b = portal.user("a@b.ru"), portal.user("b@b.ru")
    code, match = a.json("POST", "/api/matches", {
        "match": "m2_economy.yaml", "overrides": ["duration_s=5"],
    })
    assert code == 200, match
    mid = match["id"]
    assert b.json("GET", "/api/matches")[1] == []
    assert b.json("GET", f"/api/matches/{mid}")[0] == 404
    assert b.json("POST", f"/api/matches/{mid}/stop")[0] == 404
    with connect(f"{portal.ws}/ws/matches/{mid}",
                 additional_headers={"Cookie": b.cookie_header(), "Origin": portal.base}) as ws:
        with pytest.raises(ConnectionClosed) as closed:
            ws.recv(timeout=10)
    assert closed.value.rcvd.code == 4404
    with connect(f"{portal.ws}/ws/matches/{mid}",
                 additional_headers={"Cookie": a.cookie_header(), "Origin": portal.base}) as ws:
        assert unpack(ws.recv(timeout=10))["t"] in ("header", "status")

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        state = a.json("GET", f"/api/matches/{mid}")[1]["state"]
        if state in ("finished", "stopped", "error"):
            break
        time.sleep(0.1)
    assert state == "finished"
    # Статус finished приходит из воркера до его выхода и фиксации реплея в базе.
    while time.monotonic() < deadline:
        if mid in {r["id"] for r in a.json("GET", "/api/replays")[1]}:
            break
        time.sleep(0.1)
    assert mid in {r["id"] for r in a.json("GET", "/api/replays")[1]}
    assert b.json("GET", "/api/replays")[1] == []
    assert b.raw("GET", f"/api/replays/{mid}")[0] == 404
    code, _, replay = a.raw("GET", f"/api/replays/{mid}")
    assert code == 200 and len(replay) > 100
