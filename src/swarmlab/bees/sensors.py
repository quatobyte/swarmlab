"""Сенсоры летающих пчёл (BEES_SPEC §5.1).

Всё, что зависит от числа пчёл, считается векторно: соседи, цветы и препятствия —
пространственной сеткой за O(N·k), шум — одним вызовом генератора на массив.
Затем один проход собирает для каждой пчелы словарь ровно в формате §5.1: только
`dict`, `list`, `float`, `int`, `bool` и `str`, — в M2 он уйдёт в протокол раннера
(msgpack) без изменений.

Формат записи пчелы:

```
{"tick", "time",
 "me": {"id", "kind", "pos", "vel", "energy", "energy_max", "cargo", "cargo_max",
        "in_hive", "alive"},
 "home": {"pos", "dir", "dist"}, "ground_z", "airspeed", "weather",
 "flowers": [{"id", "rel_pos", "nectar"(, "spider")}],
 "bees": [{"id", "rel_pos", "vel", "kind", "team"}],
 "enemies": [{"id", "kind", "rel_pos", "vel"}],
 "obstacles": [{"rel_pos", "radius"}],
 "messages": [{"from_id", "rel_pos", "values"}],
 "pheromones": {"values": [3][3][C], "gradient": [C][2]}}
```

Векторы — списки `[x, y, z]`, `rel_pos` — относительно пчелы. Поле `spider` у
цветка есть только у разведчика ближе `spider_visible_radius`. Пчела в улье
получает ту же запись с `in_hive = True`, позицией летка и пустыми списками.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    tick: int
    time: float
    airborne: np.ndarray  # (K,) слоты пчёл в воздухе
    pos: np.ndarray  # (K,3)
    vel: np.ndarray  # (K,3)
    ground: np.ndarray  # (K,) рельеф под пчёлами
    wind: np.ndarray  # (K,3)
    bee_grid: UniformGrid  # проиндексирован по `pos`
    weather: str
    rain: bool
    messages: Delivery
    #: Живые враги (шершни): uid `(E,)`, позиции и скорости `(E,3)`.
    enemy_uid: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    enemy_pos: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    enemy_vel: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))


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
        self.enemy_grid = UniformGrid(half, params.grid_cell)

    def _noisy(self, values: np.ndarray, sigma: float) -> np.ndarray:
        if self.noise is None or sigma == 0 or values.size == 0:
            return values
        return values + self.noise.normal(0.0, sigma, values.shape)

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
        view = b.view_radius[a] * (p.rain_view_multiplier if inp.rain else 1.0)
        kind = b.kind[a]
        hive = b.hive[a]

        # --------------------------------------------------------------- векторная часть
        bee_pairs = inp.bee_grid.within(inp.pos, view, exclude_self=True)
        flower_pairs = self.flower_grid.within(inp.pos, view)
        obstacle_pairs = self.obstacle_pairs(inp.pos, view)
        self.enemy_grid.build(inp.enemy_pos)
        enemy_pairs = self.enemy_grid.within(inp.pos, view)
        pher_values, pher_grad = self.pheromones.sample(hive, inp.pos)

        # Шум сенсоров — в фиксированном порядке массивов.
        my_pos = self._noisy(inp.pos, p.noise_pos_sigma)
        my_vel = self._noisy(inp.vel, p.noise_vel_sigma)
        bee_rel = self._noisy(bee_pairs.delta, p.noise_pos_sigma)
        bee_vel = self._noisy(inp.vel[bee_pairs.point], p.noise_vel_sigma)
        flower_rel = self._noisy(flower_pairs.delta, p.noise_pos_sigma)
        obstacle_rel = self._noisy(obstacle_pairs.delta, p.noise_pos_sigma)
        enemy_rel = self._noisy(enemy_pairs.delta, p.noise_pos_sigma)
        enemy_vel = self._noisy(inp.enemy_vel[enemy_pairs.point], p.noise_vel_sigma)

        entrance = self.world.hive_entrance[hive]
        to_home = entrance - inp.pos
        home_dist = np.linalg.norm(to_home, axis=1)
        home_dir = to_home / np.maximum(home_dist, 1e-9)[:, None]
        spider_seen = (kind[flower_pairs.query] == _SCOUT) & (
            flower_pairs.dist <= p.spider_visible_radius
        )

        # --------------------------------------------------------------- списки записей
        # Каждый массив переводится в списки Python одним вызовом.
        kinds = list(FLYING_KINDS)
        bee_rows = [
            {"id": i, "rel_pos": r, "vel": v, "kind": kinds[t], "team": h}
            for i, r, v, t, h in zip(
                b.uid[a][bee_pairs.point].tolist(),
                bee_rel.tolist(),
                bee_vel.tolist(),
                kind[bee_pairs.point].tolist(),
                hive[bee_pairs.point].tolist(),
                strict=True,
            )
        ]
        flower_rows: list[dict[str, Any]] = [
            {"id": i, "rel_pos": r, "nectar": n}
            for i, r, n in zip(
                flower_pairs.point.tolist(),
                flower_rel.tolist(),
                self.world.flower_nectar[flower_pairs.point].tolist(),
                strict=True,
            )
        ]
        for j in np.flatnonzero(spider_seen).tolist():
            flower_rows[j]["spider"] = bool(self.world.flower_spider[flower_pairs.point[j]])
        obstacle_rows = [
            {"rel_pos": r, "radius": rad}
            for r, rad in zip(
                obstacle_rel.tolist(),
                self.obstacles.radius[obstacle_pairs.point].tolist(),
                strict=True,
            )
        ]
        enemy_rows = [
            {"id": i, "kind": "hornet", "rel_pos": r, "vel": v}
            for i, r, v in zip(
                inp.enemy_uid[enemy_pairs.point].tolist(),
                enemy_rel.tolist(),
                enemy_vel.tolist(),
                strict=True,
            )
        ]
        eb = _bounds(enemy_pairs.query, k)
        inbox = _messages_by_receiver(inp.messages, self._pos_of(inp))
        bb = _bounds(bee_pairs.query, k)
        fb = _bounds(flower_pairs.query, k)
        ob = _bounds(obstacle_pairs.query, k)

        # --------------------------------------------------------------- записи пчёл
        rows: dict[int, AgentSensors] = {}
        cols = zip(
            a.tolist(),
            b.uid[a].tolist(),
            kind.tolist(),
            my_pos.tolist(),
            my_vel.tolist(),
            b.energy[a].tolist(),
            b.energy_max[a].tolist(),
            b.cargo[a].tolist(),
            b.cargo_max[a].tolist(),
            entrance.tolist(),
            home_dir.tolist(),
            home_dist.tolist(),
            inp.ground.tolist(),
            inp.wind.tolist(),
            pher_values.tolist(),
            pher_grad.tolist(),
            strict=True,
        )
        for i, row in enumerate(cols):
            slot, uid, t, pos, vel, e, e_max, c, c_max, home, hdir, hdist, gz, wind, pv, pg = row
            rows[slot] = {
                "tick": inp.tick,
                "time": inp.time,
                "me": {
                    "id": uid,
                    "kind": kinds[t],
                    "pos": pos,
                    "vel": vel,
                    "energy": e,
                    "energy_max": e_max,
                    "cargo": c,
                    "cargo_max": c_max,
                    "in_hive": False,
                    "alive": True,
                },
                "home": {"pos": home, "dir": hdir, "dist": hdist},
                "ground_z": gz,
                "airspeed": wind,
                "weather": inp.weather,
                "flowers": flower_rows[fb[i] : fb[i + 1]],
                "bees": bee_rows[bb[i] : bb[i + 1]],
                "enemies": enemy_rows[eb[i] : eb[i + 1]],
                "obstacles": obstacle_rows[ob[i] : ob[i + 1]],
                "messages": inbox.get(slot, []),
                "pheromones": {"values": pv, "gradient": pg},
            }
        for slot in np.flatnonzero(b.state == IN_HIVE).tolist():
            rows[slot] = self._in_hive(inp, slot)

        out: dict[int, list[AgentSensors]] = {h: [] for h in range(b.n_hives)}
        for slot in sorted(rows):
            out[int(b.hive[slot])].append(rows[slot])
        return out

    def _pos_of(self, inp: SensorInputs) -> dict[int, list[float]]:
        return dict(zip(inp.airborne.tolist(), inp.pos.tolist(), strict=True))

    def _in_hive(self, inp: SensorInputs, slot: int) -> AgentSensors:
        b = self.bees
        h = int(b.hive[slot])
        entrance = self.world.hive_entrance[h]
        values, grad = self.pheromones.sample(np.array([h]), entrance[None])
        return {
            "tick": inp.tick,
            "time": inp.time,
            "me": {
                "id": int(b.uid[slot]),
                "kind": b.kind_name(slot),
                "pos": entrance.tolist(),
                "vel": [0.0, 0.0, 0.0],
                "energy": float(b.energy[slot]),
                "energy_max": float(b.energy_max[slot]),
                "cargo": float(b.cargo[slot]),
                "cargo_max": float(b.cargo_max[slot]),
                "in_hive": True,
                "alive": True,
            },
            "home": {"pos": entrance.tolist(), "dir": [0.0, 0.0, 0.0], "dist": 0.0},
            "ground_z": float(self.world.ground_height(entrance[:2])),
            "airspeed": [0.0, 0.0, 0.0],
            "weather": inp.weather,
            "flowers": [],
            "bees": [],
            "enemies": [],
            "obstacles": [],
            "messages": [],
            "pheromones": {"values": values[0].tolist(), "gradient": grad[0].tolist()},
        }


def _bounds(query: np.ndarray, n: int) -> list[int]:
    """Границы групп пар по запросам (пары отсортированы по запросу)."""
    return np.concatenate([[0], np.cumsum(np.bincount(query, minlength=n))]).tolist()


def _messages_by_receiver(
    d: Delivery, receiver_pos: dict[int, list[float]]
) -> dict[int, list[dict[str, Any]]]:
    """Сообщения по слотам-получателям в формате §5.1."""
    out: dict[int, list[dict[str, Any]]] = {}
    for recv, msg, rel in zip(d.receiver.tolist(), d.message.tolist(), d.rel_pos.tolist(),
                              strict=True):
        if recv not in receiver_pos:
            continue
        out.setdefault(recv, []).append(
            {"from_id": int(d.sender_uid[msg]), "rel_pos": rel, "values": list(d.values[msg])}
        )
    return out
