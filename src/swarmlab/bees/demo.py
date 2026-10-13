"""Демо-пилот вехи M0: пчела облетает заданные точки без раннера.

Это доверенный скрипт внутри процесса симуляции (вызывается из `decide`), а не
код игрока. Он отдаёт автопилоту те же высокоуровневые команды, что позже будут
приходить из раннера: `fly_to` и `hover`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swarmlab.bees.autopilot import Autopilot
from swarmlab.bees.params import DemoBee


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
