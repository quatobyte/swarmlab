"""Портал для тестов (M9a): настоящий uvicorn в потоке, `create_app` во временной папке, без модуля.

У каждого пользователя свой клиент с cookie (`http.cookiejar`) и CSRF-токеном из `/api/me`.
"""

from __future__ import annotations

import http.cookiejar
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from swarmlab.core.config import deep_merge
from swarmlab.server.accounts import PublicSettings, load_settings
from swarmlab.server.app import ServerConfig, create_app

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "correct horse 1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Client:
    """Браузер одного пользователя: cookie сессии и CSRF-токен."""

    base: str
    jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)
    csrf: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def raw(self, method: str, path: str, data: bytes | None = None,
            headers: dict[str, str] | None = None, csrf: bool = True,
            ) -> tuple[int, dict[str, str], bytes]:
        h = {**self.headers, **(headers or {})}
        if csrf and self.csrf and method not in ("GET", "HEAD"):
            h.setdefault("X-CSRF-Token", self.csrf)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def json(self, method: str, path: str, body: Any = None, **kw: Any) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        code, _, raw = self.raw(method, path, data, headers, **kw)
        try:
            return code, json.loads(raw or b"null")
        except ValueError:
            return code, raw

    def register(self, email: str, password: str = PASSWORD) -> tuple[int, Any]:
        code, data = self.json("POST", "/api/auth/register", {"email": email,
                                                              "password": password})
        if code == 200:
            self.csrf = data["csrf"]
        return code, data

    def login(self, email: str, password: str = PASSWORD) -> tuple[int, Any]:
        code, data = self.json("POST", "/api/auth/login", {"email": email, "password": password})
        if code == 200:
            self.csrf = data["csrf"]
        return code, data

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)


@dataclass
class Portal:
    base: str
    ws: str
    cfg: ServerConfig
    app: Any
    uv: uvicorn.Server

    @property
    def portal(self) -> Any:
        return self.app.state.portal

    def client(self, **headers: str) -> Client:
        return Client(self.base, headers=headers)

    def user(self, email: str) -> Client:
        c = self.client()
        code, data = c.register(email)
        assert code == 200, data
        return c


def _settings(**over: Any) -> PublicSettings:
    base = load_settings().model_dump()
    return PublicSettings(**deep_merge(base, over))


def shared_examples(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.py").write_text("def loop(self):\n    pass\n", encoding="utf-8")
    (folder / "example_a.py").write_text("def loop(self):\n    self.wait(1)\n", encoding="utf-8")
    (folder / "my_local.py").write_text("# локальный скрипт, на портале не виден\n",
                                        encoding="utf-8")
    return folder


@pytest.fixture
def make_portal(tmp_path: Path) -> Iterator[Callable[..., Portal]]:
    servers: list[tuple[uvicorn.Server, threading.Thread]] = []

    def make(public: bool = True, **settings: Any) -> Portal:
        n = len(servers)
        root = tmp_path / f"root{n}"
        root.mkdir()
        cfg = ServerConfig(root=root, configs=root / "configs", replays=root / "replays",
                           logs=root / "logs", web=ROOT / "web",
                           scripts=shared_examples(root / "examples"),
                           projects=root / "projects",
                           public=_settings(**settings) if public else None,
                           data=root / "data")
        app = create_app(cfg)
        port = _free_port()
        uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           ws="websockets-sansio", proxy_headers=False))
        thread = threading.Thread(target=uv.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not uv.started:
            assert time.monotonic() < deadline, "uvicorn не запустился"
            time.sleep(0.05)
        servers.append((uv, thread))
        return Portal(base=f"http://127.0.0.1:{port}", ws=f"ws://127.0.0.1:{port}", cfg=cfg,
                      app=app, uv=uv)

    yield make
    for uv, thread in servers:
        uv.should_exit = True
        thread.join(30)


@pytest.fixture
def portal(make_portal: Callable[..., Portal]) -> Portal:
    return make_portal()
