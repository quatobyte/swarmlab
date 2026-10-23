"""Редактор M5 на сервере: скрипты, проверка синтаксиса, логи ульев, перезапуск с новым кодом."""

from __future__ import annotations

import json

from tests.server.conftest import ROOT, recv_until
from websockets.sync.client import connect

from swarmlab.server.scripts import check_syntax

#: Пчёлы сидят в улье: ни одной команды, вылетать некому.
SCRIPT_STAY = '''
from swarmlab.bees.api import Forager, Guard, Scout

_said = False


def hive_step(hive):
    global _said
    if not _said:
        print("ВЕРСИЯ A: все сидят в улье")
        _said = True


class MyScout(Scout):
    def step(self, s):
        pass


class MyForager(Forager):
    def step(self, s):
        pass


class MyGuard(Guard):
    def step(self, s):
        pass
'''

#: Те же классы, но все вылетают и летят на восток от улья.
SCRIPT_FLY = SCRIPT_STAY.replace("ВЕРСИЯ A: все сидят в улье", "ВЕРСИЯ B: все летят").replace(
    "        pass\n",
    "        if s.me.in_hive:\n"
    "            self.leave_hive()\n"
    "        else:\n"
    "            self.fly_to(s.home.pos.x + 30, s.home.pos.y)\n",
)

#: Бесконечный цикл в step() сборщика.
SCRIPT_HANG = '''
from swarmlab.bees.api import Forager


class MyForager(Forager):
    def step(self, s):
        while True:
            pass
'''


def _ws(server, mid):
    return connect(f"{server.ws}/ws/matches/{mid}", max_size=None, open_timeout=10)


def _start_with_script(server, name, *, duration, extra=(), match="m2_economy.yaml", speed=8.0):
    """Матч из редактора: как его собирает панель «Матч» (скрипт улья — оверрайдом)."""
    path = (server.cfg.scripts / name).as_posix()
    body = {"match": match, "speed": speed, "scripts": [name],
            "overrides": [f"duration_s={duration}", f'hives=[{{script: "{path}"}}]', *extra]}
    return server.json("POST", "/api/matches", body)


def _run_and_collect(server, mid, timeout=90):
    """Все пакеты матча до footer."""
    packets: list[dict] = []
    with _ws(server, mid) as ws:
        recv_until(ws, lambda m: m["t"] == "footer", timeout=timeout, into=packets)
    return packets


def _log_lines(packets):
    return [line for p in packets if p["t"] == "log" for line in p["lines"]]


# ---------------------------------------------------------------------- файлы


def test_scripts_list_read_write(server):
    code, items = server.json("GET", "/api/scripts")
    assert code == 200
    by_name = {s["name"]: s for s in items}
    assert by_name["template.py"]["readonly"] and by_name["example_basic.py"]["readonly"]
    code, tpl = server.json("GET", "/api/scripts/template.py")
    assert code == 200 and "class MyForager" in tpl["text"]

    code, res = server.json("PUT", "/api/scripts/my_bees.py", {"text": tpl["text"]})
    assert code == 200 and res["ok"] and res["errors"] == []
    assert (server.cfg.scripts / "my_bees.py").read_text(encoding="utf-8") == tpl["text"]
    code, items = server.json("GET", "/api/scripts")
    mine = next(s for s in items if s["name"] == "my_bees.py")
    assert not mine["readonly"] and items.index(mine) < items.index(by_name["template.py"])


def test_write_only_inside_scripts_folder(server, tmp_path):
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    root_before = {p.name for p in ROOT.iterdir()}
    bad = ["..%2Fevil.py", "..%5Cevil.py", "evil.txt", "evil", "con.py", "Nul.py", "lpt1.py",
           "1bad.py", "%D0%BC%D0%BE%D0%B9.py", "a.b.py", "x" * 70 + ".py", "%2E%2E.py"]
    for name in bad:
        code, _ = server.json("PUT", f"/api/scripts/{name}", {"text": "x = 1\n"})
        assert code in (400, 404, 405), (name, code)
    for name in ("a/b.py", "../evil.py"):
        code, _ = server.json("PUT", f"/api/scripts/{name}", {"text": "x = 1\n"})
        assert code in (400, 404, 405), (name, code)
    # Справочные скрипты не перезаписываются.
    for name in ("template.py", "example_basic.py", "example_smart.py"):
        code, err = server.json("PUT", f"/api/scripts/{name}", {"text": "x = 1\n"})
        assert code == 403 and "Сохраните под своим именем" in err["detail"]
    code, _ = server.json("PUT", "/api/scripts/huge.py", {"text": "#" * (300 * 1024)})
    assert code == 413
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    assert after == before, after - before
    assert {p.name for p in ROOT.iterdir()} == root_before
    assert server.json("GET", "/api/scripts/nope.py")[0] == 404
    assert server.json("GET", "/api/scripts/..%2Fpyproject.toml")[0] in (400, 404)


# ---------------------------------------------------------------------- синтаксис


def test_check_syntax_reports_line_and_column():
    assert check_syntax("x = 1\n") == []
    (p,) = check_syntax("x = 1\ndef f(:\n    pass\n")
    assert p.line == 2 and p.col >= 1 and "Синтаксическая ошибка" in p.message
    (p,) = check_syntax("def f():\nreturn 1\n")
    assert p.line == 2 and "Ошибка отступа" in p.message
    (p,) = check_syntax("x = 'a\0'")
    assert p.line == 1


def test_syntax_error_shown_with_line_server_alive(server):
    text = SCRIPT_STAY.replace("class MyGuard(Guard):", "class MyGuard(Guard)")
    line = text.splitlines().index("class MyGuard(Guard)") + 1
    code, res = server.json("POST", "/api/scripts/check", {"text": text})
    assert code == 200 and not res["ok"] and res["errors"][0]["line"] == line

    # Сохранение не теряет правку, но сообщает об ошибке.
    code, res = server.json("PUT", "/api/scripts/broken.py", {"text": text})
    assert code == 200 and not res["ok"] and res["errors"][0]["line"] == line
    assert (server.cfg.scripts / "broken.py").read_text(encoding="utf-8") == text

    # Запуск матча с ним — 400 со строкой; процесс матча не запускается.
    code, err = _start_with_script(server, "broken.py", duration=5)
    assert code == 400
    detail = err["detail"]
    assert detail["script"] == "broken.py" and detail["line"] == line
    assert detail["message"].startswith(f"broken.py, строка {line}:")
    assert server.json("GET", "/api/matches") == (200, [])
    # Сервер жив и запускает исправленный скрипт.
    assert server.get("/api/configs")[0] == 200
    server.json("PUT", "/api/scripts/broken.py", {"text": SCRIPT_STAY})
    code, info = _start_with_script(server, "broken.py", duration=2)
    assert code == 200, info
    server.wait_state(info["id"], ("finished",), timeout=60)


# ---------------------------------------------------------------------- критерии M5


def _airborne_after(packets, t_min):
    frames = [p for p in packets if p["t"] == "frame" and p["time"] >= t_min]
    assert frames, "нет кадров"
    return max(len(f["arrays"]["bee_uid"]) for f in frames)


def test_blocks_over_http_error_points_to_block(server):
    """M7b: файл блоков через PUT/GET; ошибка ast — с id блока и в проверке, и при запуске."""
    blocks = {"format": 1, "mode": "blocks", "workspace": {"blocks": {"blocks": []}}}
    text = "def hive_step(hive):  # block:prog\n    print(hive.time  # block:bad_line\n"
    code, res = server.json("PUT", "/api/scripts/my_blocks.py", {"text": text, "blocks": blocks})
    assert code == 200 and not res["ok"] and res["mode"] == "blocks"
    assert res["errors"][0]["block"] == "bad_line"
    code, data = server.json("GET", "/api/scripts/my_blocks.py")
    assert code == 200 and data["blocks"] == blocks
    code, res = server.json("POST", "/api/scripts/check", {"text": text})
    assert res["errors"][0]["block"] == "bad_line" and res["errors"][0]["line"] == 2
    code, err = _start_with_script(server, "my_blocks.py", duration=2)
    assert code == 400 and err["detail"]["block"] == "bad_line"
    # Переход в Python: дальше блоки этот файл не пишут.
    to_python = {**blocks, "mode": "python"}
    server.json("PUT", "/api/scripts/my_blocks.py", {"text": text, "blocks": to_python})
    code, err = server.json("PUT", "/api/scripts/my_blocks.py", {"text": text, "blocks": blocks})
    assert code == 409
    code, items = server.json("GET", "/api/scripts")
    by_name = {s["name"]: s for s in items}
    assert by_name["my_blocks.py"]["mode"] == "python"
    assert by_name["example_blocks.py"]["mode"] == "blocks"


def test_edit_restart_changes_behaviour(server):
    """Правка кода → перезапуск → поведение пчёл меняется (критерий M5)."""
    server.json("PUT", "/api/scripts/my_bees.py", {"text": SCRIPT_STAY})
    code, a = _start_with_script(server, "my_bees.py", duration=6)
    assert code == 200, a
    pa = _run_and_collect(server, a["id"])
    logs_a = _log_lines(pa)
    assert any("ВЕРСИЯ A" in line for line in logs_a), logs_a
    airborne_a = _airborne_after(pa, 3.0)

    # Правка в «редакторе» и перезапуск того же файла.
    code, res = server.json("PUT", "/api/scripts/my_bees.py", {"text": SCRIPT_FLY})
    assert code == 200 and res["ok"]
    code, b = _start_with_script(server, "my_bees.py", duration=6)
    assert code == 200, b
    pb = _run_and_collect(server, b["id"])
    logs_b = _log_lines(pb)
    assert any("ВЕРСИЯ B" in line for line in logs_b) and not any("ВЕРСИЯ A" in x for x in logs_b)
    airborne_b = _airborne_after(pb, 3.0)
    print(f"в воздухе после 3 с: версия A — {airborne_a}, версия B — {airborne_b}")
    assert airborne_a == 0
    assert airborne_b >= 5


def test_infinite_loop_match_goes_on_with_budget_warning(server):
    """`while True` в step(): матч доходит до конца, в логе улья — предупреждение о бюджете."""
    server.json("PUT", "/api/scripts/hang.py", {"text": SCRIPT_HANG})
    code, info = _start_with_script(
        server, "hang.py", duration=4,
        extra=["runner.hard_timeout_ms=100"])
    assert code == 200, info
    packets = _run_and_collect(server, info["id"], timeout=120)
    final = server.wait_state(info["id"], ("finished",), timeout=30)
    assert final["time"] >= 4.0 - 1e-6
    frames = [p for p in packets if p["t"] == "frame"]
    assert frames[-1]["time"] > 3.0
    logs = _log_lines(packets)
    budget = [x for x in logs if "бюджет" in x]
    assert budget and "бесконечный цикл" in budget[0], logs[:20]
    assert any("перезапускается" in x for x in logs)
    # Логи — пакеты `log` с номером улья и временем матча.
    pkt = next(p for p in packets if p["t"] == "log")
    assert pkt["team"] == 0 and pkt["name"] == "hive0" and isinstance(pkt["time"], float)


def test_hornets_toggle_off_removes_hornets(server):
    """Переключатель «шершни» выключен → шершней нет (тело запроса — как у панели «Матч»)."""
    path = (server.cfg.scripts / "example_basic.py").as_posix()

    def run(hornets: bool) -> tuple[dict, list[dict]]:
        body = {"match": "demo.yaml", "speed": 8.0, "seed": 3, "scripts": ["example_basic.py"],
                "overrides": [
                    "profile=small", "duration_s=12", f'hives=[{{script: "{path}"}}]',
                    f"enemies.hornets.enabled={str(hornets).lower()}",
                    "enemies.spiders.enabled=true", "weather.enabled=true",
                    # Шершни прилетают сразу и часто, чтобы включённые точно появились.
                    "enemies.hornets.first_wave_s=1", "enemies.hornets.wave_interval_s=3",
                ]}
        code, info = server.json("POST", "/api/matches", body)
        assert code == 200, info
        packets = _run_and_collect(server, info["id"], timeout=120)
        header = next(p for p in packets if p["t"] == "header")
        frames = [p for p in packets if p["t"] == "frame"]
        assert frames[-1]["time"] >= 11.0
        return header, frames

    def hornets_seen(frames: list[dict]) -> int:
        return max(len(f["arrays"]["hornet_uid"]) for f in frames)

    header_on, frames_on = run(True)
    assert header_on["config"]["params"]["enemies"]["hornets"]["enabled"] is True
    assert hornets_seen(frames_on) > 0
    header_off, frames_off = run(False)
    assert header_off["config"]["params"]["enemies"]["hornets"]["enabled"] is False
    assert hornets_seen(frames_off) == 0
    assert not any(str(e.get("type", "")).startswith("hornet")
                   for f in frames_off for e in f["events"])


def test_late_viewer_gets_log_history(server):
    server.json("PUT", "/api/scripts/my_bees.py", {"text": SCRIPT_STAY})
    code, info = _start_with_script(server, "my_bees.py", duration=3, speed=4.0)
    assert code == 200
    server.wait_state(info["id"], ("finished",), timeout=60)
    packets = _run_and_collect(server, info["id"])
    assert packets[0]["t"] == "header"
    assert any("ВЕРСИЯ A" in x for x in _log_lines(packets))


def test_profiles_and_help(server):
    code, profiles = server.json("GET", "/api/profiles")
    assert code == 200
    by = {p["name"]: p for p in profiles}
    assert by["small"]["config"]["bees"]["world"]["n_hives"] == 1
    assert by["medium"]["config"]["bees"]["world"]["n_hives"] == 3
    code, doc = server.json("GET", "/api/help")
    assert code == 200 and "fly_to" in doc["text"]
    json.dumps(profiles)
