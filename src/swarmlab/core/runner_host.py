"""Запуск и обслуживание процессов-раннеров кода игрока (ARCHITECTURE §3.3–3.4).

Один процесс на команду: `sys.executable -m swarmlab.runner` (без `fork`, работает
со spawn на Windows). Код игрока импортируется только внутри раннера.

Параллельность: на Windows `select()` не работает с пайпами, поэтому у каждого
`ProcessLink` свои фоновые потоки — писатель (очередь → stdin раннера), читатель
(stdout раннера → очередь) и читатель stderr (→ лог). Главный поток сначала
отправляет пакеты всем раннерам, потом собирает ответы с общим дедлайном: ядро
ждёт самого медленного раннера, а не сумму всех.

Часы стены (`time.monotonic`) здесь нужны только для таймаутов и в состояние
симуляции не попадают. Если раннер не успел, его тик пропускается — это
единственное место, где реальное время влияет на матч (ARCHITECTURE §3.4).
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from swarmlab.core.config import RunnerConfig
from swarmlab.core.module import TeamSpec
from swarmlab.core.protocol import (
    PROTOCOL_VERSION,
    CommandBatch,
    ProtocolError,
    SensorBatch,
    TeamId,
    encode,
    read_frame,
)

Clock = Callable[[], float]

#: Состояния канала.
STARTING, READY, DEAD, DISABLED = "starting", "ready", "dead", "disabled"
#: Сколько ждать добровольного выхода раннера после `stop`, с.
_STOP_WAIT_S = 1.0
#: Сообщений о превышении бюджета в лог: первые N, потом каждое M-е.
_BUDGET_LOG_FIRST, _BUDGET_LOG_EVERY = 5, 100


@dataclass
class RunnerStats:
    """Статистика раннера команды за матч."""

    team: TeamId
    ticks: int = 0  # тиков решений, на которых команда должна была ответить
    replies: int = 0  # получено вовремя
    missed: int = 0  # нет ответа к дедлайну
    consecutive_missed: int = 0
    over_budget: int = 0  # ответ пришёл, но код игрока превысил бюджет
    restarts: int = 0
    agent_errors: int = 0  # исключений в коде отдельных агентов
    cpu_ms_total: float = 0.0
    cpu_ms_max: float = 0.0
    disabled: bool = False
    load_error: str | None = None

    @property
    def cpu_ms_mean(self) -> float:
        return self.cpu_ms_total / self.replies if self.replies else 0.0


class TeamLog:
    """Лог команды: последние строки в памяти и (если задан) файл."""

    def __init__(self, path: Path | None, keep: int = 5000) -> None:
        self.path = path
        self.lines: deque[str] = deque(maxlen=keep)
        self._lock = threading.Lock()
        self._file: IO[str] | None = None
        self._listeners: list[Callable[[str], None]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = path.open("w", encoding="utf-8", buffering=1)

    def write(self, line: str) -> None:
        with self._lock:
            for part in line.splitlines() or [""]:
                self.lines.append(part)
                if self._file is not None:
                    self._file.write(part + "\n")
                for listener in self._listeners:
                    listener(part)

    def subscribe(self, listener: Callable[[str], None]) -> None:
        """Получать каждую строку лога: сначала уже накопленные, потом новые.

        Слушатель вызывается под замком лога из любого потока — он должен быть быстрым
        (например, класть строку в очередь).
        """
        with self._lock:
            for part in self.lines:
                listener(part)
            self._listeners.append(listener)

    def text(self) -> str:
        with self._lock:
            return "\n".join(self.lines)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None


class ProcessLink:
    """Канал к раннеру-процессу одной команды (реализация `AgentLink`)."""

    def __init__(
        self,
        spec: TeamSpec,
        *,
        module: str,
        seed: int,
        cfg: RunnerConfig,
        options: dict[str, Any],
        log: TeamLog,
        clock: Clock = time.monotonic,
        python: str = sys.executable,
    ) -> None:
        if spec.script is None:
            raise ValueError(f"У команды {spec.name} нет скрипта")
        self.spec = spec
        self.module = module
        self.seed = seed
        self.cfg = cfg
        self.options = options
        self.log = log
        self.clock = clock
        self.python = python
        self.state = DEAD
        self.busy = False  # ждём ответа на отправленный пакет
        self.started_at = 0.0
        self.ready_info: dict[str, Any] = {}
        self.load_error: str | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._inbox: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._outbox: queue.Queue[bytes | None] = queue.Queue()

    @property
    def team(self) -> TeamId:
        return self.spec.team

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    # --------------------------------------------------------------- процесс

    def start(self) -> None:
        """Запустить процесс раннера и поставить в очередь `hello`."""
        env = dict(os.environ)
        env.update(PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        self._proc = proc = subprocess.Popen(
            [self.python, "-m", "swarmlab.runner"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=flags,
        )
        # Новые очереди на каждый запуск: потоки прошлого процесса пишут в старые.
        self._inbox = queue.Queue()
        self._outbox = queue.Queue()
        self.state = STARTING
        self.busy = False
        self.started_at = self.clock()
        assert proc.stdin and proc.stdout and proc.stderr
        for target, args in (
            (_writer, (proc.stdin, self._outbox)),
            (_reader, (proc.stdout, self._inbox)),
            (_stderr_reader, (proc.stderr, self.log)),
        ):
            threading.Thread(target=target, args=args, daemon=True).start()
        self._outbox.put(
            encode(
                {
                    "t": "hello",
                    "v": PROTOCOL_VERSION,
                    "module": self.module,
                    "team": self.team,
                    "script": str(self.spec.script),
                    "seed": self.seed,
                    "budget_ms": self.cfg.budget_ms,
                    "options": self.options,
                }
            )
        )

    def kill(self) -> None:
        """Убить процесс (без вежливости) и закрыть каналы."""
        proc = self._proc
        self._proc = None
        self.busy = False
        if proc is None:
            return
        self._outbox.put(None)
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - ОС не убила процесс
            pass
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass

    def close(self) -> None:
        """Попросить раннер завершиться, по истечении `_STOP_WAIT_S` — убить."""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            self._outbox.put(encode({"t": "stop"}))
            try:
                proc.wait(timeout=_STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                pass
        self.kill()
        if self.state != DISABLED:
            self.state = DEAD

    # --------------------------------------------------------------- рукопожатие

    def poll_ready(self, deadline: float) -> bool:
        """Ждать `ready` до `deadline`; `True` — раннер готов."""
        if self.state != STARTING:
            return self.state == READY
        while True:
            item = self._get(deadline)
            if item is None:
                return False
            kind, msg = item
            if kind != "msg":
                self.state = DEAD
                self.log.write(f"[ядро] раннер завершился при запуске: {msg}")
                return False
            if msg.get("t") != "ready":
                continue
            self.ready_info = msg
            for line in msg.get("log") or []:
                self.log.write(str(line))
            if not msg.get("ok"):
                self.load_error = str(msg.get("error") or "неизвестная ошибка")
                self.log.write("[ядро] скрипт не загрузился:\n" + self.load_error)
                self.state = DISABLED
                self.kill()
                return False
            self.state = READY
            return True

    def wait_ready(self, deadline: float) -> bool:
        return self.poll_ready(deadline)

    # --------------------------------------------------------------- тик

    def send(self, batch: SensorBatch) -> bool:
        """Отправить пакет; `False` — раннер занят прошлым тиком или не готов."""
        if self.state != READY or self.busy:
            return False
        self._outbox.put(encode(batch.to_message()))
        self.busy = True
        return True

    def receive(self, tick: int, deadline: float) -> CommandBatch | None:
        """Ответ на тик `tick` до `deadline`. Устаревшие ответы отбрасываются."""
        while self.busy:
            item = self._get(deadline)
            if item is None:
                return None
            kind, msg = item
            if kind != "msg":
                self.state = DEAD
                self.busy = False
                self.log.write(f"[ядро] раннер завершился: {msg}")
                return None
            if msg.get("t") != "commands":
                continue
            self.busy = False
            try:
                batch = CommandBatch.from_message(msg)
            except (KeyError, TypeError, ValueError, ProtocolError) as e:
                self.log.write(f"[ядро] битый ответ раннера отброшен: {e}")
                return None
            if batch.tick == tick:
                return batch
            # Ответ на старый тик (раннер опоздал) — команды устарели.
            for line in batch.log:
                self.log.write(line)
        return None

    def _get(self, deadline: float) -> tuple[str, Any] | None:
        timeout = deadline - self.clock()
        try:
            if timeout <= 0:
                return self._inbox.get_nowait()
            return self._inbox.get(timeout=timeout)
        except queue.Empty:
            return None


def _writer(stream: IO[bytes], outbox: queue.Queue[bytes | None]) -> None:
    """Поток-писатель: кадры из очереди → stdin раннера. Не блокирует цикл симуляции."""
    while True:
        data = outbox.get()
        if data is None:
            return
        try:
            stream.write(data)
            stream.flush()
        except (OSError, ValueError):
            return


def _reader(stream: IO[bytes], inbox: queue.Queue[tuple[str, Any]]) -> None:
    """Поток-читатель: кадры из stdout раннера → очередь."""
    try:
        while True:
            msg = read_frame(stream)
            if msg is None:
                inbox.put(("eof", "канал закрыт"))
                return
            inbox.put(("msg", msg))
    except (OSError, ValueError, ProtocolError) as e:
        inbox.put(("eof", f"ошибка канала: {e}"))


def _stderr_reader(stream: IO[bytes], log: TeamLog) -> None:
    """Поток: stderr раннера (падения интерпретатора) → лог команды."""
    try:
        for raw in iter(stream.readline, b""):
            log.write("[stderr] " + raw.decode("utf-8", errors="replace").rstrip())
    except (OSError, ValueError):
        return


class RunnerPool:
    """Раннеры всех команд матча: запуск, обмен на тике, таймауты, перезапуски."""

    def __init__(
        self,
        teams: Iterable[TeamSpec],
        *,
        module: str,
        seed: int,
        cfg: RunnerConfig,
        options: dict[str, Any] | None = None,
        log_dir: Path | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self.cfg = cfg
        self.clock = clock
        self.links: dict[TeamId, ProcessLink] = {}
        self.stats: dict[TeamId, RunnerStats] = {}
        self.logs: dict[TeamId, TeamLog] = {}
        for spec in teams:
            log = TeamLog(log_dir / f"{spec.name}.log" if log_dir is not None else None)
            self.logs[spec.team] = log
            self.stats[spec.team] = RunnerStats(spec.team)
            self.links[spec.team] = ProcessLink(
                spec,
                module=module,
                seed=seed,
                cfg=cfg,
                options={**(options or {}), **spec.options},
                log=log,
                clock=clock,
            )

    @property
    def teams(self) -> list[TeamId]:
        return list(self.links)

    def start(self) -> None:
        """Запустить все раннеры параллельно и дождаться рукопожатий."""
        for link in self.links.values():
            link.log.write(f"[ядро] запуск раннера: {link.spec.script}")
            link.start()
        deadline = self.clock() + self.cfg.startup_timeout_s
        for team, link in self.links.items():
            if not link.poll_ready(deadline) and link.state == DISABLED:
                self.stats[team].disabled = True
                self.stats[team].load_error = link.load_error

    def exchange(self, batches: dict[TeamId, SensorBatch]) -> dict[TeamId, CommandBatch]:
        """Тик решений: отправить сенсоры всем, собрать ответы с общим дедлайном.

        Возвращает принятые пакеты команд. Команды не попадают в ответ, если
        раннер не ответил вовремя (тик пропущен), превысил бюджет, отключён или
        ещё запускается.
        """
        now = self.clock()
        expecting: list[TeamId] = []
        for team, batch in batches.items():
            link = self.links.get(team)
            if link is None or link.state == DISABLED:
                continue
            if link.state == STARTING and not link.poll_ready(now):
                if now - link.started_at > self.cfg.startup_timeout_s:
                    self._restart(team, "раннер не ответил на рукопожатие")
                continue  # пока раннер запускается, тики не считаются пропущенными
            self.stats[team].ticks += 1
            link.send(batch)
            expecting.append(team)

        deadline = self.clock() + self.cfg.hard_timeout_ms / 1000.0
        out: dict[TeamId, CommandBatch] = {}
        for team in expecting:
            link, stats = self.links[team], self.stats[team]
            tick = batches[team].tick
            reply = link.receive(tick, deadline)
            if reply is None:
                self._miss(team, tick)
                continue
            stats.replies += 1
            stats.consecutive_missed = 0
            stats.cpu_ms_total += reply.cpu_ms
            stats.cpu_ms_max = max(stats.cpu_ms_max, reply.cpu_ms)
            stats.agent_errors += len(reply.errors)
            for line in reply.log:
                link.log.write(line)
            if reply.cpu_ms > self.cfg.budget_ms:
                stats.over_budget += 1
                n = stats.over_budget
                if n <= _BUDGET_LOG_FIRST or n % _BUDGET_LOG_EVERY == 0:
                    link.log.write(
                        f"[ядро] тик {tick}: код работал {reply.cpu_ms:.1f} мс при бюджете "
                        f"{self.cfg.budget_ms:g} мс — команды тика отброшены "
                        f"(превышений: {n})"
                    )
                continue
            out[team] = reply
        return out

    def _miss(self, team: TeamId, tick: int) -> None:
        stats = self.stats[team]
        stats.missed += 1
        stats.consecutive_missed += 1
        link = self.links[team]
        if link.state == DEAD:
            reason = "раннер не работает"
        else:
            reason = (
                f"код улья не ответил за {self.cfg.hard_timeout_ms:g} мс при бюджете "
                f"{self.cfg.budget_ms:g} мс — бесконечный цикл или слишком долгий step()?"
            )
        link.log.write(
            f"[ядро] тик {tick} пропущен: {reason} "
            f"({stats.consecutive_missed} подряд, всего {stats.missed})"
        )
        if stats.consecutive_missed >= self.cfg.misses_before_restart:
            self._restart(team, f"{stats.consecutive_missed} тика подряд без ответа")

    def _restart(self, team: TeamId, reason: str) -> None:
        stats = self.stats[team]
        link = self.links[team]
        link.kill()
        stats.consecutive_missed = 0
        if stats.restarts >= self.cfg.max_restarts:
            link.state = DISABLED
            stats.disabled = True
            link.log.write(
                f"[ядро] {reason}; лимит перезапусков ({self.cfg.max_restarts}) исчерпан — "
                "улей отключён, пчёлы продолжают последние команды"
            )
            return
        stats.restarts += 1
        link.log.write(
            f"[ядро] {reason} — раннер перезапускается (№{stats.restarts}); "
            "всё, что пчёлы хранили в self, потеряно"
        )
        link.start()

    def close(self) -> None:
        for link in self.links.values():
            link.close()
        for log in self.logs.values():
            log.close()

    def __enter__(self) -> RunnerPool:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
