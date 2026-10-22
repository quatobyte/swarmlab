"""Хост пчёлок внутри процесса-раннера (`AgentHost`, ARCHITECTURE §3.4).

Работает только в раннере: импортирует скрипт игрока, держит объекты пчёл между
тиками (память в `self` живёт, пока жив раннер), переводит словари протокола в
классы `api.py`, вызывает `step()` каждой пчелы и `hive_step(hive)`, собирает
команды. Исключение в `step()` одной пчелы не трогает остальных: пчела
зависает (`hover`), трассировка уходит в лог игрока (одинаковые ошибки — с
подсчётом, без потопа). Время кода игрока меряется `time.perf_counter()`
(DECISIONS №32) — только вокруг вызовов кода игрока.

`step()` и `hive_step()` могут быть генераторами (DECISIONS №57–59): хост держит
генератор между тиками (`core.program.Program`), добавляет к команде номер
ожидания `wait` и продолжает генератор, когда модуль прислал в сенсорах пчелы
`me["wait"] = [seq, состояние]`. Пока программа ждёт, `s` в генераторе
обновляется на месте — после `yield` в нём свежие сенсоры. Пчела погибла —
генератор закрывается (`finally` выполняется); конец матча — `close()`.

Тот же хост без процесса исполняет встроенных ботов врагов (шершни, пауки,
DECISIONS №36): модуль передаёт классы ботов в `use_classes` и вызывает `step`
у себя — протокол и классы API те же, что у игрока.

Ядро этот файл не импортирует; MuJoCo и NumPy здесь не нужны.
"""

from __future__ import annotations

import importlib.util
import inspect
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
    "forager": api.Forager,
    "guard": api.Guard,
    "house": api.HouseBee,
    "hornet": api.Hornet,
    "spider": api.Spider,
}
#: Одинаковая ошибка повторно пишется в лог на 1-й, 10-й, 100-й… раз.
_REPEAT_LOG = (1, 10, 100, 1000, 10000)
_PLAYER_MODULE = "player_script"


class PlayerLoadError(RuntimeError):
    """Скрипт игрока не загрузился; `player_message` — трассировка для игрока."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.player_message = message


class HiveHost:
    """Код одного улья в раннере."""

    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self.classes: dict[str, type] = dict(_BASES)
        self.hive_step: Callable[[api.Hive], Any] | None = None
        self.agents: dict[int, Any] = {}
        self.hive = api.Hive()
        self.team = 0
        self.script_dir: Path | None = None
        #: `step()` с `yield`: генераторы пчёл, которые сейчас ждут (DECISIONS №57).
        self.programs: dict[int, Program] = {}
        #: Объект `s`, который держит генератор: обновляется на месте каждый тик.
        self.held_sensors: dict[int, Any] = {}
        self.hive_program: Program | None = None
        self._seq = 0
        self._error_counts: dict[tuple[str, str, int], int] = {}

    # --------------------------------------------------------------- загрузка

    def load(self, hello: dict[str, Any]) -> dict[str, Any]:
        options = hello.get("options") or {}
        for key in ("advanced_control", "channels", "max_values"):
            if key in options:
                api._RULES[key] = options[key]
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
                            f"Найдено несколько классов-{kind}: {found[kind].__name__} и "
                            f"{obj.__name__}; используется {found[kind].__name__}"
                        )
                    else:
                        found[kind] = obj
        self.classes.update(found)
        hive_step = getattr(module, "hive_step", None)
        self.hive_step = hive_step if callable(hive_step) else None
        return {
            "classes": {k: c.__name__ for k, c in self.classes.items()},
            "hive_step": self.hive_step is not None,
        }

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

    def use_classes(self, classes: dict[str, type]) -> None:
        """Доверенные классы агентов без загрузки скрипта (боты врагов в процессе симуляции)."""
        for kind, cls in classes.items():
            base = _BASES.get(kind)
            if base is None or not issubclass(cls, base):
                raise TypeError(f"{cls!r} — не подкласс {kind}")
            self.classes[kind] = cls

    # --------------------------------------------------------------- тик

    def step(self, batch: SensorBatch) -> CommandBatch:
        cpu = 0.0
        commands: dict[int, dict[str, Any]] = {}
        errors: list[int] = []
        seen: set[int] = set()
        perf = time.perf_counter

        for raw in batch.agents:
            me = raw["me"]
            uid = int(me["id"])
            kind = str(me["kind"])
            seen.add(uid)
            sensors = self._sensors(raw, kind)
            program = self.programs.get(uid)
            t0 = perf()
            try:
                if program is not None:
                    cmd = self._continue(uid, program, sensors, raw)
                else:
                    bee = self.agents.get(uid)
                    if bee is None:
                        bee = self._create(kind, uid)
                    bee.__dict__["_swarmlab_cmd"] = {}
                    result = bee.step(sensors)
                    cmd = bee.__dict__.get("_swarmlab_cmd") or {}
                    if inspect.isgenerator(result):
                        cmd = self._start(uid, Program(result), sensors, float(raw["time"]))
            except Exception as e:
                # Летающий агент зависает; домашняя пчела и паук продолжают как было.
                cmd = {"move": ["hover"]} if kind not in ("house", "spider") else {}
                errors.append(uid)
                self._forget_program(uid)  # генератор с исключением уже закончен
                self._report(e, f"Пчела {kind} id={uid}, тик {batch.tick}")
            finally:
                cpu += perf() - t0
            if cmd:
                commands[uid] = cmd

        # Погибшие пчёлы — закрываем их программы и забываем объекты (id не повторяются).
        for uid in [u for u in self.agents if u not in seen]:
            t0 = perf()
            try:
                self._drop(uid)
            finally:
                cpu += perf() - t0

        team_command = None
        self._update_hive(batch.team_view)
        if self.hive_step is not None:
            hive = self.hive
            hive._swarmlab_cmd = {}
            t0 = perf()
            try:
                self._hive_tick(hive)
                team_command = hive._swarmlab_cmd or None
            except Exception as e:
                self.hive_program = None
                self._report(e, f"hive_step, тик {batch.tick}")
            finally:
                cpu += perf() - t0

        return CommandBatch(
            tick=batch.tick,
            commands=commands,
            team_command=team_command,
            cpu_ms=cpu * 1000.0,
            errors=errors,
        )

    # --------------------------------------------------------------- программы (yield)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _start(self, uid: int, program: Program, sensors: Any, now: float) -> dict[str, Any]:
        """`step()` оказался генератором: прогнать до первого `yield`."""
        bee = self.agents[uid]
        if program.start(now, self._next_seq()):
            self.programs[uid] = program
            self.held_sensors[uid] = sensors
        return self._with_wait(bee.__dict__.get("_swarmlab_cmd") or {}, uid)

    def _continue(
        self, uid: int, program: Program, sensors: Any, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """Пчела ждёт: обновить её `s` на месте и, если ожидание кончилось, продолжить."""
        held = self.held_sensors[uid]
        for name in type(held).__slots__:
            setattr(held, name, getattr(sensors, name))
        status = raw["me"].get("wait")
        now = float(raw["time"])
        result = program.poll(now, status)
        if result is None:
            if program.acknowledged(status):
                return {}  # пчела продолжает команду, которую ждёт
            # Команда не дошла до модуля (бюджет, пропуск тика) — отправить ещё раз.
            return self._with_wait({}, uid)
        bee = self.agents[uid]
        bee.__dict__["_swarmlab_cmd"] = {}
        alive = program.resume(result, now, self._next_seq())
        cmd = bee.__dict__.get("_swarmlab_cmd") or {}
        if not alive:
            self._forget_program(uid)
            return cmd
        return self._with_wait(cmd, uid)

    def _with_wait(self, cmd: dict[str, Any], uid: int) -> dict[str, Any]:
        """Добавить к команде то, чего ждёт программа (`yield жетон`)."""
        program = self.programs.get(uid)
        if program is None or not isinstance(program.waiting, Order):
            return cmd
        cmd = dict(cmd)
        cmd["move"] = program.waiting.move
        if program.seq:
            cmd["wait"] = program.seq
        return cmd

    def _forget_program(self, uid: int) -> None:
        self.programs.pop(uid, None)
        self.held_sensors.pop(uid, None)

    def _drop(self, uid: int) -> None:
        """Пчела погибла: закрыть её программу (`finally` выполнится) и забыть объект."""
        program = self.programs.get(uid)
        self._forget_program(uid)
        del self.agents[uid]
        if program is not None:
            try:
                program.close()
            except Exception as e:
                self._report(e, f"finally пчелы id={uid}")

    def _hive_tick(self, hive: api.Hive) -> None:
        """`hive_step` один раз за тик; если он генератор — ждать по `yield wait(…)`."""
        assert self.hive_step is not None
        program = self.hive_program
        now = hive.time
        if program is not None:
            result = program.poll(now, None)
            if result is not None and not program.resume(result, now, 0):
                self.hive_program = None
            return
        result = self.hive_step(hive)
        if inspect.isgenerator(result):
            program = Program(result)
            if program.start(now, 0):
                self.hive_program = program

    def close(self) -> None:
        """Конец матча: закрыть все программы (`finally` выполнится)."""
        for uid in list(self.programs):
            program = self.programs[uid]
            self._forget_program(uid)
            try:
                program.close()
            except Exception as e:
                self._report(e, f"finally пчелы id={uid}")
        if self.hive_program is not None:
            program, self.hive_program = self.hive_program, None
            try:
                program.close()
            except Exception as e:
                self._report(e, "finally hive_step")

    def _create(self, kind: str, uid: int) -> Any:
        cls = self.classes.get(kind)
        if cls is None:
            raise ValueError(f"Неизвестный тип пчелы {kind!r}")
        bee = cls()
        self.agents[uid] = bee
        return bee

    # --------------------------------------------------------------- ошибки

    def _report(self, exc: BaseException, where: str) -> None:
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
            self.log(self.format_error(exc, f"Ошибка: {where}. Пчела зависла на этом тике"))
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

    # --------------------------------------------------------------- сенсоры

    def _sensors(self, raw: dict[str, Any], kind: str) -> Any:
        if kind == "house":
            return _house_sensors(raw)
        if kind == "hornet":
            return _hornet_sensors(raw)
        if kind == "spider":
            return _spider_sensors(raw)
        return _flying_sensors(raw, self.team)

    def _update_hive(self, view: dict[str, Any]) -> None:
        for note in view.get("notes") or []:
            self.log(f"Улей: {note}")
        h = self.hive
        h.tick = int(view.get("tick", 0))
        h.time = float(view.get("time", 0.0))
        h.honey = float(view.get("honey", 0.0))
        h.nectar = float(view.get("nectar", 0.0))
        h.counts = _counts(view.get("counts") or {})
        h.queue = [api.Larva(q["kind"], q["left_s"]) for q in view.get("queue") or []]
        h.max_bees = int(view.get("max_bees", 0))
        h.costs = dict(view.get("costs") or {})
        h.messages = [
            api.Message(m["from_id"], _vec(m["pos"]), _vec(m["rel_pos"]), tuple(m["values"]))
            for m in view.get("messages") or []
        ]


def _vec(v: list[float]) -> api.Vec:
    return api.Vec(v[0], v[1], v[2])


def _counts(c: dict[str, Any]) -> api.Counts:
    out = api.Counts()
    for kind in ("scout", "forager", "guard"):
        entry = c.get(kind) or {}
        in_hive, flying = int(entry.get("in_hive", 0)), int(entry.get("flying", 0))
        setattr(out, kind, in_hive + flying)
        out.in_hive[kind] = in_hive
        out.flying[kind] = flying
    out.house = int(c.get("house", 0))
    out.in_hive["house"] = out.house
    out.flying["house"] = 0
    return out


def _house_sensors(raw: dict[str, Any]) -> api.HouseSensors:
    me = raw["me"]
    return api.HouseSensors(
        tick=raw["tick"],
        time=raw["time"],
        me=api.HouseMe(me["id"], "house", me.get("task", "rest")),
        hive_nectar=raw["hive_nectar"],
        hive_honey=raw["hive_honey"],
        breeding_queue=[api.Larva(q["kind"], q["left_s"]) for q in raw["breeding_queue"]],
        counts=_counts(raw["counts"]),
    )


def _flying_sensors(raw: dict[str, Any], team: int) -> api.Sensors:
    m = raw["me"]
    pos = _vec(m["pos"])
    px, py, pz = pos
    me = api.Me(
        m["id"], m["kind"], pos, _vec(m["vel"]), m["energy"], m["energy_max"],
        m["cargo"], m["cargo_max"], m["in_hive"], m["alive"],
    )
    home = raw["home"]
    Vec = api.Vec

    def absolute(r: list[float]) -> api.Vec:
        return Vec(px + r[0], py + r[1], pz + r[2])

    def dist(r: list[float]) -> float:
        return (r[0] * r[0] + r[1] * r[1] + r[2] * r[2]) ** 0.5

    flowers = [
        api.Flower(f["id"], absolute(r), Vec(*r), dist(r), f["nectar"], f.get("spider"))
        for f in raw["flowers"]
        for r in (f["rel_pos"],)
    ]
    flowers.sort(key=lambda f: f.dist)
    bees = [
        api.BeeInfo(b["id"], b["kind"], b["team"], b["team"] == team, absolute(r), Vec(*r),
                    dist(r), _vec(b["vel"]))
        for b in raw["bees"]
        for r in (b["rel_pos"],)
    ]
    enemies = [
        api.Enemy(e["id"], e["kind"], absolute(r), Vec(*r), dist(r), _vec(e["vel"]))
        for e in raw["enemies"]
        for r in (e["rel_pos"],)
    ]
    obstacles = [
        api.Obstacle(absolute(r), Vec(*r), dist(r), o["radius"])
        for o in raw["obstacles"]
        for r in (o["rel_pos"],)
    ]
    messages = [
        api.Message(msg["from_id"], absolute(r), Vec(*r), tuple(msg["values"]))
        for msg in raw["messages"]
        for r in (msg["rel_pos"],)
    ]
    ph = raw["pheromones"]
    return api.Sensors(
        tick=raw["tick"],
        time=raw["time"],
        me=me,
        home=api.Home(_vec(home["pos"]), _vec(home["dir"]), home["dist"]),
        ground_z=raw["ground_z"],
        airspeed=_vec(raw["airspeed"]),
        weather=raw["weather"],
        flowers=flowers,
        bees=bees,
        enemies=enemies,
        obstacles=obstacles,
        messages=messages,
        pheromones=api.Pheromones(ph["values"], ph["gradient"]),
    )


def _bee_infos(rows: list[dict[str, Any]], origin: api.Vec, team: int) -> list[api.BeeInfo]:
    Vec = api.Vec
    ox, oy, oz = origin
    out = []
    for b in rows:
        r = b["rel_pos"]
        out.append(
            api.BeeInfo(
                b["id"], b["kind"], b["team"], b["team"] == team,
                Vec(ox + r[0], oy + r[1], oz + r[2]), Vec(*r),
                (r[0] * r[0] + r[1] * r[1] + r[2] * r[2]) ** 0.5, _vec(b["vel"]),
            )
        )
    out.sort(key=lambda b: b.dist)
    return out


def _hornet_sensors(raw: dict[str, Any]) -> api.HornetSensors:
    m = raw["me"]
    pos = _vec(m["pos"])
    me = api.HornetMe(
        m["id"], "hornet", pos, _vec(m["vel"]), m["hp"], m["hp_max"], m["fleeing"]
    )
    hives = []
    for h in raw["hives"]:
        hp = _vec(h["pos"])
        rel = hp - pos
        hives.append(api.HiveInfo(h["team"], hp, rel, rel.length()))
    return api.HornetSensors(
        tick=raw["tick"],
        time=raw["time"],
        me=me,
        ground_z=raw["ground_z"],
        bees=_bee_infos(raw["bees"], pos, -1),
        hives=hives,
        map_half_size=raw["map_half_size"],
    )


def _spider_sensors(raw: dict[str, Any]) -> api.SpiderSensors:
    m = raw["me"]
    pos = _vec(m["pos"])
    return api.SpiderSensors(
        tick=raw["tick"],
        time=raw["time"],
        me=api.SpiderMe(m["id"], "spider", m["flower_id"], pos),
        prey=_bee_infos(raw["prey"], pos, -1),
    )
