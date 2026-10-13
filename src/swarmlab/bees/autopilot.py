"""Векторный автопилот пчёл (BEES_SPEC §3.4).

PD-регулятор по всем пчёлам сразу, на частоте физики:

    a_des = Kp·(p* − p) + Kd·(v* − v)

записан в эквивалентной форме с ограничением скорости:
`a_des = Kd·(v_ref − v)`, где `v_ref = clip(Kp/Kd · (p* − p), speed)`. Пока
ограничение не действует, это ровно PD с v* = 0; вдали от цели пчела летит не
быстрее заданной скорости, а не разгоняется до упора тяги.

Тяга `T = m·(a_des + g)` ограничивается `|T| ≤ T_max` с приоритетом вертикали:
сначала удерживается высота, остаток тяги идёт на горизонталь. Тяга не бывает
направлена вниз — снижение идёт за счёт уменьшения тяги.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from swarmlab.bees.params import AutopilotParams

GroundFn = Callable[[np.ndarray], np.ndarray]


class Autopilot:
    """Цели и расчёт тяги для `n` пчёл. Все поля — массивы по пчёлам (SoA).

    Цель задаётся точкой `target` (x, y, z). Если `target_agl[i]` не NaN, высота
    цели — `target_agl[i]` над рельефом под пчелой (следование рельефу), а `target[i, 2]`
    не используется.
    """

    def __init__(
        self,
        n: int,
        params: AutopilotParams,
        *,
        gravity: float,
        ground: GroundFn,
        map_half_size: float,
        ceiling_agl: float,
    ) -> None:
        self.params = params
        self.gravity = gravity
        self.ground = ground
        self.map_limit = map_half_size - 1.0
        self.ceiling_agl = ceiling_agl
        self.target = np.zeros((n, 3))
        self.target_agl = np.full(n, np.nan)
        self.speed = np.ones(n)

    # --------------------------------------------------------------- команды

    def fly_to(
        self,
        ids: np.ndarray,
        xy: np.ndarray,
        *,
        z: np.ndarray | None = None,
        agl: np.ndarray | float | None = None,
        speed: np.ndarray | float,
    ) -> None:
        """Лететь к точке.

        Высота: абсолютная `z` либо `agl` над рельефом (по умолчанию — `default_agl`).
        """
        ids = np.atleast_1d(ids)
        self.target[ids, :2] = np.clip(xy, -self.map_limit, self.map_limit)
        if z is not None:
            self.target[ids, 2] = z
            self.target_agl[ids] = np.nan
        else:
            self.target_agl[ids] = self.params.default_agl if agl is None else agl
        self.speed[ids] = speed

    def hover(self, ids: np.ndarray, pos: np.ndarray) -> None:
        """Висеть в точке `pos` (обычно — текущая позиция)."""
        ids = np.atleast_1d(ids)
        self.target[ids] = pos
        self.target_agl[ids] = np.nan

    # --------------------------------------------------------------- расчёт

    def reference(self, pos: np.ndarray) -> np.ndarray:
        """Опорная точка с учётом следования рельефу, просвета и потолка, `(n,3)`."""
        ground = self.ground(pos[:, :2])
        ref = self.target.copy()
        follow = ~np.isnan(self.target_agl)
        ref[follow, 2] = ground[follow] + self.target_agl[follow]
        ref[:, 2] = np.clip(
            ref[:, 2], ground + self.params.min_clearance, ground + self.ceiling_agl
        )
        return ref

    def thrust(
        self,
        pos: np.ndarray,
        vel: np.ndarray,
        mass: np.ndarray,
        thrust_max: np.ndarray,
    ) -> np.ndarray:
        """Вектор тяги `(n,3)`, Н, для позиций `pos` и линейных скоростей `vel`."""
        p = self.params
        error = self.reference(pos) - pos
        v_ref = clip_norm(error * (p.kp / p.kd), self.speed)
        a_des = p.kd * (v_ref - vel)

        t = mass[:, None] * a_des
        t[:, 2] += mass * self.gravity
        return limit_thrust(t, thrust_max)


def clip_norm(v: np.ndarray, max_norm: np.ndarray) -> np.ndarray:
    """Ограничить длину векторов `v (n,3)` значениями `max_norm (n,)`."""
    norm = np.linalg.norm(v, axis=1)
    scale = np.minimum(1.0, max_norm / np.maximum(norm, 1e-12))
    return v * scale[:, None]


def limit_thrust(t: np.ndarray, thrust_max: np.ndarray) -> np.ndarray:
    """`|T| ≤ T_max`, вертикаль в приоритете, тяга вниз запрещена."""
    out = t.copy()
    out[:, 2] = np.clip(out[:, 2], 0.0, thrust_max)
    budget = np.sqrt(np.maximum(thrust_max**2 - out[:, 2] ** 2, 0.0))
    h_norm = np.linalg.norm(out[:, :2], axis=1)
    scale = np.minimum(1.0, budget / np.maximum(h_norm, 1e-12))
    out[:, :2] *= scale[:, None]
    return out
