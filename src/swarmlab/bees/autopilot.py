"""Векторный автопилот пчёл (BEES_SPEC §3.4).

PD-регулятор по всем пчёлам сразу, на частоте физики:

    a_des = Kp·(p* − p) + Kd·(v* − v)

записан в эквивалентной форме с ограничением скорости (DECISIONS №24):
`a_des = Kd·(v_ref − v)`, где `v_ref = clip(Kp/Kd · (p* − p), speed)`. Пока
ограничение не действует, это ровно PD с v* = 0; вдали от цели пчела летит не
быстрее заданной скорости, а не разгоняется до упора тяги.

Поверх PD:

* **просвет над рельефом** — опорная высота не ниже `min_clearance` над рельефом
  под пчелой и над рельефом впереди (точка через `terrain_lookahead_s` полёта);
* **обход препятствий** (`avoid_obstacles`) — потенциальное поле: отталкивание
  от поверхности препятствия ближе `avoid_margin` плюс увод скорости вбок по
  касательной, чтобы не застревать за деревом. Препятствие, в зоне действия
  которого лежит сама цель, не отталкивает — так можно подлететь к летку;
* **расталкивание соседей** (`separation`, DECISIONS №27) — мягкое ускорение
  от пчёл, чьи поверхности ближе `separation_margin`;
* **компенсация известных сил** — сопротивления с учётом ветра и дождя: модуль
  передаёт их прогноз в `feedforward`.

Тяга `T = m·(a_des + g) + feedforward` ограничивается `|T| ≤ T_max` с приоритетом
вертикали: сначала удерживается высота, остаток тяги идёт на горизонталь. Тяга
не бывает направлена вниз — снижение идёт за счёт уменьшения тяги.

Пары «пчела–сосед» и «пчела–препятствие» модуль ищет пространственной сеткой на
тике решений (с запасом радиуса) и передаёт сюда локальными индексами; на шаге
физики остаётся только векторная арифметика по готовым парам.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from swarmlab.bees.params import AutopilotParams
from swarmlab.bees.world import Obstacles

GroundFn = Callable[[np.ndarray], np.ndarray]
#: Пары локальных индексов `(i, j)`.
PairIdx = tuple[np.ndarray, np.ndarray]


class Autopilot:
    """Цели и расчёт тяги для `n` слотов. Все поля — массивы по слотам (SoA).

    Цель задаётся точкой `target` (x, y, z). Если `target_agl[i]` не NaN, высота
    цели — `target_agl[i]` над рельефом под пчелой (следование рельефу), а `target[i, 2]`
    не используется. `speed[i]` NaN — крейсерская скорость при текущей массе.
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
        obstacles: Obstacles | None = None,
    ) -> None:
        self.params = params
        self.gravity = gravity
        self.ground = ground
        self.map_limit = map_half_size - 1.0
        self.ceiling_agl = ceiling_agl
        self.obstacles = obstacles
        self.target = np.zeros((n, 3))
        self.target_agl = np.full(n, np.nan)
        self.speed = np.full(n, np.nan)
        self.avoid = np.ones(n, dtype=bool)

    # --------------------------------------------------------------- команды

    def fly_to(
        self,
        ids: np.ndarray,
        xy: np.ndarray,
        *,
        z: np.ndarray | None = None,
        agl: np.ndarray | float | None = None,
        speed: np.ndarray | float | None = None,
        avoid: np.ndarray | bool = True,
    ) -> None:
        """Лететь к точке.

        Высота: абсолютная `z` либо `agl` над рельефом (по умолчанию — `default_agl`).
        `speed=None` — крейсерская. `avoid=False` — без обхода препятствий и соседей.
        """
        ids = np.atleast_1d(ids)
        self.target[ids, :2] = np.clip(xy, -self.map_limit, self.map_limit)
        if z is not None:
            self.target[ids, 2] = z
            self.target_agl[ids] = np.nan
        else:
            self.target_agl[ids] = self.params.default_agl if agl is None else agl
        self.speed[ids] = np.nan if speed is None else speed
        self.avoid[ids] = avoid

    def hover(self, ids: np.ndarray, pos: np.ndarray) -> None:
        """Висеть в точке `pos` (обычно — текущая позиция)."""
        ids = np.atleast_1d(ids)
        self.target[ids] = pos
        self.target_agl[ids] = np.nan

    # --------------------------------------------------------------- расчёт

    def reference(
        self,
        pos: np.ndarray,
        vel: np.ndarray | None = None,
        *,
        ids: np.ndarray | None = None,
        ground: np.ndarray | None = None,
        ground_ahead: np.ndarray | None = None,
    ) -> np.ndarray:
        """Опорная точка с учётом следования рельефу, просвета и потолка, `(K,3)`.

        `ids` — слоты, к которым относятся `pos` (по умолчанию все); `ground` —
        уже посчитанная высота рельефа под `pos`; `ground_ahead` — высота рельефа
        впереди по курсу (если не задана — считается по `vel`).
        """
        sel = slice(None) if ids is None else ids
        if ground is None:
            ground = self.ground(pos[:, :2])
        if ground_ahead is not None:
            ground = np.maximum(ground, ground_ahead)
        elif vel is not None and self.params.terrain_lookahead_s > 0:
            ahead = pos[:, :2] + vel[:, :2] * self.params.terrain_lookahead_s
            ground = np.maximum(ground, self.ground(ahead))
        ref = self.target[sel].copy()
        agl = self.target_agl[sel]
        follow = ~np.isnan(agl)
        ref[follow, 2] = ground[follow] + agl[follow]
        ref[:, 2] = np.clip(
            ref[:, 2], ground + self.params.min_clearance, ground + self.ceiling_agl
        )
        return ref

    def thrust(
        self,
        ids: np.ndarray,
        pos: np.ndarray,
        vel: np.ndarray,
        *,
        mass: np.ndarray,
        thrust_max: np.ndarray,
        cruise: np.ndarray,
        radius: np.ndarray | None = None,
        ground: np.ndarray | None = None,
        ground_ahead: np.ndarray | None = None,
        feedforward: np.ndarray | None = None,
        neighbors: PairIdx | None = None,
        obstacles: PairIdx | None = None,
    ) -> np.ndarray:
        """Вектор тяги `(K,3)`, Н, для слотов `ids` с позициями `pos` и скоростями `vel`.

        `feedforward (K,3)` — сила, которую нужно добавить к тяге, чтобы скомпенсировать
        известные внешние силы (обычно `−(сопротивление + дождь)`). Пары `neighbors` и
        `obstacles` — в локальных индексах `0..K-1` (для препятствий второй индекс —
        номер препятствия).
        """
        p = self.params
        k = ids.shape[0]
        ref = self.reference(pos, vel, ids=ids, ground=ground, ground_ahead=ground_ahead)
        speed = self.speed[ids]
        speed = np.where(np.isnan(speed), cruise, speed)
        v_ref = clip_norm((ref - pos) * (p.kp / p.kd), speed)
        avoid = self.avoid[ids]
        extra = np.zeros((k, 3))

        if (
            obstacles is not None
            and p.avoid_obstacles
            and self.obstacles is not None
            and radius is not None
            and obstacles[0].size
        ):
            dv, acc = self._avoid_obstacles(pos, ref, v_ref, radius, avoid, obstacles)
            v_ref = v_ref + dv
            extra += acc

        a_des = p.kd * (v_ref - vel) + extra
        if neighbors is not None and p.separation and radius is not None and neighbors[0].size:
            a_des += self._separation(pos, radius, avoid, neighbors)

        t = mass[:, None] * a_des
        t[:, 2] += mass * self.gravity
        if feedforward is not None:
            t += feedforward
        return limit_thrust(t, thrust_max)

    def _avoid_obstacles(
        self,
        pos: np.ndarray,
        ref: np.ndarray,
        v_ref: np.ndarray,
        radius: np.ndarray,
        avoid: np.ndarray,
        pairs: PairIdx,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Поправка опорной скорости и ускорение отталкивания от препятствий, `(K,3)` каждое."""
        p = self.params
        obs = self.obstacles
        assert obs is not None
        li, ok = pairs
        k = pos.shape[0]
        z = np.zeros((k, 3))
        rr = obs.radius[ok] + radius[li]
        d = pos[li] - obs.closest(ok, pos[li])
        dist = np.sqrt(np.einsum("ij,ij->i", d, d))
        gap = dist - rr
        near = np.flatnonzero((gap < p.avoid_margin) & avoid[li] & (dist > 1e-9))
        if near.size == 0:
            return z, z.copy()
        li, ok, rr, d, dist, gap = li[near], ok[near], rr[near], d[near], dist[near], gap[near]
        # Препятствие, у которого лежит сама цель, не отталкивает.
        t_d = ref[li] - obs.closest(ok, ref[li])
        m = np.sqrt(np.einsum("ij,ij->i", t_d, t_d)) - rr >= p.avoid_margin
        if not np.any(m):
            return z, z.copy()
        li, d, dist, gap = li[m], d[m], dist[m], gap[m]
        n = d / dist[:, None]  # наружу от препятствия
        w = np.clip(1.0 - gap / p.avoid_margin, 0.0, 2.0)
        acc = (p.avoid_gain * w)[:, None] * n

        # Скорость «внутрь» препятствия гасится и переводится вбок по касательной,
        # в ту сторону, где цель.
        inward = np.maximum(-np.einsum("ij,ij->i", v_ref[li], n), 0.0)
        side = np.column_stack([-n[:, 1], n[:, 0], np.zeros(len(n))])
        side_norm = np.linalg.norm(side, axis=1)
        side = np.where(side_norm[:, None] > 1e-6, side / np.maximum(side_norm, 1e-9)[:, None], 0)
        to_target = ref[li] - pos[li]
        sign = np.where(np.einsum("ij,ij->i", side, to_target) >= 0.0, 1.0, -1.0)
        dv = (np.minimum(w, 1.0) * inward)[:, None] * (n + sign[:, None] * side)
        return scatter_add(k, li, dv), scatter_add(k, li, acc)

    def _separation(
        self, pos: np.ndarray, radius: np.ndarray, avoid: np.ndarray, pairs: PairIdx
    ) -> np.ndarray:
        """Ускорение расталкивания от соседей `(K,3)`."""
        p = self.params
        li, lj = pairs
        d = pos[li] - pos[lj]
        dist = np.sqrt(np.einsum("ij,ij->i", d, d))
        gap = dist - radius[li] - radius[lj]
        m = avoid[li] & (gap < p.separation_margin) & (dist > 1e-9)
        if not np.any(m):
            return np.zeros((pos.shape[0], 3))
        w = np.clip(1.0 - gap[m] / p.separation_margin, 0.0, 2.0)
        acc = (p.separation_gain * w / dist[m])[:, None] * d[m]
        return scatter_add(pos.shape[0], li[m], acc)


def scatter_add(n: int, idx: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Сумма строк `values (M,3)` по индексам `idx (M,)` в массив `(n,3)` (быстрее `np.add.at`)."""
    out = np.empty((n, values.shape[1]))
    for c in range(values.shape[1]):  # по компонентам вектора, не по пчёлам
        out[:, c] = np.bincount(idx, weights=values[:, c], minlength=n)
    return out


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
