"""Демо-пилоты без раннера: облёт точек (M0) и рой по случайным точкам (M1).

Это доверенные скрипты внутри процесса симуляции (вызываются из `decide`), а не
код игрока. Они отдают автопилоту те же высокоуровневые команды, что позже будут
приходить из раннера: `fly_to` и `hover`. Рой M1 читает сенсоры (BEES_SPEC §5.1)
так же, как будет читать их код игрока.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swarmlab.bees.autopilot import Autopilot
from swarmlab.bees.params import DemoBee, DemoSwarm
from swarmlab.bees.sensors import AgentSensors


@dataclass
class _Route:
    bee: int  # индекс пчелы (тела)
    points: np.ndarray  # (K, 3): x, y, agl
    loop: bool
    dwell_s: float
    speed: float
    index: int = 0
    dwell_left: float = 0.0
    done: bool = False


class WaypointPilot:
    """Ведёт демо-пчёл по точкам: долетела (≤ `arrive_radius`) → повисела `dwell_s` → дальше."""

    def __init__(self, autopilot: Autopilot, arrive_radius: float) -> None:
        self.autopilot = autopilot
        self.arrive_radius = arrive_radius
        self.routes: list[_Route] = []
        #: Сколько точек пройдено каждым маршрутом (для тестов и логов).
        self.visits: list[int] = []

    def add(self, bee: int, spec: DemoBee, origin_xy: np.ndarray, speed: float) -> None:
        pts = np.array(spec.waypoints, dtype=np.float64)
        pts[:, :2] += origin_xy
        self.routes.append(
            _Route(bee, pts, spec.loop, spec.dwell_s, speed, dwell_left=spec.dwell_s)
        )
        self.visits.append(0)
        self._command(self.routes[-1])

    def decide(self, pos: np.ndarray, vel: np.ndarray, dt: float) -> None:
        """Тик решений: проверить прибытие и выдать следующую точку."""
        ap = self.autopilot
        ref = ap.reference(pos)
        for r_i, route in enumerate(self.routes):
            if route.done:
                continue
            b = route.bee
            arrived = (
                np.linalg.norm(ref[b] - pos[b]) <= self.arrive_radius
                and np.linalg.norm(vel[b]) < 0.5
            )
            if not arrived:
                continue
            route.dwell_left -= dt
            if route.dwell_left > 0:
                continue
            self.visits[r_i] += 1
            nxt = route.index + 1
            if nxt >= len(route.points):
                if not route.loop:
                    route.done = True  # остаёмся висеть в последней точке
                    continue
                nxt = 0
            route.index = nxt
            route.dwell_left = route.dwell_s
            self._command(route)

    def _command(self, route: _Route) -> None:
        x, y, agl = route.points[route.index]
        self.autopilot.fly_to(np.array([route.bee]), np.array([[x, y]]), agl=agl, speed=route.speed)


class RandomWaypoints:
    """Рой M1: каждая пчела летит в случайную точку карты, долетела — новая точка.

    Решения принимаются по сенсорам (`me.id`, `me.pos`), как у кода игрока.
    Случайность — из переданного генератора (`rng("demo")`), порядок обращений
    фиксирован: по ульям, внутри улья — по слотам.
    """

    def __init__(
        self,
        autopilot: Autopilot,
        params: DemoSwarm,
        gen: np.random.Generator,
        half_size: float,
    ) -> None:
        self.autopilot = autopilot
        self.params = params
        self.gen = gen
        self.limit = half_size - params.edge_margin
        self.slot_of: dict[int, int] = {}  # uid → слот
        self.target_xy: dict[int, np.ndarray] = {}
        self.since: dict[int, float] = {}
        self.dwell_left: dict[int, float] = {}
        #: Сколько точек достигнуто (для тестов и логов).
        self.arrivals = 0

    def add(self, uid: int, slot: int, time: float) -> None:
        self.slot_of[uid] = slot
        self._retarget([uid], time)

    def remove(self, uid: int) -> None:
        for d in (self.slot_of, self.target_xy, self.since, self.dwell_left):
            d.pop(uid, None)

    def decide(self, agents: list[AgentSensors], time: float, dt: float) -> None:
        """Тик решений одного улья по его сенсорам."""
        p = self.params
        due: list[int] = []
        for s in agents:
            uid = s["me"]["id"]
            target = self.target_xy.get(uid)
            if target is None:
                continue
            pos = s["me"]["pos"]
            if time - self.since[uid] >= p.retarget_s:
                due.append(uid)
                continue
            if np.hypot(pos[0] - target[0], pos[1] - target[1]) > p.arrive_radius:
                continue
            self.dwell_left[uid] -= dt
            if self.dwell_left[uid] <= 0:
                self.arrivals += 1
                due.append(uid)
        if due:
            self._retarget(due, time)

    def _retarget(self, uids: list[int], time: float) -> None:
        p = self.params
        n = len(uids)
        xy = self.gen.uniform(-self.limit, self.limit, (n, 2))
        agl = self.gen.uniform(*p.agl, n)
        for uid, point in zip(uids, xy, strict=True):
            self.target_xy[uid] = point
            self.since[uid] = time
            self.dwell_left[uid] = p.dwell_s
        slots = np.array([self.slot_of[u] for u in uids], dtype=np.int64)
        self.autopilot.fly_to(slots, xy, agl=agl)
