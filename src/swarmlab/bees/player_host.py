"""Хост пчёлок внутри процесса-раннера (`AgentHost`, ARCHITECTURE §3.4).

Работает только в раннере: импортирует скрипт игрока, держит объекты пчёл и
улья между тиками (память в `self` живёт, пока жив раннер), кладёт им свежие
сенсоры и прогоняет их `loop()` в лёгких потоках (`core.program.Program`,
DECISIONS №84). Переключения — строго по порядку `uid`, улей — последним; время
кода игрока меряется `time.perf_counter()` только вокруг переключений в его код
(DECISIONS №32).

* Команда, которая ждёт, возвращает поток в хост; хост отправляет её модулю с
  номером ожидания `wait` и продолжает поток, когда модуль прислал в сенсорах
  `me["wait"] = [seq, состояние, результат]`. Команда, которую модуль не получил
  (тик отброшен по бюджету), отправляется ещё раз с тем же номером.
* `heard` (DECISIONS №87): сообщение видно с тика, когда пришло, до конца
  следующего прохода `loop()`; от каждого отправителя — последнее по каждому слову.
* Ошибка в `loop()` — трассировка в лог (одинаковые — с подсчётом), пчела
  останавливается, на следующем тике `loop()` с начала. Смерть, автовозврат
  домой (модуль увеличил `me["epoch"]`) и конец матча закрывают поток —
  `finally` игрока выполняется.

Ядро этот файл не импортирует; MuJoCo и NumPy здесь не нужны.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swarmlab.bees import api
from swarmlab.core.program import Order, Program
from swarmlab.core.protocol import CommandBatch, SensorBatch

_BASES: dict[str, type] = {
    "scout": api.Scout,
    "forager": api.Collector,
    "hive": api.Hive,
}
#: Одинаковая ошибка повторно пишется в лог на 1-й, 10-й, 100-й… раз.
_REPEAT_LOG = (1, 10, 100, 1000, 10000)
_PLAYER_MODULE = "player_script"


class PlayerLoadError(RuntimeError):
    """Скрипт игрока не загрузился; `player_message` — трассировка для игрока."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.player_message = message


class _Agent:
    """Пчела или улей в хосте: объект игрока, его поток и услышанное."""

    __slots__ = ("epoch", "inbox", "kind", "label", "obj", "passes", "program", "view")

    def __init__(self, kind: str, label: str, team: int) -> None:
        self.kind = kind
        self.label = label
        self.view = api._View(team)
        self.obj: Any = None
        self.program: Program | None = None
        #: Номер автовозврата модуля: изменился — `loop()` с начала.
        self.epoch: int | None = None
        #: Проходов `loop()` начато (сквозной счёт, переживает перезапуски потока).
        self.passes = 0
        #: Услышанное: (отправитель, слово) → (сообщение, проход, в который пришло).
        self.inbox: dict[tuple[int, str], tuple[api.Message, int]] = {}


class HiveHost:
    """Код одного улья в раннере."""

    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self.classes: dict[str, type] = dict(_BASES)
        self.agents: dict[int, _Agent] = {}
        self.hive: _Agent | None = None
        self.team = 0
        self.script_dir: Path | None = None
        self._seq = 0
        self._cpu = 0.0
        self._error_counts: dict[tuple[str, str, int], int] = {}

    # --------------------------------------------------------------- загрузка

    def load(self, hello: dict[str, Any]) -> dict[str, Any]:
        options = hello.get("options") or {}
        for key in ("max_word", "max_say"):
            if key in options:
                api._RULES[key] = int(options[key])
        self.team = int(hello.get("team", 0))
        script = Path(str(hello["script"])).resolve()
        self.script_dir = script.parent
        try:
            module = self._import(script)
        except Exception as e:
            title = f"Скрипт {script.name} не загрузился"
            raise PlayerLoadError(self.format_error(e, title)) from None

        found: dict[str, type] = {}
        for obj in list(vars(module).values()):
            if not isinstance(obj, type) or getattr(obj, "__module__", None) != module.__name__:
                continue
            for kind, base in _BASES.items():
                if issubclass(obj, base) and obj is not base:
                    if kind in found:
                        self.log(
                            f"Найдено несколько классов-{base.__name__}: {found[kind].__name__} и "
                            f"{obj.__name__}; используется {found[kind].__name__}"
                        )
                    else:
                        found[kind] = obj
        self.classes.update(found)
        return {"classes": {k: c.__name__ for k, c in self.classes.items()}}

    def _import(self, script: Path) -> Any:
        if not script.is_file():
            raise FileNotFoundError(f"Нет файла {script}")
        sys.path.insert(0, str(script.parent))  # чтобы скрипт мог импортировать свои модули
        spec = importlib.util.spec_from_file_location(_PLAYER_MODULE, script)
        if spec is None or spec.loader is None:
            raise ImportError(f"Не удалось прочитать {script}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PLAYER_MODULE] = module
        spec.loader.exec_module(module)
        return module

    # --------------------------------------------------------------- тик

    def step(self, batch: SensorBatch) -> CommandBatch:
        self._cpu = 0.0
        commands: dict[int, dict[str, Any]] = {}
        errors: list[int] = []
        rows = {int(raw["me"]["id"]): raw for raw in batch.agents}

        # Погибшие пчёлы — закрыть потоки (finally выполнится) и забыть (id не повторяются).
        for uid in [u for u in self.agents if u not in rows]:
            agent = self.agents.pop(uid)
            self._close(agent, f"finally пчелы id={uid}")

        for uid in sorted(rows):  # фиксированный порядок — детерминизм
            raw = rows[uid]
            agent = self.agents.get(uid)
            if agent is None:
                kind = str(raw["me"]["kind"])
                agent = self.agents[uid] = _Agent(kind, f"Пчела {kind} id={uid}", self.team)
            cmd, failed = self._tick(agent, raw, raw["me"], batch.tick)
            if failed:
                errors.append(uid)
            if cmd:
                commands[uid] = cmd

        team_command = None
        view = batch.team_view
        if view:
            for note in view.get("notes") or []:
                self.log(f"Улей: {note}")
            if self.hive is None:
                self.hive = _Agent("hive", "Улей", self.team)
            team_command, failed = self._tick(self.hive, view, None, batch.tick)
            if failed:
                errors.append(-1)  # ошибка в loop() улья

        return CommandBatch(
            tick=batch.tick,
            commands=commands,
            team_command=team_command or None,
            cpu_ms=self._cpu * 1000.0,
            errors=errors,
        )

    def _tick(
        self, agent: _Agent, raw: dict[str, Any], me: dict[str, Any] | None, tick: int
    ) -> tuple[dict[str, Any], bool]:
        """Один тик агента: сенсоры, услышанное, поток `loop()`; вернуть (команда, ошибка)."""
        view = agent.view
        view.update(raw)
        view.cmd = {}
        now = float(raw.get("time", 0.0))
        status = me.get("wait") if me is not None else None

        if me is not None:
            epoch = int(me.get("epoch", 0))
            if agent.epoch is not None and epoch != agent.epoch and agent.program is not None:
                # Пчела сама вернулась домой и заправилась — loop() с начала.
                program, agent.program = agent.program, None
                self._close_program(program, f"finally ({agent.label})")
            agent.epoch = epoch

        program = agent.program
        self._hear(agent, raw.get("messages") or [], program)
        perf = time.perf_counter
        t0 = perf()
        try:
            if agent.obj is None:
                agent.obj = self._create(agent)
            if program is None:
                program = agent.program = Program(agent.obj.loop, lambda: self._new_pass(agent))
                program.run(now, self._next_seq())
            else:
                out = program.poll(now, status)
                if out is None:
                    if isinstance(program.waiting, Order) and not program.acknowledged(status):
                        return self._with_wait({}, program), False  # команда не дошла — ещё раз
                    return {}, False  # ждём; пчела продолжает команду
                program.run(now, self._next_seq(), out)
        except Exception as e:
            agent.program = None
            self._report(e, f"{agent.label}, тик {tick}", restart=True)
            return ({"move": ["stop"]} if me is not None else {}), True
        finally:
            self._cpu += perf() - t0
        return self._with_wait(dict(view.cmd), program), False

    def _with_wait(self, cmd: dict[str, Any], program: Program) -> dict[str, Any]:
        """Добавить к команде то, чего ждёт поток (команду движения с номером ожидания)."""
        if not program.dead and isinstance(program.waiting, Order):
            cmd["move"] = program.waiting.move
            cmd["wait"] = program.seq
        return cmd

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _create(self, agent: _Agent) -> Any:
        """Объект игрока: данные доступны уже в `__init__`."""
        cls = self.classes.get(agent.kind)
        if cls is None:
            raise ValueError(f"Неизвестный тип {agent.kind!r}")
        obj = cls.__new__(cls)
        object.__setattr__(obj, "_swarmlab_view", agent.view)
        obj.__init__()
        return obj

    # --------------------------------------------------------------- услышанное

    def _hear(self, agent: _Agent, rows: list[dict[str, Any]], program: Program | None) -> None:
        """Новые сообщения тика — в копилку; номер прохода, к которому они относятся."""
        if rows:
            between = program is None or not program.started or program.at_pass_end()
            stamp = agent.passes + (1 if between else 0)
            for m in rows:
                where = m.get("where")
                msg = api.Message(
                    str(m["word"]),
                    api.Point(where[0], where[1]) if where is not None else None,
                    api.Point(*m["from"]),
                    int(m["from_id"]),
                )
                key = (msg._from, msg.word)
                agent.inbox.pop(key, None)  # новое — в конец списка
                agent.inbox[key] = (msg, stamp)
        agent.view.heard = [m for m, _ in agent.inbox.values()]

    def _new_pass(self, agent: _Agent) -> None:
        """Начало прохода `loop()`: забыть то, что пришло до прошлого прохода."""
        agent.passes += 1
        old = agent.passes - 1
        agent.inbox = {k: v for k, v in agent.inbox.items() if v[1] >= old}
        agent.view.heard = [m for m, _ in agent.inbox.values()]

    # --------------------------------------------------------------- закрытие

    def _close(self, agent: _Agent, where: str) -> None:
        if agent.program is not None:
            program, agent.program = agent.program, None
            self._close_program(program, where)

    def _close_program(self, program: Program, where: str) -> None:
        t0 = time.perf_counter()
        try:
            program.close()
        except Exception as e:
            self._report(e, where)
        finally:
            self._cpu += time.perf_counter() - t0

    def close(self) -> None:
        """Конец матча: закрыть все потоки (`finally` выполнится)."""
        for uid in sorted(self.agents):
            self._close(self.agents[uid], f"finally пчелы id={uid}")
        if self.hive is not None:
            self._close(self.hive, "finally улья")

    # --------------------------------------------------------------- ошибки

    def _report(self, exc: BaseException, where: str, restart: bool = False) -> None:
        tb = traceback.extract_tb(exc.__traceback__)
        frame = self._player_frames(tb)[-1:] or tb[-1:]
        key = (
            type(exc).__name__,
            frame[0].filename if frame else "",
            frame[0].lineno or 0 if frame else 0,
        )
        n = self._error_counts.get(key, 0) + 1
        self._error_counts[key] = n
        if n == 1:
            tail = ". На следующем тике loop() начнётся сначала" if restart else ""
            self.log(self.format_error(exc, f"Ошибка: {where}{tail}"))
        elif n in _REPEAT_LOG:
            self.log(f"Та же ошибка ({key[0]}, строка {key[2]}) уже {n} раз. Последний: {where}")

    def _player_frames(self, tb: traceback.StackSummary) -> list[traceback.FrameSummary]:
        if self.script_dir is None:
            return list(tb)
        return [f for f in tb if Path(f.filename).resolve().parent == self.script_dir]

    def format_error(self, exc: BaseException, title: str) -> str:
        """Трассировка только по файлам игрока + текст ошибки (с номером строки)."""
        frames = self._player_frames(traceback.extract_tb(exc.__traceback__))
        lines = [title]
        if frames:
            lines.append("Traceback (most recent call last):")
            lines.extend(s.rstrip("\n") for s in traceback.format_list(frames))
        lines.extend(s.rstrip("\n") for s in traceback.format_exception_only(type(exc), exc))
        return "\n".join(lines)
