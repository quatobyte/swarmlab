"""Команды пчёл от раннера: разбор `CommandBatch` и режимы движения (BEES_SPEC §3.3).

Раннер присылает для каждой пчелы, которая что-то решила, словарь
`{"move": [op, *args] | None, "signal": [числа] | None, "marks": [[канал, сила], …]}`
и для улья `{"breed": [[kind, n], …], "cancel": [kind, …], "signal": […]}`.
API игрока проверяет аргументы в момент вызова; здесь — повторная защитная
проверка (раннер — чужой процесс): битая команда отбрасывается и считается.

Режим движения пчелы хранится массивами по слотам (SoA). Режимы, которым нужна
свежая цель каждый тик (`fly_dir`, `go_home`, `collect`, `intercept`), модуль
пересчитывает векторно на тике решений.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from swarmlab.bees.params import BEE_KINDS, FLYING_KINDS

#: Режимы движения слота.
HOVER, FLY_TO, FLY_DIR, GO_HOME, COLLECT, INTERCEPT, THRUST = range(7)
MODE_NAMES = ("hover", "fly_to", "fly_dir", "go_home", "collect", "intercept", "thrust")

_FORAGER = FLYING_KINDS.index("forager")
_GUARD = FLYING_KINDS.index("guard")
#: Сколько аргументов у операции и кому она разрешена (None — всем летающим).
_FLYING_OPS: dict[str, tuple[int, int | None]] = {
    "fly_to": (5, None),
    "fly_dir": (4, None),
    "hover": (0, None),
    "go_home": (0, None),
    "leave_hive": (0, None),
    "collect": (1, _FORAGER),
    "unload": (0, _FORAGER),
    "intercept": (1, _GUARD),
    "thrust": (3, None),
}
HOUSE_OPS = ("rest", "process", "nurse")
#: Не больше стольких `mark` за тик от одной пчелы.
MAX_MARKS_PER_TICK = 8


class Control:
    """Режимы движения всех слотов пула."""

    def __init__(self, n: int) -> None:
        self.mode = np.full(n, HOVER, dtype=np.int8)
        #: Цель режима: номер цветка (`collect`) или uid цели (`intercept`).
        self.target = np.full(n, -1, dtype=np.int64)
        #: Направление `fly_dir` (длина 1).
        self.direction = np.zeros((n, 3))
        #: Скорость `fly_dir`/`intercept`; NaN — крейсерская.
        self.speed = np.full(n, np.nan)
        #: Пчела в улье хочет вылететь.
        self.exit_pending = np.zeros(n, dtype=bool)

    def reset(self, slots: np.ndarray) -> None:
        self.mode[slots] = HOVER
        self.target[slots] = -1
        self.direction[slots] = 0.0
        self.speed[slots] = np.nan
        self.exit_pending[slots] = False


@dataclass
class Parsed:
    """Разобранные команды улья на тике, сгруппированные по операциям."""

    #: op → список (слот, аргументы…); аргументы уже проверены и приведены к float.
    moves: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict)
    #: задача домашней → слоты домашних пчёл.
    house: dict[str, list[int]] = field(default_factory=dict)
    signals: list[tuple[int, list[float]]] = field(default_factory=list)
    marks: list[tuple[int, int, float]] = field(default_factory=list)
    breed: list[tuple[str, int]] = field(default_factory=list)
    cancel: list[str] = field(default_factory=list)
    hive_signal: list[float] | None = None
    invalid: int = 0


def _num(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError
    f = float(v)
    if not math.isfinite(f):
        raise ValueError
    return f


def _opt(v: Any) -> float:
    return math.nan if v is None else _num(v)


def _values(v: Any, limit: int) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) > limit:
        raise ValueError
    return [_num(x) for x in v]


def parse(
    commands: dict[int, dict[str, Any]],
    team_command: dict[str, Any] | None,
    *,
    flying: dict[int, int],
    flying_kind: np.ndarray,
    house: dict[int, int],
    advanced_control: bool,
    max_values: int,
    channels: int,
) -> Parsed:
    """Разобрать команды улья. `flying`/`house` — uid → слот живых пчёл этого улья."""
    out = Parsed()
    for uid in sorted(commands):  # фиксированный порядок — детерминизм
        cmd = commands[uid]
        try:
            if uid in flying:
                slot = flying[uid]
                _parse_flying(out, slot, int(flying_kind[slot]), cmd, advanced_control,
                              max_values, channels)
            elif uid in house:
                move = cmd.get("move")
                if move is not None:
                    if not isinstance(move, list) or len(move) != 1 or move[0] not in HOUSE_OPS:
                        raise ValueError
                    out.house.setdefault(move[0], []).append(house[uid])
            # Команда погибшей (или чужой) пчеле молча пропускается.
        except (TypeError, ValueError, KeyError, IndexError):
            out.invalid += 1

    if team_command:
        try:
            for kind, n in team_command.get("breed") or []:
                if kind not in BEE_KINDS or isinstance(n, bool) or not isinstance(n, int):
                    raise ValueError
                out.breed.append((kind, max(0, min(n, 1000))))
            for kind in team_command.get("cancel") or []:
                if kind not in BEE_KINDS:
                    raise ValueError
                out.cancel.append(kind)
            if team_command.get("signal") is not None:
                out.hive_signal = _values(team_command["signal"], max_values)
        except (TypeError, ValueError):
            out.invalid += 1
    return out


def _parse_flying(
    out: Parsed,
    slot: int,
    kind: int,
    cmd: dict[str, Any],
    advanced: bool,
    max_values: int,
    channels: int,
) -> None:
    move = cmd.get("move")
    if move is not None:
        if not isinstance(move, list) or not move or not isinstance(move[0], str):
            raise ValueError
        op, args = move[0], move[1:]
        n_args, only = _FLYING_OPS[op]
        if len(args) != n_args or (only is not None and kind != only):
            raise ValueError
        if op == "thrust" and not advanced:
            raise ValueError
        if op == "fly_to":
            parsed: tuple[Any, ...] = (
                _num(args[0]), _num(args[1]), _opt(args[2]), _opt(args[3]), bool(args[4])
            )
        elif op == "fly_dir":
            parsed = (_num(args[0]), _num(args[1]), _num(args[2]), _opt(args[3]))
            if parsed[0] == parsed[1] == parsed[2] == 0.0:
                raise ValueError
        elif op in ("collect", "intercept"):
            if isinstance(args[0], bool) or not isinstance(args[0], int):
                raise TypeError
            parsed = (int(args[0]),)
        else:
            parsed = tuple(_num(a) for a in args)
        out.moves.setdefault(op, []).append((slot, *parsed))
    if cmd.get("signal") is not None:
        out.signals.append((slot, _values(cmd["signal"], max_values)))
    for mark in (cmd.get("marks") or [])[:MAX_MARKS_PER_TICK]:
        channel, amount = mark
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise TypeError
        if not 0 <= channel < channels or _num(amount) < 0:
            raise ValueError
        out.marks.append((slot, channel, float(amount)))
