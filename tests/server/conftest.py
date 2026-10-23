"""Сервер для тестов: настоящий uvicorn в потоке на свободном порту.

Реплеи и логи — во временной папке.
"""

from __future__ import annotations

import json
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from swarmlab.core.replay import unpack
from swarmlab.server.app import ServerConfig, create_app

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Server:
    base: str
    ws: str
    cfg: ServerConfig
    app: Any
    uv: uvicorn.Server

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def json(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def start(self, match: str = "m2_economy.yaml", duration: float = 8.0, **extra: Any) -> str:
        overrides = [f"duration_s={duration}", *extra.pop("overrides", [])]
        body = {"match": match, "overrides": overrides, **extra}
        code, info = self.json("POST", "/api/matches", body)
        assert code == 200, info
        return info["id"]

    def wait_state(self, mid: str, states: tuple[str, ...],
                   timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        info: dict[str, Any] = {}
        while time.monotonic() < deadline:
            _, info = self.json("GET", f"/api/matches/{mid}")
            if info["state"] in states:
                return info
            time.sleep(0.1)
        raise AssertionError(f"матч {mid}: ждали {states}, а он {info.get('state')}")


def recv_until(ws: Any, pred: Callable[[dict[str, Any]], bool], timeout: float = 30.0,
               into: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Читать пакеты WS, пока `pred(пакет)`; все прочитанные — в `into`."""
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AssertionError("не дождались нужного пакета WS")
        msg = unpack(ws.recv(timeout=left))
        if into is not None:
            into.append(msg)
        if pred(msg):
            return msg


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    # Скрипты редактора — копия examples/bees во временной папке: тесты пишут туда.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for pattern in ("*.py", "*.blocks.json"):
        for src in (ROOT / "examples" / "bees").glob(pattern):
            shutil.copy2(src, scripts / src.name)
    cfg = ServerConfig(root=ROOT, configs=ROOT / "configs", replays=tmp_path / "replays",
                       logs=tmp_path / "logs", web=ROOT / "web", scripts=scripts,
                       projects=tmp_path / "projects")
    app = create_app(cfg)
    port = _free_port()
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                       ws="websockets-sansio"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not uv.started:
        assert time.monotonic() < deadline, "uvicorn не запустился"
        time.sleep(0.05)
    srv = Server(base=f"http://127.0.0.1:{port}", ws=f"ws://127.0.0.1:{port}", cfg=cfg, app=app,
                 uv=uv)
    try:
        yield srv
    finally:
        uv.should_exit = True
        thread.join(30)
