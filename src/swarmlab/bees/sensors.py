"""Сенсоры летающих пчёл (BEES_SPEC §5.1, DECISIONS №85).

Всё, что зависит от числа пчёл, считается векторно: соседи и цветы —
пространственной сеткой за O(N·k), шум — одним вызовом генератора на массив.
Затем один проход собирает для каждой пчелы словарь из `dict`, `list`, `float`,
`int`, `bool` и `str` — он уходит в протокол раннера (msgpack) без изменений.

Формат записи пчелы:

```
{"time",
 "me": {"id", "kind", "pos", "energy", "energy_max", "cargo", "cargo_max", "in_hive"},
 "home": [x, y, z],
 "flowers": [{"id", "pos", "nectar"(, "spider")}],
 "bees": [{"id", "pos", "team"}],
 "messages": [{"from_id", "word", "where", "from"}],
 "smell": [C], "smell_way": [C][2]}
```

Позиции — абсолютные `[x, y, z]` (с шумом сенсоров, если он включён). Поле
`spider` у цветка есть только у разведчика ближе `spider_visible_radius` по горизонтали.
`smell` — запах каждого цвета в клетке под пчелой, `smell_way` — градиент
(∂/∂x, ∂/∂y). Пчела в улье получает запись с `in_hive = True`, позицией летка,
пустыми цветами и пчёлами; сообщения она слышит у летка (`comms.py`). Модуль
дописывает в `me` автовозврат, ожидание команды и найденный цветок.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from swarmlab.bees.comms import Delivery
from swarmlab.bees.params import FLYING_KINDS, SensorParams
from swarmlab.bees.pheromones import PheromoneField
from swarmlab.bees.state import IN_HIVE, BeeState
from swarmlab.bees.world import Obstacles, World
from swarmlab.core.spatial import Pairs, UniformGrid

AgentSensors = dict[str, Any]
_SCOUT = FLYING_KINDS.index("scout")


@dataclass
class SensorInputs:
    """Состояние мира на тике решений, нужное для сенсоров."""

    time: float
    airborne: np.ndarray  # (K,) слоты пчёл в воздухе
    pos: np.ndarray  # (K,3)
    bee_grid: UniformGrid  # проиндексирован по `pos`
    rain: bool
    messages: Delivery


class SensorBuilder:
    """Сборщик сенсоров всех пчёл матча на тике решений."""

    def __init__(
        self,
        params: SensorParams,
        world: World,
        bees: BeeState,
        pheromones: PheromoneField,
        obstacles: Obstacles,
        *,
        noise: np.random.Generator | None,
    ) -> None:
        self.params = params
        self.world = world
        self.bees = bees
        self.pheromones = pheromones
        self.obstacles = obstacles
        self.noise = noise
        half = world.half_size
        self.flower_grid = UniformGrid(half, params.grid_cell)
        self.flower_grid.build(world.flower_pos)
        self.obstacle_grid = UniformGrid(half, params.grid_cell)
        self.obstacle_grid.build(obstacles.xy)
        self._obstacle_r_max = float(obstacles.radius.max()) if len(obstacles) else 0.0

    def _noisy(self, values: np.ndarray, sigma: float) -> np.ndarray:
        if self.noise is None or sigma == 0 or values.size == 0:
            return values
        return values + self.noise.normal(0.0, sigma, values.shape)

    def view_radius(self, slots: np.ndarray, rain: bool) -> np.ndarray:
        """Радиус обзора пчёл (в дождь меньше)."""
        return self.bees.view_radius[slots] * (self.params.rain_view_multiplier if rain else 1.0)

    def obstacle_pairs(self, pos: np.ndarray, reach: np.ndarray) -> Pairs:
        """Препятствия, поверхность которых ближе `reach`; `delta` — к ближайшей точке оси."""
        obs = self.obstacles
        cand = self.obstacle_grid.within(pos[:, :2], reach + self._obstacle_r_max)
        if not len(cand):
            return cand
        closest = obs.closest(cand.point, pos[cand.query])
        delta = closest - pos[cand.query]
        dist = np.sqrt(np.einsum("ij,ij->i", delta, delta))
        keep = dist - obs.radius[cand.point] <= reach[cand.query]
        return Pairs(cand.query[keep], cand.point[keep], delta[keep], dist[keep])

    def build(self, inp: SensorInputs) -> dict[int, list[AgentSensors]]:
        """Сенсоры всех живых пчёл, по ульям; внутри улья — по возрастанию слота."""
        p = self.params
        b = self.bees
        a = inp.airborne
        k = a.shape[0]
        view = self.view_radius(a, inp.rain)
        kind = b.kind[a]
        hive = b.hive[a]

        # --------------------------------------------------------------- векторная часть
        bee_pairs = inp.bee_grid.within(inp.pos, view, exclude_self=True)
        flower_pairs = self.flower_grid.within(inp.pos, view)
        smell, smell_way = self._smell(hive, inp.pos)

        # Шум сенсоров — в фиксированном порядке массивов.
        my_pos = self._noisy(inp.pos, p.noise_pos_sigma)
        bee_abs = inp.pos[bee_pairs.query] + self._noisy(bee_pairs.delta, p.noise_pos_sigma)
        flower_abs = inp.pos[flower_pairs.query] + self._noisy(
            flower_pairs.delta, p.noise_pos_sigma
        )
        # Паука видно по горизонтали: высоту полёта игрок не задаёт (DECISIONS №89).
        spider_seen = (kind[flower_pairs.query] == _SCOUT) & (
            np.hypot(flower_pairs.delta[:, 0], flower_pairs.delta[:, 1])
            <= p.spider_visible_radius
        )

        # --------------------------------------------------------------- списки записей
        kinds = list(FLYING_KINDS)
        bee_rows = [
            {"id": i, "pos": r, "team": h}
            for i, r, h in zip(
                b.uid[a][bee_pairs.point].tolist(),
                bee_abs.tolist(),
                hive[bee_pairs.point].tolist(),
                strict=True,
            )
        ]
        flower_rows: list[dict[str, Any]] = [
            {"id": i, "pos": r, "nectar": n}
            for i, r, n in zip(
                flower_pairs.point.tolist(),
                flower_abs.tolist(),
                self.world.flower_nectar[flower_pairs.point].tolist(),
                strict=True,
            )
        ]
        for j in np.flatnonzero(spider_seen).tolist():
            flower_rows[j]["spider"] = bool(self.world.flower_spider[flower_pairs.point[j]])
        inbox = _messages_by_receiver(inp.messages)
        bb = _bounds(bee_pairs.query, k)
        fb = _bounds(flower_pairs.query, k)
        entrance = self.world.hive_entrance

        # --------------------------------------------------------------- записи пчёл
        rows: dict[int, AgentSensors] = {}
        cols = zip(
            a.tolist(),
            b.uid[a].tolist(),
            kind.tolist(),
            hive.tolist(),
            my_pos.tolist(),
            b.energy[a].tolist(),
            b.energy_max[a].tolist(),
            b.cargo[a].tolist(),
            b.cargo_max[a].tolist(),
            smell.tolist(),
            smell_way.tolist(),
            strict=True,
        )
        homes = entrance.tolist()
        for i, row in enumerate(cols):
            slot, uid, t, h, pos, e, e_max, c, c_max, sm, sw = row
            rows[slot] = {
                "time": inp.time,
                "me": {
                    "id": uid, "kind": kinds[t], "pos": pos, "energy": e, "energy_max": e_max,
                    "cargo": c, "cargo_max": c_max, "in_hive": False,
                },
                "home": homes[h],
                "flowers": flower_rows[fb[i] : fb[i + 1]],
                "bees": bee_rows[bb[i] : bb[i + 1]],
                "messages": inbox.get(slot, []),
                "smell": sm,
                "smell_way": sw,
            }
        inside = np.flatnonzero(b.state == IN_HIVE)
        if inside.size:
            h_in = b.hive[inside]
            sm_in, sw_in = self._smell(h_in, entrance[h_in])
            for j, slot in enumerate(inside.tolist()):
                h = int(h_in[j])
                rows[slot] = {
                    "time": inp.time,
                    "me": {
                        "id": int(b.uid[slot]), "kind": b.kind_name(slot), "pos": homes[h],
                        "energy": float(b.energy[slot]),
                        "energy_max": float(b.energy_max[slot]),
                        "cargo": float(b.cargo[slot]), "cargo_max": float(b.cargo_max[slot]),
                        "in_hive": True,
                    },
                    "home": homes[h],
                    "flowers": [],
                    "bees": [],
                    "messages": inbox.get(slot, []),
                    "smell": sm_in[j].tolist(),
                    "smell_way": sw_in[j].tolist(),
                }

        out: dict[int, list[AgentSensors]] = {h: [] for h in range(b.n_hives)}
        for slot in sorted(rows):
            out[int(b.hive[slot])].append(rows[slot])
        return out

    def _smell(self, hive: np.ndarray, pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Запах под пчёлами `(N,C)` и его градиент `(N,C,2)`."""
        values, grad = self.pheromones.sample(hive, pos)
        return values[:, 1, 1, :], grad


def _bounds(query: np.ndarray, n: int) -> list[int]:
    """Границы групп пар по запросам (пары отсортированы по запросу)."""
    return np.concatenate([[0], np.cumsum(np.bincount(query, minlength=n))]).tolist()


def _messages_by_receiver(d: Delivery) -> dict[int, list[dict[str, Any]]]:
    """Сообщения по слотам-получателям в формате протокола."""
    rows = [d.row(i) for i in range(len(d.words))]
    out: dict[int, list[dict[str, Any]]] = {}
    for recv, msg in zip(d.receiver.tolist(), d.message.tolist(), strict=True):
        out.setdefault(recv, []).append(rows[msg])
    return out
