"""Сервер M4: статика, REST, WS-стрим живого матча, пауза и скорость, реплей, живучесть."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import numpy as np
import pytest
from tests.server.conftest import ROOT, recv_until
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from swarmlab.core.protocol import encode
from swarmlab.core.replay import read_replay


def _ws(server, mid):
    return connect(f"{server.ws}/ws/matches/{mid}", max_size=None, open_timeout=10)


def test_index_static_and_configs(server):
    code, headers, body = server.get("/")
    assert code == 200
    assert b'<script type="importmap">' in body
    assert headers["cache-control"] == "no-cache"
    code, headers, _ = server.get("/js/core/app.js")
    assert code == 200 and headers["content-type"].startswith("text/javascript")
    code, _, _ = server.get("/vendor/three/three.module.js")
    assert code == 200
    code, configs = server.json("GET", "/api/configs")
    assert code == 200
    assert configs[0]["name"] == "demo.yaml"
    assert configs[0]["profile"] == "medium" and configs[0]["description"]


def test_live_match_stream_pause_speed_and_replay(server):
    mid = server.start("m2_economy.yaml", duration=8.0, speed=2.0)
    packets: list[dict] = []
    with _ws(server, mid) as ws:
        header = recv_until(ws, lambda m: m["t"] == "header", into=packets)
        scene = header["scene"]
        assert header["match_id"] == mid and header["frame_hz"] == 10
        assert isinstance(scene["world"]["terrain"], np.ndarray)
        assert scene["world"]["terrain"].shape == (128, 128)
        assert header["runners"] and all(r["ok"] for r in header["runners"])
        frames = [recv_until(ws, lambda m: m["t"] == "frame", into=packets) for _ in range(5)]
        times = [f["time"] for f in frames]
        assert times == sorted(times) and times[-1] > times[0]
        assert frames[-1]["arrays"]["bee_pos"].dtype == np.uint16

        # Пауза: время симуляции стоит.
        ws.send('{"t": "pause"}')
        st = recv_until(ws, lambda m: m["t"] == "status" and m["state"] == "paused")
        t_paused = st["time"]
        time.sleep(1.0)
        _, info = server.json("GET", f"/api/matches/{mid}")
        assert info["state"] == "paused" and info["time"] == pytest.approx(t_paused)

        # Продолжить и ускорить.
        ws.send('{"t": "resume"}')
        recv_until(ws, lambda m: m["t"] == "status" and m["state"] == "running")
        ws.send('{"t": "speed", "value": 4}')
        st = recv_until(ws, lambda m: m["t"] == "status" and m["speed"] == 4.0)
        footer = recv_until(ws, lambda m: m["t"] == "footer", timeout=60, into=packets)

    assert footer["replay"] == f"{mid}.swr"
    info = server.wait_state(mid, ("finished",))
    assert info["time"] == pytest.approx(8.0)
    path = server.cfg.replays / f"{mid}.swr"
    rp = read_replay(path)
    assert rp.complete and rp.hash_ok
    assert footer["hash"] == rp.hash
    # Кадры стрима — байт в байт кадры реплея (в т. ч. начальный кадр t = 0).
    streamed = [p for p in packets if p["t"] == "frame"]
    by_tick = {f.tick: f for f in rp.frames}
    for f in streamed:
        np.testing.assert_array_equal(f["arrays"]["bee_pos"], by_tick[f["tick"]].arrays["bee_pos"])
    code, _, body = server.get(f"/api/replays/{mid}")
    assert code == 200 and body == path.read_bytes()
    code, replays = server.json("GET", "/api/replays")
    assert [r["id"] for r in replays] == [mid]


def test_tab_closed_server_survives_new_match_replaces_old(server):
    first = server.start("m2_economy.yaml", duration=120.0)
    with _ws(server, first) as ws:
        recv_until(ws, lambda m: m["t"] == "frame")
        ws.socket.close()  # вкладку закрыли без прощания
    time.sleep(0.5)
    _, info = server.json("GET", f"/api/matches/{first}")
    assert info["state"] in ("running", "starting")  # матч идёт без зрителей

    # Зритель вернулся: получает заголовок и свежий кадр сразу.
    with _ws(server, first) as ws2:
        recv_until(ws2, lambda m: m["t"] == "header", timeout=5)
        recv_until(ws2, lambda m: m["t"] == "frame", timeout=5)

    # Новый матч без перезапуска сервера вытесняет старый; реплей старого дописан.
    second = server.start("m2_economy.yaml", duration=120.0, seed=7)
    assert second != first
    server.wait_state(first, ("stopped",))
    old = read_replay(server.cfg.replays / f"{first}.swr")
    assert old.complete and old.hash_ok
    with _ws(server, second) as ws3:
        header = recv_until(ws3, lambda m: m["t"] == "header")
        assert header["seed"] == 7
        recv_until(ws3, lambda m: m["t"] == "frame")
        ws3.send('{"t": "stop"}')
        recv_until(ws3, lambda m: m["t"] == "footer")
    assert server.wait_state(second, ("stopped",))["replay"] == second
    code, matches = server.json("GET", "/api/matches")
    assert code == 200 and {m["id"] for m in matches} == {first, second}


def test_bad_requests(server):
    assert server.json("POST", "/api/matches", {"match": "nope.yaml"})[0] == 404
    assert server.json("POST", "/api/matches", {"match": "../demo.yaml"})[0] == 400
    code, err = server.json("POST", "/api/matches",
                            {"match": "demo.yaml", "overrides": ["duration_s=-5"]})
    assert code == 400 and "Ошибка конфига" in err["detail"]
    assert server.json("GET", "/api/matches/nope")[0] == 404
    assert server.get("/api/replays/..%2F..%2Fpyproject")[0] in (400, 404)
    assert server.get("/api/replays/missing")[0] == 404
    with _ws(server, "nope") as ws, pytest.raises(ConnectionClosed) as e:
        ws.recv(timeout=5)
    assert e.value.rcvd.code == 4404
    assert server.json("GET", "/api/matches") == (200, [])


def test_match_error_reported_server_alive(server):
    # Конфиг проходит слияние, но модуль его отвергает уже в процессе матча.
    mid = server.start("m2_economy.yaml", overrides=["world.n_hives=7"])
    with _ws(server, mid) as ws:
        st = recv_until(ws, lambda m: m["t"] == "status" and m["state"] == "error")
    assert "n_hives" in st["error"]
    assert server.wait_state(mid, ("error",))["error"]
    assert server.get("/api/configs")[0] == 200


def test_server_shutdown_stops_match_process(server):
    mid = server.start("m2_economy.yaml", duration=120.0)
    with _ws(server, mid) as ws:
        recv_until(ws, lambda m: m["t"] == "frame")
    proc = server.app.state.manager.matches[mid].proc
    assert proc.poll() is None
    server.uv.should_exit = True
    proc.wait(20)  # lifespan: stop → воркер дописывает реплей и выходит
    assert read_replay(server.cfg.replays / f"{mid}.swr").complete


def test_worker_exits_when_server_disappears(tmp_path):
    """EOF на stdin (сервер умер) → воркер останавливает матч и выходит — сирот нет."""
    proc = subprocess.Popen([sys.executable, "-m", "swarmlab.server.worker"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, cwd=ROOT)
    assert proc.stdin is not None and proc.stdout is not None
    match = str(ROOT / "configs/matches/m0.yaml")
    proc.stdin.write(encode({"t": "start", "id": "eof", "match": match,
                             "overrides": ["duration_s=60"],
                             "replay": str(tmp_path / "eof.swr")}))
    proc.stdin.flush()
    proc.stdout.read(4)  # первый пакет: статус «starting»
    # Сервер «умер»: stdin закрыт, но stdout кто-то дочитывает (иначе воркер встанет на записи).
    threading.Thread(target=proc.stdout.read, daemon=True).start()
    proc.stdin.close()
    assert proc.wait(20) == 0
    assert read_replay(tmp_path / "eof.swr").complete
