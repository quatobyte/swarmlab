"""Команды пчёл от раннера: разбор `CommandBatch` и режимы движения (BEES_SPEC §3.3).

Раннер присылает для каждой пчелы, которая что-то решила, словарь
`{"move": [op, *args] | None, "wait": seq, "say": [[слово, x, y] | [слово], …],
"marks": [[канал, сила], …]}` и для улья `{"hatch": [kind, …], "say": […],
"home_energy": %, "refuel_energy": %}`. Домашние пчёлы команд не получают — они
работают сами (`economy.py`, DECISIONS №82). API игрока проверяет аргументы в
момент вызова; здесь — повторная защитная проверка (раннер — чужой процесс):
битая команда отбрасывается и считается.

Операции движения (DECISIONS №84–87): `fly_to[x, y, speed]`, `search[x, y, speed]`,
`explore[speed]`, `collect[flower_id, speed]`, `collect_at[x, y, speed]`,
`go_home[speed]`, `refuel[level]`, `stop[]`; `speed` — число или `None`.

Режим движения пчелы хранится массивами по слотам (SoA). Команда с полем
`"wait": seq` — программа игрока ждёт её выполнения (DECISIONS №61): номер,
условие, начало, состояние и результат ожидания тоже хранятся по слотам, модуль
проверяет все ждущие слоты векторно на тике решений.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from swarmlab.bees.params import BEE_KINDS, FLYING_KINDS

#: Режимы движения слота.
HOVER, FLY_TO, GO_HOME, COLLECT, SEARCH, COLLECT_AT = range(6)

_FORAGER = FLYING_KINDS.index("forager")
#: Аргументы операций: описание по позициям ('n' — число, 'i' — целое, 's' — скорость
#: (число или None), 'p' — процент) и кому операция разрешена (None — всем летающим).
_FLYING_OPS: dict[str, tuple[str, int | None]] = {
    "fly_to": ("nns", None),
    "search": ("nns", None),
    "explore": ("s", None),
    "collect": ("is", _FORAGER),
    "collect_at": ("nns", _FORAGER),
    "go_home": ("s", None),
    "refuel": ("p", None),
    "stop": ("", None),
}
#: Условие выполнения команды, которую ждёт программа игрока.
ARRIVE, ENTER, COLLECTED, FOUND, REFUELED = range(5)
WAIT_COND = {
    "fly_to": ARRIVE, "go_home": ENTER, "collect": COLLECTED, "collect_at": COLLECTED,
    "search": FOUND, "explore": FOUND, "refuel": REFUELED,
}
#: Не больше стольких `mark` за тик от одной пчелы.
MAX_MARKS_PER_TICK = 8


class Control:
    """Режимы движения всех слотов пула."""

    def __init__(self, n: int) -> None:
        self.mode = np.full(n, HOVER, dtype=np.int8)
        #: Цель режима: номер цветка (`collect`).
        self.target = np.full(n, -1, dtype=np.int64)
        #: Точка режима (`search`, `collect_at`), м.
        self.place = np.zeros((n, 2))
        #: Скорость команды (NaN — крейсерская).
        self.speed = np.full(n, np.nan)
        #: Пчела в улье хочет вылететь.
        self.exit_pending = np.zeros(n, dtype=bool)
        #: Ожидание программы игрока: номер (0 — не ждёт), условие, начало, состояние
        #: (`core.program.RUNNING/DONE/FAILED`), результат (номер цветка или −1), уровень.
        self.wait_seq = np.zeros(n, dtype=np.int64)
        self.wait_cond = np.zeros(n, dtype=np.int8)
        self.wait_since = np.zeros(n)
        self.wait_state = np.zeros(n, dtype=np.int8)
        self.wait_result = np.full(n, -1, dtype=np.int64)
        self.refuel_level = np.zeros(n)
        #: Автовозврат (DECISIONS №86): пчела сама летит домой и заправляется.
        self.auto_home = np.zeros(n, dtype=bool)
        #: Сколько раз автовозврат закончился — раннер начинает `loop()` с начала.
        self.epoch = np.zeros(n, dtype=np.int64)

    def reset(self, slots: np.ndarray) -> None:
        self.mode[slots] = HOVER
        self.target[slots] = -1
        self.speed[slots] = np.nan
        self.exit_pending[slots] = False
        self.wait_seq[slots] = 0
        self.wait_state[slots] = 0
        self.wait_result[slots] = -1
        self.auto_home[slots] = False
        self.epoch[slots] = 0


@dataclass
class Parsed:
    """Разобранные команды улья на тике, сгруппированные по операциям."""

    #: op → список (слот, аргументы…); аргументы проверены, скорость None → NaN.
    moves: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict)
    #: (слот, слово, x, y); места нет — NaN.
    says: list[tuple[int, str, float, float]] = field(default_factory=list)
    marks: list[tuple[int, int, float]] = field(default_factory=list)
    hatch: list[str] = field(default_factory=list)
    hive_says: list[tuple[str, float, float]] = field(default_factory=list)
    home_energy: float | None = None
    refuel_energy: float | None = None
    #: Команды, выполнения которых ждёт программа: (слот, seq, op, разобрана ли команда).
    waits: list[tuple[int, int, str, bool]] = field(default_factory=list)
    invalid: int = 0


def _num(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError
    f = float(v)
    if not math.isfinite(f):
        raise ValueError
    return f


def _arg(spec: str, v: Any) -> Any:
    if spec == "n":
        return _num(v)
    if spec == "s":
        if v is None:
            return math.nan
        if _num(v) <= 0:
            raise ValueError
        return float(v)
    if spec == "p":
        if not 0 <= _num(v) <= 100:
            raise ValueError
        return float(v)
    if isinstance(v, bool) or not isinstance(v, int):  # 'i'
        raise TypeError
    return int(v)


def _says(v: Any, max_word: int, max_say: int) -> list[tuple[str, float, float]]:
    if not isinstance(v, list) or len(v) > max_say:
        raise ValueError
    out = []
    for m in v:
        if not isinstance(m, list) or len(m) not in (1, 3):
            raise ValueError
        word = m[0]
        if not isinstance(word, str) or not word.strip() or len(word) > max_word:
            raise ValueError
        x, y = (_num(m[1]), _num(m[2])) if len(m) == 3 else (math.nan, math.nan)
        out.append((word, x, y))
    return out


def _wait_seq(cmd: dict[str, Any]) -> int:
    """Номер ожидания команды (0 — не ждут, команда без движения или битый номер).

    Неизвестная или битая команда с ожиданием не разберётся и сразу получит «не
    вышло» — иначе раннер слал бы её снова каждый тик.
    """
    seq = cmd.get("wait")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
        return 0
    move = cmd.get("move")
    return seq if isinstance(move, list) and move else 0


def parse(
    commands: dict[int, dict[str, Any]],
    team_command: dict[str, Any] | None,
    *,
    flying: dict[int, int],
    flying_kind: np.ndarray,
    max_word: int,
    max_say: int,
    channels: int,
) -> Parsed:
    """Разобрать команды улья. `flying` — uid → слот живых летающих пчёл этого улья."""
    out = Parsed()
    for uid in sorted(commands):  # фиксированный порядок — детерминизм
        cmd = commands[uid]
        try:
            if uid in flying:
                slot = flying[uid]
                wait = _wait_seq(cmd)
                try:
                    _parse_flying(out, slot, int(flying_kind[slot]), cmd, max_word, max_say,
                                  channels)
                except (TypeError, ValueError, KeyError, IndexError):
                    if wait:  # битая команда, которую ждут: сразу «не вышло»
                        out.waits.append((slot, wait, "", False))
                    raise
                if wait:
                    out.waits.append((slot, wait, cmd["move"][0], True))
            # Команда погибшей (или чужой) пчеле молча пропускается.
        except (TypeError, ValueError, KeyError, IndexError):
            out.invalid += 1

    if team_command:
        try:
            for kind in team_command.get("hatch") or []:
                if kind not in BEE_KINDS:
                    raise ValueError
                out.hatch.append(kind)
            if team_command.get("say") is not None:
                out.hive_says = _says(team_command["say"], max_word, max_say)
            if team_command.get("home_energy") is not None:
                v = _num(team_command["home_energy"])
                if not 0 <= v <= 90:
                    raise ValueError
                out.home_energy = v
            if team_command.get("refuel_energy") is not None:
                out.refuel_energy = _arg("p", team_command["refuel_energy"])
        except (TypeError, ValueError, KeyError, IndexError):
            out.invalid += 1
    return out


def _parse_flying(
    out: Parsed,
    slot: int,
    kind: int,
    cmd: dict[str, Any],
    max_word: int,
    max_say: int,
    channels: int,
) -> None:
    move = cmd.get("move")
    if move is not None:
        if not isinstance(move, list) or not move or not isinstance(move[0], str):
            raise ValueError
        op, args = move[0], move[1:]
        spec, only = _FLYING_OPS[op]
        if len(args) != len(spec) or (only is not None and kind != only):
            raise ValueError
        parsed = tuple(_arg(s, a) for s, a in zip(spec, args, strict=True))
        out.moves.setdefault(op, []).append((slot, *parsed))
    if cmd.get("say") is not None:
        for word, x, y in _says(cmd["say"], max_word, max_say):
            out.says.append((slot, word, x, y))
    for mark in (cmd.get("marks") or [])[:MAX_MARKS_PER_TICK]:
        channel, amount = mark
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise TypeError
        if not 0 <= channel < channels or _num(amount) < 0:
            raise ValueError
        out.marks.append((slot, channel, float(amount)))
