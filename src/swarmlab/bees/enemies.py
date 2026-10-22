"""Враги (BEES_SPEC §7): шершни и пауки — правила мира и встроенная команда ботов.

Боты (`bees/bots/`) написаны на том же API, что и код игроков, и работают как
команда без процесса (DECISIONS №36): на тике решений `Enemies` собирает для них
обычный `SensorBatch` (формат записей — как у протокола раннера), вызывает тот же
`HiveHost`, что и раннер, но прямо в процессе симуляции, и применяет `CommandBatch`.

Правила, которые от ботов не зависят, считает мир — на тике решений, векторно
по матрице «шершни × пчёлы в воздухе» (DECISIONS №37):

* **волны** — с края карты каждые `wave_interval_s`, размер `1 + floor(t / wave_growth_s)`,
  одновременно не больше `max`; точка появления — из `rng("enemies")`;
* **атака** — у шершня одна жертва: пчела, которая касается его дольше всех
  (зазор ≤ `touch_margin`); `kill_contact_s` непрерывного контакта — пчела гибнет;
* **тепловой шар** — ≥ `heat_ball_min_guards` охранников ближе `heat_ball_distance`
  к поверхности шершня: урон `heat_ball_dps` за каждого; HP < `flee_hp` — шершень
  убегает (не атакует и не грабит), у края карты исчезает; HP = 0 — гибнет;
* **грабёж** — шершень ближе `rob_radius` к летку и рядом с ним нет охранников этого
  улья (`rob_guard_radius`): улей теряет `rob_rate` мёда в секунду;
* **пауки** — укус сборщика, собирающего на цветке паука, убивает с вероятностью
  `1 − (1 − p)^dt` за тик (`p` — `kill_prob_per_s`), кубик — `rng("spiders")`.

Тела шершней — отдельный пул в той же модели MuJoCo (маски №31), свой экземпляр
автопилота; идентификаторы — из общего с пчёлами счётчика.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from swarmlab.bees.autopilot import Autopilot
from swarmlab.bees.bots import bot_classes
from swarmlab.bees.control import FLY_DIR, FLY_TO, HOVER, INTERCEPT, Control
from swarmlab.bees.params import FLYING_KINDS, BeesParams
from swarmlab.bees.physics import forces
from swarmlab.bees.player_host import HiveHost
from swarmlab.bees.state import FREE, BeeState
from swarmlab.bees.world import Obstacles, World
from swarmlab.core.protocol import CommandBatch, SensorBatch
from swarmlab.core.rng import RngRegistry

#: Номер «команды» встроенных ботов врагов.
ENEMY_TEAM = -1
_GUARD = FLYING_KINDS.index("guard")
_FORAGER = FLYING_KINDS.index("forager")
#: `fly_dir`: цель — точка на столько метров впереди.
_FLY_DIR_LOOKAHEAD = 20.0
_INTERCEPT_MAX_LEAD_S = 2.0
#: Отступ первой точки волны от края карты внутрь, м; шаг между шершнями волны, м.
_SPAWN_INSET, _SPAWN_STEP = 2.0, 2.0
#: Аргументов у команд движения шершня.
_HORNET_OPS = {"fly_to": 5, "fly_dir": 4, "hover": 0, "intercept": 1}

Emit = Callable[[dict[str, Any]], None]
KillBees = Callable[[np.ndarray, str], None]
#: uid → (найден, позиция, скорость) для `intercept`.
FindTargets = Callable[[np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray]]
ObstaclePairs = Callable[[np.ndarray, np.ndarray], Any]


class Enemies:
    """Шершни (тела, автопилот, правила), пауки и команда ботов врагов."""

    def __init__(
        self,
        params: BeesParams,
        world: World,
        bees: BeeState,
        backend: Any,
        *,
        body_offset: int,
        park_pos: np.ndarray,
        rng: RngRegistry,
        obstacles: Obstacles,
        obstacle_pairs: ObstaclePairs,
        economy: Any,
        emit: Emit,
        kill_bees: KillBees,
        decision_dt: float,
    ) -> None:
        self.params = params
        self.hp_params = hp = params.enemies.hornets
        self.sp_params = sp = params.enemies.spiders
        self.world = world
        self.bees = bees
        self.backend = backend
        self.economy = economy
        self._emit = emit
        self._kill_bees = kill_bees
        self._obstacle_pairs = obstacle_pairs
        self._decision_dt = decision_dt
        self.gen = rng.get("enemies")
        self.spider_gen = rng.get("spiders")

        # ------------------------------------------------------------ шершни
        n = hp.max if hp.enabled else 0
        self.n = n
        self.body = body_offset + np.arange(n, dtype=np.int64)
        self.park_pos = park_pos
        self.alive = np.zeros(n, dtype=bool)
        self.uid = np.full(n, -1, dtype=np.int64)
        self.hp = np.zeros(n)
        self.fleeing = np.zeros(n, dtype=bool)
        self.victim = np.full(n, -1, dtype=np.int64)
        self.contact_s = np.zeros(n)
        self.in_ball = np.zeros(n, dtype=bool)
        self.robbing = np.full(n, -1, dtype=np.int64)
        self.control = Control(n)
        g = params.physics.gravity
        # c_d из крейсерской скорости: √(T_max² − (mg)²) = c_d · v² (§2.2).
        self.drag_coef = float(
            np.sqrt(hp.thrust_max**2 - (hp.mass * g) ** 2) / hp.cruise_speed**2
        )
        self.autopilot = Autopilot(
            n,
            params.autopilot,
            gravity=g,
            ground=world.ground_height,
            map_half_size=world.half_size,
            ceiling_agl=world.ceiling_agl,
            obstacles=obstacles,
        )
        self.next_wave = hp.first_wave_s
        self.active = np.zeros(0, dtype=np.int64)
        self._wind = np.zeros((n, 3))
        self._ground_ahead = np.zeros(n)
        self._obstacle_local: tuple[np.ndarray, np.ndarray] = (np.zeros(0, np.int64),) * 2
        self._obstacle_slack = hp.cruise_speed * 1.5 * decision_dt

        # ------------------------------------------------------------ пауки
        self.spider_flower = (
            np.flatnonzero(world.flower_spider) if sp.enabled else np.zeros(0, np.int64)
        )
        self.spider_uid = np.array([bees.new_uid() for _ in self.spider_flower], dtype=np.int64)
        self._spider_of_uid = dict(
            zip(self.spider_uid.tolist(), self.spider_flower.tolist(), strict=True)
        )
        #: Сборщики, собирающие сейчас на цветках с пауком: (слоты, цветки).
        self.prey: tuple[np.ndarray, np.ndarray] = (np.zeros(0, np.int64),) * 2
        #: Статистика укусов: бросков кубика и сумма вероятностей гибели (для тестов).
        self.bite_rolls = 0
        self.bite_hazard = 0.0

        # ------------------------------------------------------------ команда ботов
        #: Ошибки ботов (трассировки) — доверенный код, но падать матчу нельзя.
        self.log: list[str] = []
        self.host = HiveHost(self.log.append)
        self.host.team = ENEMY_TEAM
        self.host.use_classes(bot_classes(params.enemies))
        #: Счётчики событий врагов за матч.
        self.stats = {
            "hornets_spawned": 0, "hornets_killed": 0, "hornets_left": 0,
            "bees_killed_by_hornets": 0, "bees_killed_by_spiders": 0,
        }

    # --------------------------------------------------------------- выборки

    @property
    def enabled(self) -> bool:
        return self.n > 0 or self.spider_flower.size > 0

    def hornet_state(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Живые шершни: слоты, uid, позиции, скорости."""
        h = self.active
        if h.size == 0:
            z = np.zeros((0, 3))
            return h, self.uid[h], z, z.copy()
        pos, vel = self.backend.body_state(self.body[h])
        return h, self.uid[h], pos, vel

    # --------------------------------------------------------------- тик решений

    def decide(
        self,
        tick: int,
        time: float,
        a: np.ndarray,
        pos: np.ndarray,
        vel: np.ndarray,
        *,
        weather: Any,
        rain_view: float,
    ) -> None:
        """Волны, правила (атака, тепловой шар, грабёж, бегство), боты и укусы пауков.

        `a, pos, vel` — пчёлы в воздухе до этого тика; погибшие здесь пчёлы
        паркуются через `kill_bees`, модуль пересобирает выборки после вызова.
        """
        dt = self._decision_dt
        if self.n:
            self._waves(time)
            self._rules(time, dt, a, pos)
        h, uid, hpos, hvel = self.hornet_state()
        if h.size == 0 and self.spider_flower.size == 0:
            return
        alive = self.bees.state[a] != FREE
        a, pos, vel = a[alive], pos[alive], vel[alive]

        agents = self._hornet_sensors(tick, time, h, uid, hpos, hvel, a, pos, vel, rain_view)
        agents += self._spider_sensors(tick, time, a, pos, vel)
        if not agents:
            return
        batch = SensorBatch(tick=tick, team=ENEMY_TEAM, budget_ms=0.0, agents=agents)
        reply = self.host.step(batch)
        self._apply(reply, time, dt)

        # Окружение шершней до следующего тика: ветер, рельеф впереди, препятствия.
        h, _, hpos, hvel = self.hornet_state()
        if h.size:
            ground = self.world.ground_height(hpos[:, :2])
            self._wind[h] = weather.wind_at(hpos, ground, time)
            lookahead = self.params.autopilot.terrain_lookahead_s
            self._ground_ahead[h] = self.world.ground_height(
                hpos[:, :2] + hvel[:, :2] * lookahead
            )
            reach = np.full(h.size, self.hp_params.radius + self.params.autopilot.avoid_margin)
            obs = self._obstacle_pairs(hpos, reach + self._obstacle_slack)
            self._obstacle_local = (obs.query, obs.point)

    def _waves(self, time: float) -> None:
        hp = self.hp_params
        if time < self.next_wave - 1e-9:
            return
        self.next_wave += hp.wave_interval_s
        size = 1 + int(np.floor(time / hp.wave_growth_s + 1e-9))
        free = np.flatnonzero(~self.alive)
        n = min(size, free.size)
        if n == 0:
            return
        g = self.gen
        half = self.world.half_size
        side = int(g.integers(4))
        along = float(g.uniform(-0.8, 0.8)) * half
        edge = half - _SPAWN_INSET
        k = np.arange(n) * _SPAWN_STEP
        if side == 0:
            xy = np.column_stack([np.full(n, edge), along + k])
        elif side == 1:
            xy = np.column_stack([np.full(n, -edge), along + k])
        elif side == 2:
            xy = np.column_stack([along + k, np.full(n, edge)])
        else:
            xy = np.column_stack([along + k, np.full(n, -edge)])
        xy = np.clip(xy, -edge, edge)
        z = self.world.ground_height(xy) + hp.spawn_agl
        at = np.column_stack([xy, z])
        slots = free[:n]
        self.alive[slots] = True
        self.uid[slots] = [self.bees.new_uid() for _ in range(n)]
        self.hp[slots] = hp.hp
        self.fleeing[slots] = False
        self.victim[slots] = -1
        self.contact_s[slots] = 0.0
        self.in_ball[slots] = False
        self.robbing[slots] = -1
        self.control.reset(slots)
        bodies = self.body[slots]
        self.backend.activate(
            bodies, at, np.full(n, hp.radius), np.full(n, hp.mass)
        )
        self.autopilot.hover(slots, at)
        self.autopilot.speed[slots] = np.nan
        self.autopilot.avoid[slots] = True
        self.active = np.flatnonzero(self.alive)
        self.stats["hornets_spawned"] += n
        for s, p in zip(slots.tolist(), at.tolist(), strict=True):
            self._emit({"type": "hornet_spawn", "time": time, "hornet": int(self.uid[s]),
                        "pos": p})

    def _release(self, slots: np.ndarray) -> None:
        self.alive[slots] = False
        self.uid[slots] = -1
        self.victim[slots] = -1
        self.robbing[slots] = -1
        self.control.reset(slots)
        self.backend.park(self.body[slots], self.park_pos[slots])
        self.active = np.flatnonzero(self.alive)

    def _rules(self, time: float, dt: float, a: np.ndarray, pos: np.ndarray) -> None:
        """Тепловой шар, бегство, гибель, атака, грабёж, уход за край — векторно."""
        h = self.active
        if h.size == 0:
            return
        p = self.hp_params
        b = self.bees
        hpos, _ = self.backend.body_state(self.body[h])
        if a.size:
            d = pos[None, :, :] - hpos[:, None, :]
            dist = np.sqrt(np.einsum("ijk,ijk->ij", d, d))
            gap = dist - p.radius - b.radius[a][None, :]
            kind = b.kind[a]
            hive = b.hive[a]
        else:
            dist = gap = np.zeros((h.size, 0))
            kind = hive = np.zeros(0, dtype=np.int64)
        guard = kind == _GUARD

        # ---------------------------------------------------- тепловой шар
        if p.heat_ball:
            near_guard = guard[None, :] & (gap <= p.heat_ball_distance)
            n_guards = near_guard.sum(axis=1)
            ball = n_guards >= p.heat_ball_min_guards
            self.hp[h] -= np.where(ball, n_guards * p.heat_ball_dps * dt, 0.0)
            for i in np.flatnonzero(ball & ~self.in_ball[h]).tolist():
                hives = hive[near_guard[i]]
                self._emit({"type": "heat_ball", "time": time, "hornet": int(self.uid[h[i]]),
                            "guards": int(n_guards[i]),
                            "hive": int(np.bincount(hives).argmax())})
            self.in_ball[h] = ball

        # ---------------------------------------------------- бегство и гибель
        hp_now = self.hp[h]
        start_flee = (hp_now < p.flee_hp) & (hp_now > 0) & ~self.fleeing[h]
        for s in h[start_flee].tolist():
            self._emit({"type": "hornet_flee", "time": time, "hornet": int(self.uid[s]),
                        "hp": float(self.hp[s])})
        self.fleeing[h] |= hp_now < p.flee_hp
        dead = hp_now <= 0
        for s in h[dead].tolist():
            self._emit({"type": "hornet_death", "time": time, "hornet": int(self.uid[s]),
                        "cause": "heat_ball"})
        self.stats["hornets_killed"] += int(dead.sum())
        attacking = ~self.fleeing[h] & ~dead

        # ---------------------------------------------------- атака: одна жертва на шершня
        kills: list[int] = []
        if p.attack and a.size:
            touching = gap <= p.touch_margin
            bee_uid = b.uid[a]
            for i in range(h.size):
                s = int(h[i])
                if not attacking[i]:
                    self.victim[s], self.contact_s[s] = -1, 0.0
                    continue
                cur = np.flatnonzero(bee_uid == self.victim[s]) if self.victim[s] >= 0 else []
                if len(cur) and touching[i, cur[0]]:
                    self.contact_s[s] += dt
                else:
                    touch = np.flatnonzero(touching[i])
                    if touch.size == 0:
                        self.victim[s], self.contact_s[s] = -1, 0.0
                        continue
                    j = int(touch[np.argmin(gap[i, touch])])
                    self.victim[s], self.contact_s[s] = int(bee_uid[j]), 0.0
                    self._emit({"type": "attack", "time": time, "hornet": int(self.uid[s]),
                                "bee": int(bee_uid[j]), "hive": int(hive[j])})
                    continue
                if self.contact_s[s] >= p.kill_contact_s - 1e-9:
                    j = int(cur[0])
                    if int(a[j]) not in kills:
                        kills.append(int(a[j]))
                    self.victim[s], self.contact_s[s] = -1, 0.0
        if kills:
            self.stats["bees_killed_by_hornets"] += len(kills)
            self._kill_bees(np.array(kills, dtype=np.int64), "hornet")

        # ---------------------------------------------------- грабёж
        if p.rob:
            entrance = self.world.hive_entrance
            de = np.linalg.norm(hpos[:, None, :] - entrance[None, :, :], axis=2)  # (H, ульи)
            guard_close = np.zeros(de.shape, dtype=bool)
            if a.size:
                close = guard[None, :] & (dist <= p.rob_guard_radius)
                for hv in range(entrance.shape[0]):
                    guard_close[:, hv] = np.any(close & (hive == hv)[None, :], axis=1)
            rob = (de <= p.rob_radius) & ~guard_close & attacking[:, None]
            for i in range(h.size):
                s = int(h[i])
                where = np.flatnonzero(rob[i])
                hv = int(where[np.argmin(de[i, where])]) if where.size else -1
                if hv >= 0:
                    self.economy.steal(hv, p.rob_rate * dt)
                    if self.robbing[s] != hv:
                        self._emit({"type": "rob", "time": time, "hornet": int(self.uid[s]),
                                    "hive": hv})
                self.robbing[s] = hv
        else:
            self.robbing[h] = -1

        # ---------------------------------------------------- уход за край карты
        edge = self.world.half_size - p.leave_margin
        gone = self.fleeing[h] & ~dead & (np.abs(hpos[:, :2]).max(axis=1) >= edge)
        for s in h[gone].tolist():
            self._emit({"type": "hornet_left", "time": time, "hornet": int(self.uid[s]),
                        "hp": float(self.hp[s])})
        self.stats["hornets_left"] += int(gone.sum())
        out = h[dead | gone]
        if out.size:
            self._release(out)

    # --------------------------------------------------------------- сенсоры ботов

    def _hornet_sensors(
        self,
        tick: int,
        time: float,
        h: np.ndarray,
        uid: np.ndarray,
        hpos: np.ndarray,
        hvel: np.ndarray,
        a: np.ndarray,
        pos: np.ndarray,
        vel: np.ndarray,
        rain_view: float,
    ) -> list[dict[str, Any]]:
        if h.size == 0:
            return []
        p = self.hp_params
        b = self.bees
        kinds = list(FLYING_KINDS)
        view = p.view_radius * rain_view
        hives = [
            {"team": i, "pos": e} for i, e in enumerate(self.world.hive_entrance.tolist())
        ]
        ground = self.world.ground_height(hpos[:, :2]).tolist()
        if a.size:
            d = pos[None, :, :] - hpos[:, None, :]
            seen = np.einsum("ijk,ijk->ij", d, d) <= view * view
        else:
            d = np.zeros((h.size, 0, 3))
            seen = np.zeros((h.size, 0), dtype=bool)
        bee_uid, bee_kind, bee_hive = b.uid[a].tolist(), b.kind[a].tolist(), b.hive[a].tolist()
        vel_l = vel.tolist()
        out = []
        for i in range(h.size):
            s = int(h[i])
            js = np.flatnonzero(seen[i]).tolist()
            rel = d[i, js].tolist() if js else []
            out.append({
                "tick": tick,
                "time": time,
                "me": {"id": int(uid[i]), "kind": "hornet", "pos": hpos[i].tolist(),
                       "vel": hvel[i].tolist(), "hp": float(self.hp[s]), "hp_max": p.hp,
                       "fleeing": bool(self.fleeing[s])},
                "ground_z": ground[i],
                "bees": [
                    {"id": bee_uid[j], "rel_pos": r, "vel": vel_l[j], "kind": kinds[bee_kind[j]],
                     "team": bee_hive[j]}
                    for j, r in zip(js, rel, strict=True)
                ],
                "hives": hives,
                "map_half_size": self.world.half_size,
            })
        return out

    def _spider_sensors(
        self, tick: int, time: float, a: np.ndarray, pos: np.ndarray, vel: np.ndarray
    ) -> list[dict[str, Any]]:
        if self.spider_flower.size == 0:
            return []
        b = self.bees
        prey_slots, prey_flower = self.prey
        local = {s: j for j, s in enumerate(a.tolist())}
        by_flower: dict[int, list[dict[str, Any]]] = {}
        fpos = self.world.flower_pos
        for s, f in zip(prey_slots.tolist(), prey_flower.tolist(), strict=True):
            j = local.get(s)
            if j is None:
                continue
            by_flower.setdefault(f, []).append({
                "id": int(b.uid[s]), "rel_pos": (pos[j] - fpos[f]).tolist(),
                "vel": vel[j].tolist(), "kind": "forager", "team": int(b.hive[s]),
            })
        return [
            {"tick": tick, "time": time,
             "me": {"id": uid, "kind": "spider", "flower_id": f, "pos": fpos[f].tolist()},
             "prey": by_flower.get(f, [])}
            for uid, f in zip(self.spider_uid.tolist(), self.spider_flower.tolist(), strict=True)
        ]

    # --------------------------------------------------------------- команды ботов

    def _apply(self, reply: CommandBatch, time: float, dt: float) -> None:
        slot_of = {int(u): int(s) for s, u in zip(self.active, self.uid[self.active], strict=True)}
        bites: list[tuple[int, int]] = []
        for uid in sorted(reply.commands):  # фиксированный порядок — детерминизм
            cmd = reply.commands[uid]
            if uid in slot_of:
                self._hornet_move(slot_of[uid], cmd.get("move"))
            elif uid in self._spider_of_uid:
                flower = self._spider_of_uid[uid]
                bites += [(flower, int(v)) for v in cmd.get("bites") or []
                          if isinstance(v, int) and not isinstance(v, bool)]
        if bites:
            self._resolve_bites(bites, time, dt)

    def _hornet_move(self, s: int, move: Any) -> None:
        if not isinstance(move, list) or not move or move[0] not in _HORNET_OPS:
            return
        op, args = move[0], move[1:]
        if len(args) != _HORNET_OPS[op]:
            return
        c, ap = self.control, self.autopilot
        ids = np.array([s])
        if op == "hover":
            c.mode[s] = HOVER
            ap.hover(ids, self.backend.body_state(self.body[ids])[0])
        elif op == "fly_to":
            x, y, z, speed, avoid = args
            c.mode[s] = FLY_TO
            ap.fly_to(ids, np.array([[x, y]], dtype=np.float64),
                      z=None if z is None else np.array([z], dtype=np.float64),
                      speed=None if speed is None else float(speed), avoid=bool(avoid))
        elif op == "fly_dir":
            dvec = np.array(args[:3], dtype=np.float64)
            norm = float(np.linalg.norm(dvec))
            if norm > 0:
                c.mode[s] = FLY_DIR
                c.direction[s] = dvec / norm
                c.speed[s] = np.nan if args[3] is None else float(args[3])
        elif op == "intercept":
            c.mode[s] = INTERCEPT
            c.target[s] = int(args[0])
            c.speed[s] = np.nan

    def _resolve_bites(self, bites: list[tuple[int, int]], time: float, dt: float) -> None:
        """Укусы пауков: только сборщики, которые сейчас собирают на цветке этого паука."""
        b = self.bees
        prey_slots, prey_flower = self.prey
        valid = {
            (int(f), int(b.uid[s])): int(s)
            for s, f in zip(prey_slots.tolist(), prey_flower.tolist(), strict=True)
        }
        bites = sorted(set(bites))
        slots = [valid[k] for k in bites if k in valid]
        flowers = [k[0] for k in bites if k in valid]
        if not slots:
            return
        p_tick = 1.0 - (1.0 - self.sp_params.kill_prob_per_s) ** dt
        roll = self.spider_gen.random(len(slots))
        self.bite_rolls += len(slots)
        self.bite_hazard += p_tick * len(slots)
        dead = [(s, f) for s, f, r in zip(slots, flowers, roll.tolist(), strict=True)
                if r < p_tick]
        if dead:
            self.stats["bees_killed_by_spiders"] += len(dead)
            self._kill_bees(np.array([s for s, _ in dead], dtype=np.int64), "spider")

    # --------------------------------------------------------------- цели и силы

    def refresh_targets(self, find: FindTargets) -> None:
        """Цели автопилота шершней для `fly_dir` и `intercept` (на тике решений)."""
        h = self.active
        if h.size == 0:
            return
        c, ap = self.control, self.autopilot
        pos, _ = self.backend.body_state(self.body[h])
        mode = c.mode[h]
        m = mode == FLY_DIR
        if np.any(m):
            ids = h[m]
            goal = pos[m] + c.direction[ids] * _FLY_DIR_LOOKAHEAD
            ap.fly_to(ids, goal[:, :2], z=goal[:, 2], speed=c.speed[ids])
        m = mode == INTERCEPT
        if np.any(m):
            ids = h[m]
            found, tpos, tvel = find(c.target[ids])
            if np.any(found):
                mine = pos[m][found]
                speed = self.hp_params.cruise_speed
                lead = np.minimum(np.linalg.norm(tpos - mine, axis=1) / speed,
                                  _INTERCEPT_MAX_LEAD_S)
                goal = tpos + tvel * lead[:, None]
                ap.fly_to(ids[found], goal[:, :2], z=goal[:, 2])
            lost = ids[~found]
            if lost.size:
                c.mode[lost] = HOVER
                ap.hover(lost, pos[m][~found])

    def pre_physics(self, gravity: float, rain: bool) -> None:
        """Сопротивление, дождь и тяга автопилота для живых шершней — векторно."""
        h = self.active
        if h.size == 0:
            return
        p = self.hp_params
        ph = self.params.physics
        bodies = self.body[h]
        pos, vel = self.backend.body_state(bodies)
        k = h.size
        radius = np.full(k, p.radius)
        mass = np.full(k, p.mass)
        thrust_max = np.full(k, p.thrust_max)
        drag_coef = np.full(k, self.drag_coef)
        external = np.zeros((k, 3))
        load = mass * gravity
        if rain:
            drag_coef = drag_coef * ph.rain_drag_multiplier
            external += forces.rain_force(radius, ph.rain_force_coef)
            load = load + ph.rain_force_coef * radius**2
        external += forces.drag(vel, self._wind[h], drag_coef)
        cruise = forces.cruise_speed(load, thrust_max, drag_coef)
        thrust = self.autopilot.thrust(
            h, pos, vel,
            mass=mass,
            thrust_max=thrust_max,
            cruise=cruise,
            radius=radius,
            ground=self.world.ground_height(pos[:, :2]),
            ground_ahead=self._ground_ahead[h],
            feedforward=-external,
            obstacles=self._obstacle_local,
        )
        self.backend.set_forces(bodies, thrust + external)

    # --------------------------------------------------------------- для тестов

    def spawn(self, pos: np.ndarray) -> int:
        """Шершень в точке `pos` вне расписания волн (тесты); вернуть его слот."""
        free = np.flatnonzero(~self.alive)
        if free.size == 0:
            raise RuntimeError("Нет свободного слота шершня")
        s = int(free[0])
        at = np.asarray(pos, dtype=np.float64)[None]
        self.alive[s] = True
        self.uid[s] = self.bees.new_uid()
        self.hp[s] = self.hp_params.hp
        self.fleeing[s] = False
        self.victim[s] = -1
        self.contact_s[s] = 0.0
        self.in_ball[s] = False
        self.robbing[s] = -1
        self.control.reset(np.array([s]))
        self.backend.activate(self.body[[s]], at, np.array([self.hp_params.radius]),
                              np.array([self.hp_params.mass]))
        self.autopilot.hover(np.array([s]), at)
        self.active = np.flatnonzero(self.alive)
        self.stats["hornets_spawned"] += 1
        return s
