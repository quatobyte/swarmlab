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
    GET  /api/scripts              скрипты игроков в папке редактора (`examples/<модуль>/`)
    GET  /api/scripts/{name}       текст скрипта и файл блоков (`blocks`, если есть)
    PUT  /api/scripts/{name}       {text, blocks?} → сохранить; {ok, errors[{line, col, …, block}]}
    POST /api/scripts/check        {text} → синтаксические ошибки (`ast.parse`)
    GET  /api/help                 памятка игрока `docs/CHEATSHEET.md` (текст Markdown)
    GET  /api/projects             загруженные проекты `.swarm` (папка `projects/`, M7c)
    POST /api/projects             тело — файл `.swarm` → {name, mode, …, status: new | same}
    GET  /api/projects/{name}      проект: код и блоки
    POST /api/projects/{name}/to-editor   копия проекта — свой скрипт редактора
    GET  /api/series               прошлые и идущая серии (папки `replays/series/`)
    POST /api/series               {match, overrides, start_seed?, n, jobs?, scripts?, projects?}
    GET  /api/series/{id}          `series.json` + `done` (прогресс — опросом раз в 1 с)
    POST /api/series/{id}/stop     остановить: дописанные матчи остаются
    GET  /api/series/{id}/replays/{seed}  реплей матча серии
WS:
    /ws/matches/{id}               сервер → бинарный msgpack: header, frame, status, log, footer;
                                   клиент → JSON: pause, resume, speed {value}, stop

Публичный режим (`ServerConfig.public`, `swarmlab serve --public`) — `server/public.py`:
вход и профиль, свои скрипты, проекты, матчи, серии и реплеи у каждого пользователя (чужое —
404). Лимиты (M9b, DECISIONS №94, числа — `public.yaml`): матчей на пользователя и на сервер
(лишние — в очереди с номером, `state: queued`, `queue`), разрешённые профили, остановка без
зрителей, серии `n` / `jobs` / одна на сервер; раннеры — с префиксом-песочницей (№93).
Без него всё работает как выше.
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
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import msgpack
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from swarmlab.core import series as sr
from swarmlab.core.config import ConfigError, load_match, load_yaml
from swarmlab.core.module import default_module
from swarmlab.core.protocol import encode
from swarmlab.server.accounts import MatchLimits, PublicSettings, SeriesLimits
from swarmlab.server.projects import ProjectStore
from swarmlab.server.public import Portal, PortalGuard, add_routes, current_user
from swarmlab.server.scripts import ScriptError, ScriptStore, check_syntax
from swarmlab.server.storage import UserSpace

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
#: Матч ждёт места в очереди портала (процесса ещё нет).
QUEUED = "queued"
#: Сколько пакетов `log` помнит матч (их получает зритель, подключившийся позже).
_KEEP_LOG_PACKETS = 1000
#: Команда процесса живого матча после интерпретатора (тесты подменяют воркер).
WORKER_ARGS = ["-m", "swarmlab.server.worker"]
#: Ключи конфига, которые на портале нельзя менять переопределениями (бюджет, частоты, модуль).
_LOCKED_ROOTS = ("runner", "timing", "module")


@dataclass
class ServerConfig:
    """Пути и ограничения сервера (`swarmlab serve`)."""

    root: Path
    configs: Path
    replays: Path
    logs: Path
    web: Path
    max_matches: int = 1
    #: Папка скриптов редактора (M5); по умолчанию `<root>/examples/<модуль>` (`default_scripts`).
    scripts: Path | None = None
    #: Загруженные проекты `.swarm` (M7c); по умолчанию `<root>/projects`.
    projects: Path | None = None
    #: Публичный режим (портал, M9a): настройки из `public.yaml`; `None` — локальный режим.
    public: PublicSettings | None = None
    #: Данные портала: база и папки пользователей; по умолчанию `<root>/data`.
    data: Path | None = None

    @property
    def series(self) -> Path:
        """Папки серий матчей (M7c): `<replays>/series/`."""
        return self.replays / "series"


def default_scripts(root: Path) -> Path:
    """Папка скриптов редактора: `examples/<модуль>` единственного модуля ветки.

    В `master` модулей нет — `examples/` (редактор пуст, сервер работает).
    """
    try:
        return root / "examples" / default_module()
    except LookupError:
        return root / "examples"


def default_config(root: Path | None = None) -> ServerConfig:
    root = Path(root or Path.cwd()).resolve()
    web = root / "web"
    if not web.is_dir():  # запуск не из корня проекта — web/ рядом с пакетом
        web = Path(__file__).resolve().parents[3] / "web"
    return ServerConfig(root=root, configs=root / "configs", replays=root / "replays",
                        logs=root / "logs", web=web, scripts=default_scripts(root),
                        projects=root / "projects")


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
    #: Владелец (id пользователя портала); локальный режим — `None`.
    owner: int | None = None
    #: Вызывается в event loop, когда процесс матча вышел (реплей дописан и закрыт).
    on_exit: Callable[[MatchProcess], None] | None = None
    #: Портал: снять матч из очереди (`stop` до запуска процесса).
    on_cancel: Callable[[MatchProcess], None] | None = None
    state: str = "starting"
    #: Номер в очереди портала (1 — следующий); `None` — не в очереди.
    queue: int | None = None
    #: Портал: с какого момента у матча нет зрителей (часы менеджера); `None` — зрители есть.
    idle_since: float | None = None
    #: Процесс матча вышел.
    exited: bool = False
    #: Матчу уже послан `stop`.
    stopping: bool = False
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
            [sys.executable, *WORKER_ARGS],
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
        if t == "stop":
            self.stop()
        elif t in ("pause", "resume"):
            self.send({"t": t})
        elif t == "speed":
            self.send({"t": "speed", "value": msg.get("value", 1.0)})

    @property
    def alive(self) -> bool:
        """Процесс матча запущен и ещё не вышел (занимает место на сервере)."""
        return self.proc is not None and not self.exited

    def stop(self) -> None:
        if self.state in _TERMINAL or self.stopping:
            return
        if self.state == QUEUED:
            if self.on_cancel is not None:
                self.on_cancel(self)
            return
        self.stopping = True
        self.send({"t": "stop"})
        threading.Thread(target=self._reap, daemon=True).start()

    def set_status(self, state: str, **extra: Any) -> None:
        """Пакет `status` от сервера (матч в очереди, снят из очереди) — зрителям и в `info`."""
        msg = {"t": "status", "match_id": self.id, "state": state, "speed": self.speed,
               "time": self.time, "duration_s": self.duration_s, "rtf": 0.0,
               "score": self.score, **extra}
        pkt = msgpack.packb(msg, use_bin_type=True)
        self._publish(msgpack.unpackb(pkt, raw=False), pkt)

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
        self.exited = True
        if self.state not in _TERMINAL:
            tail = "\n".join(self.stderr_tail)
            self.error = self.error or f"Процесс матча завершился (код {code}).\n{tail}"
            self.set_status("error", error=self.error)
        for sub in self.subscribers:
            sub.close()
        if self.on_exit is not None:
            try:
                self.on_exit(self)
            except Exception:
                log.exception("матч %s: ошибка после окончания", self.id)

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
                "viewers": len(self.subscribers), "queue": self.queue}


class MatchManager:
    """Реестр матчей; одновременно идут не больше `max_matches` (новый вытесняет старый).

    Портал (`limits`, DECISIONS №94): у пользователя не больше `per_user` матчей (новый
    вытесняет только его старый), на сервере — не больше `total` процессов матчей, остальные
    ждут в очереди (FIFO; матч, вытеснивший свой же, — первым) и стартуют, когда место
    освободится. Матч без зрителей `idle_stop_s` секунд останавливается (`check_idle`).
    """

    def __init__(self, cfg: ServerConfig, scripts: ScriptStore, projects: ProjectStore) -> None:
        self.cfg = cfg
        self.scripts = scripts
        self.projects = projects
        self.matches: dict[str, MatchProcess] = {}
        #: Портал: матч начался / процесс матча вышел (реплеи пользователя в базе).
        self.on_start: Callable[[MatchProcess], None] | None = None
        self.on_exit: Callable[[MatchProcess], None] | None = None
        #: Портал: лимиты матчей; `None` — локальный режим.
        self.limits: MatchLimits | None = None
        #: Префикс запуска раннеров (портал: песочница); пусто — как локально.
        self.runner_prefix: list[str] = []
        #: Очередь портала: матчи, ждущие места (у каждого — пакет `start` в `_pending`).
        self.queue: list[MatchProcess] = []
        self._pending: dict[str, dict[str, Any]] = {}
        #: Часы простоя без зрителей; тесты подменяют.
        self.now: Callable[[], float] = time.monotonic

    def running(self) -> list[MatchProcess]:
        return [m for m in self.matches.values() if m.state not in _TERMINAL]

    def active(self) -> int:
        """Сколько процессов матчей сейчас запущено (вытесняемые, пока не вышли, — тоже)."""
        return sum(1 for m in self.matches.values() if m.alive)

    # ------------------------------------------------------------ лимиты портала

    def check_limits(self, cfg: Any, overrides: list[str]) -> None:
        """Портал: профиль из разрешённых; ключи профиля, `runner`, `timing` не переопределять."""
        limits = self.limits
        if limits is None:
            return
        if cfg.profile not in limits.profiles:
            raise HTTPException(400, f"Профиль {cfg.profile} на портале недоступен — можно: "
                                     + ", ".join(limits.profiles))
        locked = self._profile_keys(cfg.profile, cfg.module)
        for text in overrides:
            key = text.partition("=")[0].strip()
            parts = key.split(".")
            if parts[0] == "overrides":  # `overrides.x=…` — то же, что `x=…`
                parts = parts[1:]
            path = ".".join(parts)
            if not parts or parts[0] in _LOCKED_ROOTS:
                raise HTTPException(400, f"На портале нельзя менять «{key}»")
            for leaf in locked:
                if path == leaf or leaf.startswith(path + ".") or path.startswith(leaf + "."):
                    raise HTTPException(
                        400, f"«{key}» задаёт профиль {cfg.profile} — на портале его не меняют")

    def _profile_keys(self, profile: str, module: str) -> set[str]:
        """Листья раздела модуля в файле профиля (`world.map_size`, …) — пути в `params`."""
        try:
            data = load_yaml(self.cfg.configs / "profiles" / f"{profile}.yaml")
        except ConfigError:
            return set()
        out: set[str] = set()

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, dict) and node:
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}" if prefix else str(k))
            elif prefix:
                out.add(prefix)

        walk(data.get(module) or {}, "")
        return out

    def _spawn(self, m: MatchProcess, start: dict[str, Any]) -> None:
        if self.on_start is not None and m.owner is not None:
            self.on_start(m)
        m.idle_since = self.now()
        m.spawn(start, cwd=self.cfg.root)

    def _exited(self, m: MatchProcess) -> None:
        """Процесс матча вышел (event loop): реплей в базу портала, место — очереди."""
        try:
            if self.on_exit is not None and m.owner is not None:
                self.on_exit(m)
        finally:
            self.pump()

    def pump(self) -> None:
        """Запустить ждущие матчи, пока есть место."""
        if self.limits is None:
            return
        while self.queue and self.active() < self.limits.total:
            m = self.queue.pop(0)
            m.queue = None
            start = self._pending.pop(m.id)
            log.info("матч %s выходит из очереди", m.id)
            m.set_status("starting")
            self._spawn(m, start)
        self._renumber()

    def _renumber(self) -> None:
        for i, m in enumerate(self.queue, start=1):
            if m.queue != i:
                m.queue = i
                m.set_status(QUEUED, queue=i)

    def _cancel(self, m: MatchProcess) -> None:
        """Снять матч из очереди: процесса не было, реплея нет."""
        if m in self.queue:
            self.queue.remove(m)
        self._pending.pop(m.id, None)
        m.queue = None
        m.set_status("stopped")
        for sub in m.subscribers:
            sub.close()
        log.info("матч %s снят из очереди", m.id)
        self._renumber()

    def check_idle(self) -> None:
        """Портал: матч (и место в очереди) без зрителей `idle_stop_s` секунд — остановить."""
        if self.limits is None:
            return
        now = self.now()
        for m in list(self.matches.values()):
            if m.state in _TERMINAL or m.stopping:
                continue
            if m.subscribers:
                m.idle_since = None
            elif m.idle_since is None:
                m.idle_since = now
            elif now - m.idle_since >= self.limits.idle_stop_s:
                log.info("матч %s без зрителей %.0f с — остановка", m.id,
                         self.limits.idle_stop_s)
                m.stop()

    async def watch_idle(self) -> None:
        """Фоновая задача портала: проверка простоя несколько раз за `idle_stop_s`."""
        assert self.limits is not None
        period = min(1.0, self.limits.idle_stop_s / 4)
        while True:
            await asyncio.sleep(period)
            try:
                self.check_idle()
            except Exception:
                log.exception("проверка матчей без зрителей")

    def match_path(self, name: str) -> Path:
        if not _NAME.match(name):
            raise HTTPException(400, f"Недопустимое имя матча: {name!r}")
        stem = name[:-5] if name.endswith(".yaml") else name
        path = self.cfg.configs / "matches" / f"{stem}.yaml"
        if not path.is_file():
            raise HTTPException(404, f"Нет матча {stem}.yaml в {self.cfg.configs / 'matches'}")
        return path

    def _new_id(self, stem: str, seed: int, replays: Path) -> str:
        base = f"{stem}-s{seed}-{datetime.now():%Y%m%d-%H%M%S}"
        mid, n = base, 1
        while mid in self.matches or (replays / f"{mid}.swr").exists():
            n += 1
            mid = f"{base}-{n}"
        return mid

    def check_scripts(self, names: list[str], projects: list[str] | None = None,
                      space: UserSpace | None = None) -> None:
        """Синтаксис скриптов и проектов матча — до запуска процесса; ошибка → 400 со строкой."""
        scripts = space.scripts if space else self.scripts
        project_store = space.projects if space else self.projects
        checks = [(n, scripts.check_file, None) for n in dict.fromkeys(names)]
        checks += [(n, project_store.check_file, n) for n in dict.fromkeys(projects or [])]
        for name, check, project in checks:
            try:
                _, problems = check(name)
            except ScriptError as e:
                raise HTTPException(e.status, e.message) from e
            if problems:
                p = problems[0]
                label = f"проект {project}" if project else name
                raise HTTPException(400, {
                    **p.as_dict(), "script": None if project else name, "project": project,
                    "message": f"{label}, строка {p.line}: {p.message}",
                })

    def load_config(self, path: Path, overrides: list[str]) -> Any:
        """Проверить конфиг сразу: ошибка — 400, а не упавший процесс."""
        try:
            return load_match(path, configs_dir=self.cfg.configs, cli_overrides=overrides)
        except ConfigError as e:
            raise HTTPException(400, f"Ошибка конфига: {e}") from e

    def start(self, req: StartRequest, space: UserSpace | None = None) -> MatchProcess:
        """Запустить матч. `space` — пользователь портала: его скрипты, реплеи, логи; новый
        матч вытесняет только его же матчи (DECISIONS №94)."""
        path = self.match_path(req.match)
        self.check_scripts(req.scripts, req.projects, space)
        overrides = list(req.overrides)
        if req.seed is not None:
            overrides.append(f"seed={req.seed}")
        cfg = self.load_config(path, overrides)
        self.check_limits(cfg, overrides)
        owner = space.user_id if space else None
        per_user = self.limits.per_user if self.limits else self.cfg.max_matches
        running = [m for m in self.running() if m.owner == owner]
        evicted = False
        for old in running[: max(0, len(running) - per_user + 1)]:
            log.info("новый матч вытесняет %s", old.id)
            evicted = evicted or old.state != QUEUED
            old.stop()
        replays = space.replays if space else self.cfg.replays
        logs = space.logs if space else self.cfg.logs
        mid = self._new_id(path.stem, cfg.seed, replays)
        m = MatchProcess(id=mid, match=path.stem, seed=cfg.seed,
                         created=datetime.now().isoformat(timespec="seconds"),
                         replay=replays / f"{mid}.swr", loop=asyncio.get_running_loop(),
                         owner=owner, on_exit=self._exited, on_cancel=self._cancel,
                         duration_s=cfg.duration_s, speed=req.speed)
        start: dict[str, Any] = {
            "t": "start", "id": mid, "match": str(path), "configs": str(self.cfg.configs),
            "overrides": overrides, "replay": str(m.replay), "log_dir": str(logs / mid),
            "speed": req.speed}
        if space is not None:
            start["script_dirs"] = [str(d) for d in space.script_dirs]
        if self.runner_prefix:
            start["runner_launch"] = {"prefix": list(self.runner_prefix)}
        self.matches[mid] = m
        if self.limits is not None and self.active() >= self.limits.total:
            # Место освободит вытесненный матч пользователя — его новый матч ждёт первым.
            if evicted:
                self.queue.insert(0, m)
            else:
                self.queue.append(m)
            self._pending[mid] = start
            m.idle_since = self.now()
            self._renumber()
            log.info("матч %s в очереди (№%s)", mid, m.queue)
        else:
            self._spawn(m, start)
            log.info("матч %s запущен (%s, seed %s)", mid, path.name, cfg.seed)
        self._forget_old()
        return m

    def _forget_old(self) -> None:
        done = [m for m in self.matches.values()
                if m.state in _TERMINAL and (m.proc is None or m.exited)]
        for m in done[: max(0, len(done) - _KEEP_FINISHED)]:
            if not m.subscribers:
                del self.matches[m.id]

    def get(self, mid: str, owner: int | None = None) -> MatchProcess:
        """Матч по id; на портале чужой — 404, как несуществующий (не выдаём, что он есть)."""
        m = self.matches.get(mid)
        if m is None or m.owner != owner:
            raise HTTPException(404, f"Нет матча {mid!r}")
        return m

    @staticmethod
    def wait_exit(matches: list[MatchProcess], timeout: float = _STOP_TIMEOUT_S + 2) -> None:
        """Дождаться выхода процессов матчей (после `stop`); не вышел — `kill`."""
        for m in matches:
            if m.proc is None:
                continue
            try:
                m.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                m.proc.kill()
                m.proc.wait(5)

    def shutdown(self) -> None:
        procs = [m.proc for m in self.matches.values() if m.proc and m.proc.poll() is None]
        self.queue.clear()  # ждущие просто забываются: процессов у них нет
        self._pending.clear()
        for m in self.matches.values():
            if m.state != QUEUED:
                m.stop()
        for p in procs:
            try:
                p.wait(_STOP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                p.kill()


# ====================================================================== серии (M7c)


@dataclass
class SeriesProcess:
    """Серия, запущенная сервером: процесс `swarmlab series --progress-json`."""

    id: str
    dir: Path
    proc: subprocess.Popen[bytes]
    stderr_tail: collections.deque[str] = field(
        default_factory=lambda: collections.deque(maxlen=60))

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None


class SeriesManager:
    """Серии матчей: тот же код, что `swarmlab series` (DECISIONS №66), отдельным процессом.

    Сервер не знает модулей: колонки таблицы, ульи и итог он берёт из `series.json`
    (процесс серии переписывает его после каждого матча). Прогресс клиент узнаёт опросом
    `GET /api/series/{id}` раз в секунду. Остановка — файл `.stop` в папке серии.
    Одновременно идёт одна серия: на слабой машине вторая только замедлила бы обе.

    Портал (`limits`, DECISIONS №94): папки серий — у каждого пользователя свои
    (`base` — его `series/`), `n ≤ n_max`, `jobs ≤ jobs_max` (иначе 400), серий на сервере —
    не больше `total` (409); код ульев — только из папок пользователя, раннеры — в песочнице.
    """

    def __init__(self, cfg: ServerConfig, matches: MatchManager) -> None:
        self.cfg = cfg
        self.matches = matches
        self.running: dict[str, SeriesProcess] = {}
        #: Портал: лимиты серий; `None` — локальный режим (одна серия, `jobs` любые).
        self.limits: SeriesLimits | None = None

    def folder(self, sid: str, base: Path | None = None) -> Path:
        if not _NAME.match(sid) or sid.startswith("."):
            raise HTTPException(400, f"Недопустимое имя серии: {sid!r}")
        path = (base or self.cfg.series) / sid
        if not (path / "series.json").is_file():
            raise HTTPException(404, f"Нет серии {sid}")
        return path

    def start(self, req: SeriesRequest, space: UserSpace | None = None) -> dict[str, Any]:
        limits = self.limits
        n_max = min(sr.N_MAX, limits.n_max) if limits else sr.N_MAX
        if not sr.N_MIN <= req.n <= n_max:
            raise HTTPException(400, f"Матчей в серии — от {sr.N_MIN} до {n_max}")
        if limits and req.jobs is not None and req.jobs > limits.jobs_max:
            raise HTTPException(400, f"Процессов серии на портале — не больше {limits.jobs_max}")
        busy = [s for s in self.running.values() if s.alive]
        if len(busy) >= (limits.total if limits else 1):
            # На портале чужую серию не называем.
            name = "" if space else f" {busy[0].id}"
            raise HTTPException(409, f"Уже идёт серия{name} — дождитесь её или остановите")
        path = self.matches.match_path(req.match)
        self.matches.check_scripts(req.scripts, req.projects, space)
        seed = [f"seed={req.start_seed}"] if req.start_seed is not None else []
        cfg = self.matches.load_config(path, [*req.overrides, *seed])
        self.matches.check_limits(cfg, list(req.overrides))
        out = space.series if space else self.cfg.series
        cmd = [sys.executable, "-m", "swarmlab.cli", "series", str(path), "--n", str(req.n),
               "--out", str(out), "--configs", str(self.cfg.configs),
               "--progress-json"]
        if req.start_seed is not None:
            cmd += ["--seed", str(req.start_seed)]
        jobs = req.jobs if req.jobs is not None or limits is None else limits.jobs_max
        if jobs is not None:
            cmd += ["--jobs", str(jobs)]
        if req.team is not None:
            cmd += ["--team", str(req.team)]
        for o in req.overrides:
            cmd += ["--set", o]
        if space is not None:
            for d in space.script_dirs:
                cmd += ["--script-dir", str(d)]
        if self.matches.runner_prefix:
            cmd += ["--runner-prefix-json", json.dumps(self.matches.runner_prefix)]
        env = dict(os.environ)
        env.update(PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=str(self.cfg.root), env=env,
                                creationflags=flags)
        assert proc.stdout is not None
        first = proc.stdout.readline()  # {"t": "start", "id", "dir"} — после сборки мира
        try:
            hello = json.loads(first.decode("utf-8"))
        except ValueError as e:
            err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            proc.wait()
            raise HTTPException(
                400, f"Серия не запустилась: {err.strip() or 'нет ответа'}") from e
        sp = SeriesProcess(id=hello["id"], dir=Path(hello["dir"]), proc=proc)
        self.running[sp.id] = sp
        threading.Thread(target=self._drain, args=(sp,), daemon=True,
                         name=f"series-{sp.id}").start()
        log.info("серия %s запущена (%s, %d матчей)", sp.id, path.name, req.n)
        return self.get(sp.id, space.series if space else None)

    @staticmethod
    def _drain(sp: SeriesProcess) -> None:
        """Читать вывод процесса серии, чтобы пайпы не переполнились."""
        def err() -> None:
            assert sp.proc.stderr is not None
            for raw in sp.proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                sp.stderr_tail.append(line)
                log.info("[серия %s] %s", sp.id, line)

        threading.Thread(target=err, daemon=True).start()
        assert sp.proc.stdout is not None
        for _ in sp.proc.stdout:
            pass
        sp.proc.wait()

    def _read(self, path: Path) -> dict[str, Any]:
        data = sr.read_series(path / sr.SERIES_FILE)
        sp = self.running.get(data.get("id", path.name))
        if sp is not None and sp.dir.resolve() != path.resolve():
            sp = None  # серия с тем же именем у другого пользователя портала
        if data.get("state") == "running" and (sp is None or not sp.alive):
            data["state"] = "interrupted"  # процесс серии умер (или сервер перезапускали)
            if sp is not None and sp.stderr_tail:
                data["error"] = "\n".join(sp.stderr_tail)
        data["done"] = len(data.get("matches", []))
        return data

    def get(self, sid: str, base: Path | None = None) -> dict[str, Any]:
        return self._read(self.folder(sid, base))

    def list(self, base: Path | None = None) -> list[dict[str, Any]]:
        base = base or self.cfg.series
        if not base.is_dir():
            return []
        out = []
        for path in sorted(base.iterdir(), reverse=True):
            if not (path / "series.json").is_file():
                continue
            try:
                d = self._read(path)
            except (OSError, ValueError):
                continue
            s = d.get("summary") or {}
            out.append({k: d.get(k) for k in ("id", "created", "project", "match", "profile",
                                               "duration_s", "start_seed", "n", "state",
                                               "done")}
                       | {"wins": s.get("wins"), "with_code_errors": s.get("with_code_errors"),
                          "played": s.get("played")})
        return out

    def stop(self, sid: str, base: Path | None = None) -> dict[str, Any]:
        path = self.folder(sid, base)
        sp = self.running.get(sid)
        if sp is not None and sp.alive and sp.dir.resolve() == path.resolve():
            (path / ".stop").write_text("", encoding="utf-8")
        return self._read(path)

    def stop_under(self, folder: Path, timeout: float = 30) -> None:
        """Остановить серии, папки которых внутри `folder` (удаление аккаунта), и дождаться."""
        root = folder.resolve()
        mine = [sp for sp in self.running.values()
                if sp.alive and sp.dir.resolve().is_relative_to(root)]
        for sp in mine:
            with contextlib.suppress(OSError):
                (sp.dir / ".stop").write_text("", encoding="utf-8")
        for sp in mine:
            try:
                sp.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                sp.proc.kill()
                sp.proc.wait(5)

    def replay(self, sid: str, seed: int, base: Path | None = None) -> Path:
        path = self.folder(sid, base) / f"s{seed}.swr"
        data = self._read(path.parent)
        if not path.is_file() or seed not in {m["seed"] for m in data.get("matches", [])}:
            raise HTTPException(404, f"Нет реплея s{seed}.swr в серии {sid}")
        return path

    def shutdown(self) -> None:
        for sp in self.running.values():
            if sp.alive:
                with contextlib.suppress(OSError):
                    (sp.dir / ".stop").write_text("", encoding="utf-8")
        for sp in self.running.values():
            try:
                sp.proc.wait(30)
            except subprocess.TimeoutExpired:
                sp.proc.kill()


class StartRequest(BaseModel):
    match: str = Field(description="имя файла в configs/matches, например demo.yaml")
    seed: int | None = Field(default=None, ge=0)
    overrides: list[str] = Field(default_factory=list, description="как --set ПУТЬ=ЗНАЧЕНИЕ")
    speed: float = Field(default=1.0, ge=0.25, le=8.0)
    scripts: list[str] = Field(
        default_factory=list,
        description="скрипты из папки редактора, синтаксис которых проверить до запуска")
    projects: list[str] = Field(
        default_factory=list,
        description="загруженные проекты (имя в projects/), синтаксис которых проверить")


class SeriesRequest(BaseModel):
    match: str = Field(description="имя файла в configs/matches, например demo.yaml")
    overrides: list[str] = Field(default_factory=list, description="как --set ПУТЬ=ЗНАЧЕНИЕ")
    start_seed: int | None = Field(default=None, ge=0, description="нет — случайный")
    n: int = Field(default=10)
    jobs: int | None = Field(default=None, ge=1, le=64)
    team: int | None = Field(default=None, ge=0)
    scripts: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class ToEditorRequest(BaseModel):
    name: str | None = Field(default=None, description="имя своего скрипта; нет — по проекту")


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
    scripts = ScriptStore(cfg.scripts or default_scripts(cfg.root), cfg.root)
    projects = ProjectStore(cfg.projects or cfg.root / "projects", scripts)
    manager = MatchManager(cfg, scripts, projects)
    series = SeriesManager(cfg, manager)
    portal: Portal | None = None
    if cfg.public is not None:
        portal = Portal(cfg.public, cfg.data or cfg.root / "data", cfg.root, scripts)
        portal.manager = manager
        manager.on_start = portal.on_match_start
        manager.on_exit = portal.on_match_end
        manager.limits = cfg.public.matches
        manager.runner_prefix = list(cfg.public.sandbox.runner_prefix)
        series.limits = cfg.public.series

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        idle: asyncio.Task[None] | None = None
        if portal is not None:
            portal.startup()
            idle = asyncio.create_task(manager.watch_idle())
        yield
        if idle is not None:
            idle.cancel()
        loop = asyncio.get_running_loop()
        await asyncio.gather(loop.run_in_executor(None, manager.shutdown),
                             loop.run_in_executor(None, series.shutdown))
        if portal is not None:
            portal.close()

    app = FastAPI(title="SwarmLab", lifespan=lifespan)
    app.state.manager = manager
    app.state.series = series
    app.state.cfg = cfg
    app.state.portal = portal

    def owner(request: Request) -> int | None:
        """Владелец данных запроса: пользователь портала; локальный режим — `None`."""
        return current_user(request).id if portal is not None else None

    def space(request: Request) -> UserSpace | None:
        return portal.space(current_user(request)) if portal is not None else None

    def script_store(request: Request) -> ScriptStore:
        sp = space(request)
        return sp.scripts if sp else scripts

    def project_store(request: Request) -> ProjectStore:
        sp = space(request)
        return sp.projects if sp else projects

    def series_dir(request: Request) -> Path | None:
        sp = space(request)
        return sp.series if sp else None

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
    def list_matches(request: Request) -> list[dict[str, Any]]:
        uid = owner(request)
        return [m.info() for m in reversed(manager.matches.values()) if m.owner == uid]

    @app.post("/api/matches")
    async def start_match(req: StartRequest, request: Request) -> dict[str, Any]:
        return manager.start(req, space(request)).info()

    @app.get("/api/matches/{mid}")
    def get_match(mid: str, request: Request) -> dict[str, Any]:
        return manager.get(mid, owner(request)).info()

    @app.post("/api/matches/{mid}/stop")
    def stop_match(mid: str, request: Request) -> dict[str, Any]:
        m = manager.get(mid, owner(request))
        m.stop()
        return m.info()

    @app.get("/api/replays")
    def list_replays(request: Request) -> list[dict[str, Any]]:
        if portal is not None:
            return portal.replays.list(current_user(request).id)
        if not cfg.replays.is_dir():
            return []
        busy = {m.replay for m in manager.running()}  # ещё пишутся — не дочитаются
        files = sorted((p for p in cfg.replays.glob("*.swr") if p not in busy),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"id": p.stem, "name": p.name, "size": p.stat().st_size,
                 "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(
                     timespec="seconds")} for p in files]

    @app.get("/api/replays/{rid}")
    def get_replay(rid: str, request: Request) -> FileResponse:
        stem = rid[:-4] if rid.endswith(".swr") else rid
        if not _NAME.match(stem):
            raise HTTPException(400, "Недопустимое имя реплея")
        if portal is not None:
            path = portal.replays.path(current_user(request).id, stem)
            return FileResponse(path, media_type="application/octet-stream", filename=path.name)
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
    def list_scripts(request: Request) -> list[dict[str, Any]]:
        return script_store(request).list()

    @app.post("/api/scripts/check")
    def check_script(body: ScriptText) -> dict[str, Any]:
        problems = check_syntax(body.text)
        return {"ok": not problems, "errors": [p.as_dict() for p in problems]}

    @app.get("/api/scripts/{name}")
    def read_script(name: str, request: Request) -> dict[str, Any]:
        return _script_call(script_store(request).read, name)

    @app.put("/api/scripts/{name}")
    def write_script(name: str, body: ScriptText, request: Request) -> dict[str, Any]:
        return _script_call(script_store(request).write, name, body.text, body.blocks)

    # ------------------------------------------------------------ проекты (M7c)

    @app.get("/api/projects")
    def list_projects(request: Request) -> list[dict[str, Any]]:
        return project_store(request).list()

    @app.post("/api/projects")
    async def upload_project(request: Request) -> dict[str, Any]:
        raw = await request.body()
        return _script_call(project_store(request).add, raw)

    @app.get("/api/projects/{name}")
    def read_project(name: str, request: Request) -> dict[str, Any]:
        return _script_call(project_store(request).read, name)

    @app.post("/api/projects/{name}/to-editor")
    def project_to_editor(name: str, request: Request,
                          body: ToEditorRequest | None = None) -> dict[str, Any]:
        return _script_call(project_store(request).to_editor, name, body.name if body else None)

    # ------------------------------------------------------------ серии (M7c)

    @app.get("/api/series")
    def list_series(request: Request) -> list[dict[str, Any]]:
        return series.list(series_dir(request))

    @app.post("/api/series")
    def start_series(req: SeriesRequest, request: Request) -> dict[str, Any]:
        return series.start(req, space(request))

    @app.get("/api/series/{sid}")
    def get_series(sid: str, request: Request) -> dict[str, Any]:
        return series.get(sid, series_dir(request))

    @app.post("/api/series/{sid}/stop")
    def stop_series(sid: str, request: Request) -> dict[str, Any]:
        return series.stop(sid, series_dir(request))

    @app.get("/api/series/{sid}/replays/{seed}")
    def series_replay(sid: str, seed: int, request: Request) -> FileResponse:
        path = series.replay(sid, seed, series_dir(request))
        return FileResponse(path, media_type="application/octet-stream",
                            filename=f"{sid}-{path.name}")

    @app.websocket("/ws/matches/{mid}")
    async def stream(ws: WebSocket, mid: str) -> None:
        m = manager.matches.get(mid)
        if m is not None and portal is not None and m.owner != current_user(ws).id:
            m = None  # чужой матч — как несуществующий
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

    if portal is not None:
        add_routes(app, portal, manager)
        app.add_middleware(PortalGuard, portal=portal)
    if cfg.web.is_dir():
        app.mount("/", StaticFiles(directory=cfg.web, html=True), name="web")
    return app
