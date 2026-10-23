"""FastAPI-сервер: матчи в отдельных процессах, WS-стрим кадров, реплеи, статика `web/`.

ARCHITECTURE §7, DECISIONS №43. Сервер не знает модулей: он запускает воркер
(`swarmlab.server.worker`) и пересылает его пакеты зрителям как есть.

REST:
    GET  /api/configs              матчи из `configs/matches/*.yaml`
    GET  /api/matches              живые и недавние матчи
    POST /api/matches              {match, seed?, overrides?, speed?} → {id}
    GET  /api/matches/{id}         состояние, время, счёт
    POST /api/matches/{id}/stop    остановить (реплей дописывается)
    GET  /api/replays              реплеи `.swr` в папке реплеев
    GET  /api/replays/{id}         файл реплея (распаковывает вьюер)
    GET  /api/profiles             профили `configs/profiles/*.yaml` (имя, описание, YAML)
    GET  /api/scripts              скрипты игроков в папке редактора (`examples/bees/`)
    GET  /api/scripts/{name}       текст скрипта и файл блоков (`blocks`, если есть)
    PUT  /api/scripts/{name}       {text, blocks?} → сохранить; {ok, errors[{line, col, …, block}]}
    POST /api/scripts/check        {text} → синтаксические ошибки (`ast.parse`)
    GET  /api/help                 памятка игрока `docs/CHEATSHEET.md` (текст Markdown)
WS:
    /ws/matches/{id}               сервер → бинарный msgpack: header, frame, status, log, footer;
                                   клиент → JSON: pause, resume, speed {value}, stop
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import mimetypes
import os
import re
import struct
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import msgpack
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from swarmlab.core.config import ConfigError, load_match, load_yaml
from swarmlab.core.protocol import encode
from swarmlab.server.scripts import ScriptError, ScriptStore, check_syntax

log = logging.getLogger("swarmlab.server")

# На Windows тип `.js` берётся из реестра и бывает `text/plain` — браузер тогда
# не загрузит ES-модуль. Задаём явно.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

_LEN = struct.Struct("<I")
_NAME = re.compile(r"^[\w.\-]+$")
#: Сколько кадров копится в очереди медленного зрителя, прежде чем старые выкидываются.
_SUB_MAX_FRAMES = 30
#: Сколько завершённых матчей помнит сервер.
_KEEP_FINISHED = 20
#: На остановку воркера после `stop`, с; потом `kill`.
_STOP_TIMEOUT_S = 8.0
_TERMINAL = ("finished", "stopped", "error")
#: Сколько пакетов `log` помнит матч (их получает зритель, подключившийся позже).
_KEEP_LOG_PACKETS = 1000


@dataclass
class ServerConfig:
    """Пути и ограничения сервера (`swarmlab serve`)."""

    root: Path
    configs: Path
    replays: Path
    logs: Path
    web: Path
    max_matches: int = 1
    #: Папка скриптов редактора (M5); по умолчанию `<root>/examples/bees`.
    scripts: Path | None = None


def default_config(root: Path | None = None) -> ServerConfig:
    root = Path(root or Path.cwd()).resolve()
    web = root / "web"
    if not web.is_dir():  # запуск не из корня проекта — web/ рядом с пакетом
        web = Path(__file__).resolve().parents[3] / "web"
    return ServerConfig(root=root, configs=root / "configs", replays=root / "replays",
                        logs=root / "logs", web=web, scripts=root / "examples" / "bees")


# ====================================================================== зрители


class Subscriber:
    """Очередь пакетов одного зрителя: кадры можно выкинуть, остальное — нет."""

    def __init__(self) -> None:
        self.items: collections.deque[tuple[str, bytes]] = collections.deque()
        self.event = asyncio.Event()
        self.frames = 0
        self.closed = False

    def push(self, kind: str, data: bytes) -> None:
        if kind == "frame":
            if self.frames >= _SUB_MAX_FRAMES:
                for i, (k, _) in enumerate(self.items):
                    if k == "frame":
                        del self.items[i]
                        self.frames -= 1
                        break
            self.frames += 1
        self.items.append((kind, data))
        self.event.set()

    def close(self) -> None:
        self.closed = True
        self.event.set()

    def drain(self) -> list[bytes]:
        out = [d for _, d in self.items]
        self.items.clear()
        self.frames = 0
        self.event.clear()
        return out


# ====================================================================== матч


@dataclass
class MatchProcess:
    """Живой матч: процесс-воркер, последние пакеты, зрители."""

    id: str
    match: str
    seed: int | None
    created: str
    replay: Path
    loop: asyncio.AbstractEventLoop
    state: str = "starting"
    time: float = 0.0
    duration_s: float | None = None
    speed: float = 1.0
    rtf: float = 0.0
    score: dict[str, Any] | None = None
    error: str | None = None
    header: bytes | None = None
    status_pkt: bytes | None = None
    last_frame: bytes | None = None
    footer: bytes | None = None
    log_packets: collections.deque[bytes] = field(
        default_factory=lambda: collections.deque(maxlen=_KEEP_LOG_PACKETS))
    subscribers: set[Subscriber] = field(default_factory=set)
    proc: subprocess.Popen[bytes] | None = None
    stderr_tail: collections.deque[str] = field(
        default_factory=lambda: collections.deque(maxlen=60))
    _write_lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------ процесс

    def spawn(self, start: dict[str, Any], cwd: Path) -> None:
        env = dict(os.environ)
        env.update(PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "swarmlab.server.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(cwd), env=env, creationflags=flags,
        )
        self.send(start)
        threading.Thread(target=self._read_stdout, daemon=True,
                         name=f"match-{self.id}-out").start()
        threading.Thread(target=self._read_stderr, daemon=True,
                         name=f"match-{self.id}-err").start()

    def send(self, msg: dict[str, Any]) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return
        with self._write_lock:
            try:
                proc.stdin.write(encode(msg))
                proc.stdin.flush()
            except (OSError, ValueError):
                pass

    def control(self, msg: dict[str, Any]) -> None:
        """Команда зрителя → воркер (только известные типы)."""
        t = msg.get("t")
        if t in ("pause", "resume", "stop"):
            self.send({"t": t})
        elif t == "speed":
            self.send({"t": "speed", "value": msg.get("value", 1.0)})

    def stop(self) -> None:
        if self.state in _TERMINAL:
            return
        self.send({"t": "stop"})
        threading.Thread(target=self._reap, daemon=True).start()

    def _reap(self) -> None:
        proc = self.proc
        if proc is None:
            return
        try:
            proc.wait(_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            log.warning("матч %s не остановился за %.0f с — kill", self.id, _STOP_TIMEOUT_S)
            proc.kill()

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        stream = self.proc.stdout
        try:
            while True:
                head = stream.read(_LEN.size)
                if len(head) < _LEN.size:
                    break
                (n,) = _LEN.unpack(head)
                body = stream.read(n)
                if len(body) < n:
                    break
                msg = msgpack.unpackb(body, raw=False, strict_map_key=False)
                self.loop.call_soon_threadsafe(self._publish, msg, body)
        except (OSError, ValueError) as e:
            log.warning("матч %s: канал воркера оборвался: %s", self.id, e)
        self.proc.wait()
        self.loop.call_soon_threadsafe(self._on_exit, self.proc.returncode)

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in self.proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self.stderr_tail.append(line)
            log.info("[%s] %s", self.id, line)

    # ------------------------------------------------------------ пакеты (event loop)

    def _publish(self, msg: dict[str, Any], body: bytes) -> None:
        kind = str(msg.get("t"))
        if kind == "header":
            self.header = body
            self.duration_s = msg.get("duration_s")
        elif kind == "frame":
            self.last_frame = body
            self.time = float(msg.get("time", self.time))
        elif kind == "status":
            self.status_pkt = body
            self.state = str(msg.get("state", self.state))
            self.time = float(msg.get("time") or self.time)
            self.speed = float(msg.get("speed") or self.speed)
            self.rtf = float(msg.get("rtf") or 0.0)
            self.score = msg.get("score") or self.score
            self.error = msg.get("error") or self.error
            if msg.get("duration_s"):
                self.duration_s = float(msg["duration_s"])
        elif kind == "log":
            self.log_packets.append(body)
        elif kind == "footer":
            self.footer = body
            self.score = msg.get("score") or self.score
        for sub in self.subscribers:
            sub.push(kind, body)

    def _on_exit(self, code: int | None) -> None:
        if self.state not in _TERMINAL:
            tail = "\n".join(self.stderr_tail)
            self.state = "error"
            self.error = self.error or f"Процесс матча завершился (код {code}).\n{tail}"
            pkt = msgpack.packb({"t": "status", "match_id": self.id, "state": "error",
                                 "speed": self.speed, "time": self.time,
                                 "duration_s": self.duration_s, "rtf": 0.0,
                                 "score": self.score, "error": self.error}, use_bin_type=True)
            self._publish(msgpack.unpackb(pkt, raw=False), pkt)
        for sub in self.subscribers:
            sub.close()

    def subscribe(self) -> Subscriber:
        sub = Subscriber()
        if self.header is not None:
            sub.push("header", self.header)
        for pkt in self.log_packets:
            sub.push("log", pkt)
        for kind, pkt in (("status", self.status_pkt), ("frame", self.last_frame),
                          ("footer", self.footer)):
            if pkt is not None:
                sub.push(kind, pkt)
        if self.state in _TERMINAL and (self.proc is None or self.proc.poll() is not None):
            sub.close()
        self.subscribers.add(sub)
        return sub

    def info(self) -> dict[str, Any]:
        return {"id": self.id, "match": self.match, "seed": self.seed, "created": self.created,
                "state": self.state, "time": self.time, "duration_s": self.duration_s,
                "speed": self.speed, "rtf": self.rtf, "score": self.score, "error": self.error,
                "replay": self.replay.stem if self.footer is not None else None,
                "viewers": len(self.subscribers)}


class MatchManager:
    """Реестр матчей; одновременно идут не больше `max_matches` (новый вытесняет старый)."""

    def __init__(self, cfg: ServerConfig, scripts: ScriptStore) -> None:
        self.cfg = cfg
        self.scripts = scripts
        self.matches: dict[str, MatchProcess] = {}

    def running(self) -> list[MatchProcess]:
        return [m for m in self.matches.values() if m.state not in _TERMINAL]

    def match_path(self, name: str) -> Path:
        if not _NAME.match(name):
            raise HTTPException(400, f"Недопустимое имя матча: {name!r}")
        stem = name[:-5] if name.endswith(".yaml") else name
        path = self.cfg.configs / "matches" / f"{stem}.yaml"
        if not path.is_file():
            raise HTTPException(404, f"Нет матча {stem}.yaml в {self.cfg.configs / 'matches'}")
        return path

    def _new_id(self, stem: str, seed: int) -> str:
        base = f"{stem}-s{seed}-{datetime.now():%Y%m%d-%H%M%S}"
        mid, n = base, 1
        while mid in self.matches or (self.cfg.replays / f"{mid}.swr").exists():
            n += 1
            mid = f"{base}-{n}"
        return mid

    def check_scripts(self, names: list[str]) -> None:
        """Синтаксис скриптов матча — до запуска процесса; ошибка → 400 со строкой."""
        for name in dict.fromkeys(names):
            try:
                _, problems = self.scripts.check_file(name)
            except ScriptError as e:
                raise HTTPException(e.status, e.message) from e
            if problems:
                p = problems[0]
                raise HTTPException(400, {
                    **p.as_dict(), "script": name,
                    "message": f"{name}, строка {p.line}: {p.message}",
                })

    def start(self, req: StartRequest) -> MatchProcess:
        path = self.match_path(req.match)
        self.check_scripts(req.scripts)
        overrides = list(req.overrides)
        if req.seed is not None:
            overrides.append(f"seed={req.seed}")
        try:  # проверить конфиг сразу: ошибка — 400, а не упавший процесс
            cfg = load_match(path, configs_dir=self.cfg.configs, cli_overrides=overrides)
        except ConfigError as e:
            raise HTTPException(400, f"Ошибка конфига: {e}") from e
        for old in self.running()[: max(0, len(self.running()) - self.cfg.max_matches + 1)]:
            log.info("новый матч вытесняет %s", old.id)
            old.stop()
        mid = self._new_id(path.stem, cfg.seed)
        m = MatchProcess(id=mid, match=path.stem, seed=cfg.seed,
                         created=datetime.now().isoformat(timespec="seconds"),
                         replay=self.cfg.replays / f"{mid}.swr", loop=asyncio.get_running_loop(),
                         duration_s=cfg.duration_s, speed=req.speed)
        m.spawn({"t": "start", "id": mid, "match": str(path), "configs": str(self.cfg.configs),
                 "overrides": overrides, "replay": str(m.replay),
                 "log_dir": str(self.cfg.logs / mid), "speed": req.speed},
                cwd=self.cfg.root)
        self.matches[mid] = m
        self._forget_old()
        log.info("матч %s запущен (%s, seed %s)", mid, path.name, cfg.seed)
        return m

    def _forget_old(self) -> None:
        done = [m for m in self.matches.values() if m.state in _TERMINAL]
        for m in done[: max(0, len(done) - _KEEP_FINISHED)]:
            if not m.subscribers:
                del self.matches[m.id]

    def get(self, mid: str) -> MatchProcess:
        m = self.matches.get(mid)
        if m is None:
            raise HTTPException(404, f"Нет матча {mid!r}")
        return m

    def shutdown(self) -> None:
        procs = [m.proc for m in self.matches.values() if m.proc and m.proc.poll() is None]
        for m in self.matches.values():
            m.stop()
        for p in procs:
            try:
                p.wait(_STOP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                p.kill()


class StartRequest(BaseModel):
    match: str = Field(description="имя файла в configs/matches, например demo.yaml")
    seed: int | None = Field(default=None, ge=0)
    overrides: list[str] = Field(default_factory=list, description="как --set ПУТЬ=ЗНАЧЕНИЕ")
    speed: float = Field(default=1.0, ge=0.25, le=8.0)
    scripts: list[str] = Field(
        default_factory=list,
        description="скрипты из папки редактора, синтаксис которых проверить до запуска")


class ScriptText(BaseModel):
    text: str
    #: Файл блоков рядом со скриптом (M7b): `{format, mode, workspace}`.
    blocks: dict[str, Any] | None = None


def _script_call(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except ScriptError as e:
        raise HTTPException(e.status, e.message) from e


# ====================================================================== приложение


def _describe_yaml(path: Path) -> dict[str, Any]:
    desc = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            desc = line.lstrip("#").strip()
            break
    try:
        data = load_yaml(path)
    except ConfigError:
        data = {}
    return {"name": path.name, "description": desc, "seed": data.get("seed"),
            "profile": data.get("profile"), "duration_s": data.get("duration_s")}


def create_app(cfg: ServerConfig | None = None) -> FastAPI:
    cfg = cfg or default_config()
    scripts = ScriptStore(cfg.scripts or cfg.root / "examples" / "bees", cfg.root)
    manager = MatchManager(cfg, scripts)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.get_running_loop().run_in_executor(None, manager.shutdown)

    app = FastAPI(title="SwarmLab", lifespan=lifespan)
    app.state.manager = manager
    app.state.cfg = cfg

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next: Any) -> Response:
        # Статика вьюера: браузер сверяет ETag при каждой загрузке, а не держит старые
        # ES-модули по эвристике кеша (после обновления кода — сразу новая версия).
        response: Response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/api/configs")
    def configs() -> list[dict[str, Any]]:
        files = sorted((cfg.configs / "matches").glob("*.yaml"))
        out = [_describe_yaml(p) for p in files]
        out.sort(key=lambda d: (d["name"] != "demo.yaml", d["name"]))
        return out

    @app.get("/api/matches")
    def list_matches() -> list[dict[str, Any]]:
        return [m.info() for m in reversed(manager.matches.values())]

    @app.post("/api/matches")
    async def start_match(req: StartRequest) -> dict[str, Any]:
        return manager.start(req).info()

    @app.get("/api/matches/{mid}")
    def get_match(mid: str) -> dict[str, Any]:
        return manager.get(mid).info()

    @app.post("/api/matches/{mid}/stop")
    def stop_match(mid: str) -> dict[str, Any]:
        m = manager.get(mid)
        m.stop()
        return m.info()

    @app.get("/api/replays")
    def list_replays() -> list[dict[str, Any]]:
        if not cfg.replays.is_dir():
            return []
        busy = {m.replay for m in manager.running()}  # ещё пишутся — не дочитаются
        files = sorted((p for p in cfg.replays.glob("*.swr") if p not in busy),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"id": p.stem, "name": p.name, "size": p.stat().st_size,
                 "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(
                     timespec="seconds")} for p in files]

    @app.get("/api/replays/{rid}")
    def get_replay(rid: str) -> FileResponse:
        stem = rid[:-4] if rid.endswith(".swr") else rid
        if not _NAME.match(stem):
            raise HTTPException(400, "Недопустимое имя реплея")
        path = cfg.replays / f"{stem}.swr"
        if not path.is_file():
            raise HTTPException(404, f"Нет реплея {stem}.swr")
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    @app.get("/api/profiles")
    def profiles() -> list[dict[str, Any]]:
        out = []
        for p in sorted((cfg.configs / "profiles").glob("*.yaml")):
            desc = _describe_yaml(p)["description"]
            try:
                data = load_yaml(p)
            except ConfigError:
                continue
            out.append({"name": p.stem, "description": desc, "config": data})
        return out

    @app.get("/api/help")
    def help_doc() -> dict[str, Any]:
        path = cfg.root / "docs" / "CHEATSHEET.md"
        if not path.is_file():
            path = Path(__file__).resolve().parents[3] / "docs" / "CHEATSHEET.md"
        if not path.is_file():
            raise HTTPException(404, "Памятка docs/CHEATSHEET.md не найдена")
        return {"name": path.name, "text": path.read_text(encoding="utf-8")}

    @app.get("/api/scripts")
    def list_scripts() -> list[dict[str, Any]]:
        return scripts.list()

    @app.post("/api/scripts/check")
    def check_script(body: ScriptText) -> dict[str, Any]:
        problems = check_syntax(body.text)
        return {"ok": not problems, "errors": [p.as_dict() for p in problems]}

    @app.get("/api/scripts/{name}")
    def read_script(name: str) -> dict[str, Any]:
        return _script_call(scripts.read, name)

    @app.put("/api/scripts/{name}")
    def write_script(name: str, body: ScriptText) -> dict[str, Any]:
        return _script_call(scripts.write, name, body.text, body.blocks)

    @app.websocket("/ws/matches/{mid}")
    async def stream(ws: WebSocket, mid: str) -> None:
        m = manager.matches.get(mid)
        await ws.accept()
        if m is None:  # закрыть с кодом после accept: клиент увидит причину, а не HTTP 403
            await ws.close(code=4404, reason="no such match")
            return
        sub = m.subscribe()

        async def receive() -> None:
            while True:
                text = await ws.receive_text()
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    m.control(msg)

        rx = asyncio.create_task(receive())
        try:
            while True:
                for data in sub.drain():
                    await ws.send_bytes(data)
                if sub.closed and not sub.items:
                    await rx  # матч кончился: ждём, пока зритель сам закроет вкладку
                    break
                waiter = asyncio.create_task(sub.event.wait())
                done, _ = await asyncio.wait({waiter, rx}, return_when=asyncio.FIRST_COMPLETED)
                if rx in done:
                    waiter.cancel()
                    rx.result()  # WebSocketDisconnect → наружу
                    break
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            pass
        finally:
            rx.cancel()
            m.subscribers.discard(sub)

    if cfg.web.is_dir():
        app.mount("/", StaticFiles(directory=cfg.web, html=True), name="web")
    return app
