"""Проекты `.swarm` и серии матчей на сервере (M7c, DECISIONS №63–66)."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from swarmlab.core.replay import read_replay
from swarmlab.server.projects import code_sha256

from .conftest import ROOT, Server

EXAMPLES = ROOT / "examples" / "bees"
NO_BUDGET = ["runner.budget_ms=100000", "runner.hard_timeout_ms=100000"]


def _project(name: str = "my_bees", mode: str = "python", code: str | None = None,
             blocks: dict | None = None) -> dict[str, Any]:
    if mode == "blocks" and blocks is None:
        blocks = json.loads((EXAMPLES / "my_blocks.blocks.json").read_text("utf-8"))["workspace"]
        code = code or (EXAMPLES / "my_blocks.py").read_text("utf-8")
    if code is None:
        code = (EXAMPLES / "example_basic.py").read_text("utf-8")
    return {"format": 1, "name": name, "created": "2026-10-23T12:00:00", "mode": mode,
            "code": code, "blocks": blocks if mode == "blocks" else None}


def _upload(server: Server, data: Any) -> tuple[int, Any]:
    raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(server.base + "/api/projects", data=raw, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


# ------------------------------------------------------------------ загрузка


def test_upload_checks_name_keeps_old_and_dedupes_same(server):
    """Критерий M7c: проверка имени, без перезаписи другого содержимого, тот же проект."""
    code, a = _upload(server, _project())
    assert code == 200 and a["status"] == "new" and a["name"] == "my_bees", a
    folder = server.cfg.projects
    assert sorted(p.name for p in folder.iterdir()) == ["my_bees.py", "my_bees.swarm"]
    assert a["sha256"] == code_sha256(_project()["code"])

    code, same = _upload(server, _project())
    assert code == 200 and same["status"] == "same" and same["name"] == "my_bees"
    assert len(list(folder.glob("*.swarm"))) == 1

    changed = _project(code="# другая версия\n" + _project()["code"])
    code, b = _upload(server, changed)
    assert code == 200 and b["status"] == "new"
    assert b["name"].startswith("my_bees-") and b["name"] != "my_bees"
    old = (folder / "my_bees.py").read_text("utf-8")
    assert old == _project()["code"]  # старый не перезаписан
    assert (folder / f"{b['name']}.py").read_text("utf-8").startswith("# другая версия")

    code, again = _upload(server, changed)  # тот же новый проект — снова он
    assert code == 200 and again["status"] == "same" and again["name"] == b["name"]

    for bad in ("../evil", "con", "1abc", "my bees", "имя", ""):
        code, err = _upload(server, _project(name=bad))
        assert code == 400 and "имя" in str(err).lower(), (bad, err)
    _, listed = server.json("GET", "/api/projects")
    assert sorted(p["name"] for p in listed) == sorted(["my_bees", b["name"]])


def test_broken_project_file_gives_clear_error(server):
    """Критерий M7c: битый файл — понятная ошибка."""
    cases = [
        (b"{not json", "битый JSON"),
        (json.dumps([1, 2]).encode(), "объект"),
        (json.dumps({**_project(), "format": 7}).encode(), "формат"),
        (json.dumps({k: v for k, v in _project().items() if k != "code"}).encode(), "кода"),
        (json.dumps({**_project(), "mode": "lisp"}).encode(), "режим"),
        (json.dumps({**_project("x", "blocks"), "blocks": None}).encode(), "блоков"),
    ]
    for raw, word in cases:
        code, err = _upload(server, raw)
        assert code == 400 and word in err["detail"], (raw[:40], err)
    assert not list(server.cfg.projects.glob("*")) if server.cfg.projects.exists() else True


def test_projects_not_in_editor_scripts_and_open_in_editor_keeps_code_and_blocks(server):
    """Критерий M7c: проекта нет в скриптах редактора; «в редактор» — тот же код и блоки."""
    for mode, name in (("python", "py_proj"), ("blocks", "bl_proj")):
        src = _project(name, mode)
        assert _upload(server, src)[0] == 200
        _, scripts = server.json("GET", "/api/scripts")
        assert f"{name}.py" not in {s["name"] for s in scripts}

        code, res = server.json("POST", f"/api/projects/{name}/to-editor", {})
        assert code == 200, res
        assert res["name"] == f"{name}.py"
        _, got = server.json("GET", f"/api/scripts/{res['name']}")
        assert got["text"] == src["code"] and not got["readonly"]
        if mode == "blocks":
            assert got["mode"] == "blocks"
            assert got["blocks"] == {"format": 1, "mode": "blocks", "workspace": src["blocks"]}
        else:
            assert got["blocks"] is None and got["mode"] == "python"
        # Повторное открытие не затирает свою копию — новое имя.
        _, res2 = server.json("POST", f"/api/projects/{name}/to-editor", {})
        assert res2["name"] == f"{name}_2.py"
    # Имя справочного скрипта не занимается.
    _upload(server, _project("example_basic"))
    _, res = server.json("POST", "/api/projects/example_basic/to-editor", {})
    assert res["name"] == "my_example_basic.py"


def test_match_with_projects_in_two_hives_runs(server):
    """Критерий M7c: матч из меню с загруженными проектами в двух ульях запускается и идёт."""
    _, a = _upload(server, _project("alpha"))
    _, b = _upload(server, _project("beta", "blocks"))
    hives = ", ".join(f'{{script: "{p}"}}' for p in (a["path"], b["path"]))
    body = {"match": "demo.yaml", "seed": 3, "projects": ["alpha", "beta"],
            "overrides": ["duration_s=20", "profile=small", "world.n_hives=2", f"hives=[{hives}]"]}
    code, info = server.json("POST", "/api/matches", body)
    assert code == 200, info
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        _, info = server.json("GET", f"/api/matches/{info['id']}")
        if info["state"] == "running" and info["time"] > 2:
            break
        time.sleep(0.2)
    assert info["state"] == "running" and info["time"] > 2, info.get("error") or info
    assert set(info["score"]["teams"]) == {"0", "1"}
    server.json("POST", f"/api/matches/{info['id']}/stop")

    bad = _project("broken", code="def step(self, s)\n    pass\n")
    _upload(server, bad)
    code, err = server.json("POST", "/api/matches", {**body, "projects": ["broken"]})
    assert code == 400 and err["detail"]["project"] == "broken" and err["detail"]["line"] == 1


# ------------------------------------------------------------------ серии


def _wait_series(server: Server, sid: str, states: tuple[str, ...], timeout: float = 120.0,
                 done: int | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    info: dict[str, Any] = {}
    while time.monotonic() < deadline:
        _, info = server.json("GET", f"/api/series/{sid}")
        if info["state"] in states and (done is None or info["done"] >= done):
            return info
        time.sleep(0.5)
    raise AssertionError(f"серия {sid}: ждали {states}, а она {info.get('state')}")


def test_series_over_http_runs_lists_and_serves_replays(server):
    """Критерий M7c: серия на сервере; прошлые серии не удаляются и видны в `GET /api/series`."""
    body = {"match": "m2_economy.yaml", "n": 2, "start_seed": 7, "jobs": 1,
            "overrides": ["duration_s=4", *NO_BUDGET], "scripts": ["example_basic.py"]}
    code, first = server.json("POST", "/api/series", body)
    assert code == 200, first
    info = _wait_series(server, first["id"], ("finished",))
    assert [m["seed"] for m in info["matches"]] == [7, 8] and info["done"] == 2
    assert info["hives"][0]["sha256"] and info["summary"]["played"] == 2

    status, _, data = server.get(f"/api/series/{first['id']}/replays/8")
    assert status == 200 and data[:4] == b"SWR1"
    tmp = Path(server.cfg.series / first["id"] / "s8.swr")
    assert read_replay(tmp).hash == info["matches"][1]["hash"]
    assert server.get(f"/api/series/{first['id']}/replays/99")[0] == 404
    assert server.get("/api/series/..%5Cx")[0] in (400, 404)

    code, second = server.json("POST", "/api/series", {**body, "start_seed": 100})
    assert code == 200, second
    _wait_series(server, second["id"], ("finished",))
    _, listed = server.json("GET", "/api/series")
    ids = [s["id"] for s in listed]
    assert first["id"] in ids and second["id"] in ids  # старая серия на месте
    row = next(s for s in listed if s["id"] == first["id"])
    assert row["n"] == 2 and row["start_seed"] == 7 and row["wins"] == 2 and row["done"] == 2

    code, _err = server.json("POST", "/api/series", {**body, "n": 1})
    assert code == 400


def test_series_stop_over_http_keeps_finished(server):
    body = {"match": "m2_economy.yaml", "n": 4, "start_seed": 1, "jobs": 1,
            "overrides": ["duration_s=5", *NO_BUDGET]}
    code, s = server.json("POST", "/api/series", body)
    assert code == 200, s
    code, _busy = server.json("POST", "/api/series", body)
    assert code == 409  # одна серия за раз
    _wait_series(server, s["id"], ("running",), done=1)
    server.json("POST", f"/api/series/{s['id']}/stop")
    info = _wait_series(server, s["id"], ("stopped",))
    assert 1 <= info["done"] < 4
    swr = sorted(p.name for p in (server.cfg.series / s["id"]).glob("*.swr"))
    assert swr == [m["replay"] for m in info["matches"]]
