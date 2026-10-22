"""Состояние летающих пчёл — структура массивов по слотам пула тел.

Слот `s` закреплён за ульем `s // per_hive` и совпадает с индексом тела в
физическом бэкенде. Свободный слот припаркован (ARCHITECTURE §3.5); рождение
занимает младший свободный слот улья — детерминированно. Пчела получает новый
`uid` при каждом рождении: слоты переиспользуются, идентификаторы — нет.

Параметры типа (радиус, масса, тяга, c_d, энергия…) раскладываются по слотам при
рождении, поэтому горячий цикл читает их одной индексацией без ветвлений по типу.
"""

from __future__ import annotations

import numpy as np

from swarmlab.bees.params import FLYING_KINDS, BeeTypes, FlyingKind

#: Состояния слота.
FREE, IN_HIVE, FLYING, FALLING = 0, 1, 2, 3
STATE_NAMES = ("free", "in_hive", "flying", "falling")

#: Поля типа, которые копируются в слот при рождении.
_TYPE_FIELDS = (
    "radius",
    "mass",
    "cargo_max",
    "thrust_max",
    "cruise_speed",
    "view_radius",
    "drag_coef",
    "energy_max",
    "power_idle",
    "power_coef",
)


class PoolFullError(RuntimeError):
    """В улье нет свободного слота пула."""


class BeeState:
    """Массивы состояния пчёл (SoA), индекс — слот пула."""

    def __init__(
        self, n_hives: int, per_hive: int, types: BeeTypes, cargo_unit_mass: float
    ) -> None:
        n = n_hives * per_hive
        self.n_hives = n_hives
        self.per_hive = per_hive
        self.cargo_unit_mass = cargo_unit_mass
        #: Таблица параметров по типам: `_table[field][kind_index]`.
        self._table = {
            f: np.array([getattr(types.of(k), f) for k in FLYING_KINDS]) for f in _TYPE_FIELDS
        }

        self.state = np.full(n, FREE, dtype=np.int8)
        self.uid = np.full(n, -1, dtype=np.int64)
        self.hive = np.repeat(np.arange(n_hives, dtype=np.int64), per_hive)
        self.kind = np.zeros(n, dtype=np.int64)

        t = types.forager  # заглушка для свободных слотов
        self.radius = np.full(n, t.radius)
        self.mass_empty = np.full(n, t.mass)
        self.cargo = np.zeros(n)
        self.cargo_max = np.zeros(n)
        self.thrust_max = np.zeros(n)
        self.cruise_empty = np.zeros(n)
        self.view_radius = np.zeros(n)
        self.drag_coef = np.zeros(n)
        self.energy = np.zeros(n)
        self.energy_max = np.zeros(n)
        self.power_idle = np.zeros(n)
        self.power_coef = np.zeros(n)
        #: Тяга последнего шага физики (для энергии и тестов), Н.
        self.thrust = np.zeros((n, 3))
        #: Прямая команда тяги (`thrust(fx, fy, fz)`, §3.3); NaN — управляет автопилот.
        self.thrust_cmd = np.full((n, 3), np.nan)

        self._next_uid = 0
        self._airborne: np.ndarray | None = None
        self._alive: np.ndarray | None = None

    @property
    def n(self) -> int:
        return int(self.state.shape[0])

    @property
    def mass(self) -> np.ndarray:
        """Полная масса с грузом, кг `(N,)`."""
        return self.mass_empty + self.cargo * self.cargo_unit_mass

    # --------------------------------------------------------------- выборки (кэш)

    def _changed(self) -> None:
        self._airborne = None
        self._alive = None

    @property
    def airborne(self) -> np.ndarray:
        """Слоты с телом в воздухе (`FLYING` и `FALLING`) — по ним идёт горячий цикл."""
        if self._airborne is None:
            self._airborne = np.flatnonzero((self.state == FLYING) | (self.state == FALLING))
        return self._airborne

    @property
    def alive(self) -> np.ndarray:
        """Живые пчёлы (в улье и в воздухе)."""
        if self._alive is None:
            self._alive = np.flatnonzero(self.state != FREE)
        return self._alive

    def hive_slots(self, hive: int) -> slice:
        return slice(hive * self.per_hive, (hive + 1) * self.per_hive)

    # --------------------------------------------------------------- рождение и гибель

    def allocate(self, hive: int, kind: FlyingKind, state: int = FLYING) -> int:
        """Занять младший свободный слот улья под пчелу типа `kind`; вернуть слот."""
        free = np.flatnonzero(self.state[self.hive_slots(hive)] == FREE)
        if free.size == 0:
            raise PoolFullError(f"В улье {hive} нет свободных слотов (пул {self.per_hive})")
        s = hive * self.per_hive + int(free[0])
        k = FLYING_KINDS.index(kind)
        tbl = self._table
        self.kind[s] = k
        self.radius[s] = tbl["radius"][k]
        self.mass_empty[s] = tbl["mass"][k]
        self.cargo[s] = 0.0
        self.cargo_max[s] = tbl["cargo_max"][k]
        self.thrust_max[s] = tbl["thrust_max"][k]
        self.cruise_empty[s] = tbl["cruise_speed"][k]
        self.view_radius[s] = tbl["view_radius"][k]
        self.drag_coef[s] = tbl["drag_coef"][k]
        self.energy_max[s] = tbl["energy_max"][k]
        self.energy[s] = tbl["energy_max"][k]
        self.power_idle[s] = tbl["power_idle"][k]
        self.power_coef[s] = tbl["power_coef"][k]
        self.thrust[s] = 0.0
        self.thrust_cmd[s] = np.nan
        self.uid[s] = self.new_uid()
        self.state[s] = state
        self._changed()
        return s

    def new_uid(self) -> int:
        """Новый идентификатор пчелы (общий счётчик для летающих и домашних)."""
        uid = self._next_uid
        self._next_uid += 1
        return uid

    def set_state(self, slots: np.ndarray, state: int) -> None:
        self.state[slots] = state
        self._changed()

    def release(self, slots: np.ndarray) -> None:
        """Вернуть слоты в пул."""
        self.state[slots] = FREE
        self.uid[slots] = -1
        self.cargo[slots] = 0.0
        self.energy[slots] = 0.0
        self.thrust[slots] = 0.0
        self.thrust_cmd[slots] = np.nan
        self._changed()

    def kind_name(self, slot: int) -> FlyingKind:
        return FLYING_KINDS[int(self.kind[slot])]
