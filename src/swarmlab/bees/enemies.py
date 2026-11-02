"""Враги (BEES_SPEC §7): пауки — правила мира и встроенная команда ботов.

Шершней и охранников в игре нет (DECISIONS №82). Боты (`bees/bots/`) написаны на
том же API, что и код игроков, и работают как команда без процесса (DECISIONS №36):
на тике решений `Enemies` собирает для них обычный `SensorBatch` (формат записей —
как у протокола раннера), вызывает тот же `HiveHost`, что и раннер, но прямо в
процессе симуляции, и применяет `CommandBatch`.

* **пауки** — укус сборщика, собирающего на цветке паука, убивает с вероятностью
  `1 − (1 − p)^dt` за тик (`p` — `kill_prob_per_s`), кубик — `rng("spiders")`.

Тел у пауков нет: паук — это отметка на цветке (`world.flower_spider`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from swarmlab.bees.bots import bot_classes
from swarmlab.bees.params import BeesParams
from swarmlab.bees.player_host import HiveHost
from swarmlab.bees.state import FREE, BeeState
from swarmlab.bees.world import World
from swarmlab.core.protocol import CommandBatch, SensorBatch
from swarmlab.core.rng import RngRegistry

#: Номер «команды» встроенных ботов врагов.
ENEMY_TEAM = -1

KillBees = Callable[[np.ndarray, str], None]


class Enemies:
    """Пауки и команда ботов врагов."""

    def __init__(
        self,
        params: BeesParams,
        world: World,
        bees: BeeState,
        *,
        rng: RngRegistry,
        kill_bees: KillBees,
        decision_dt: float,
    ) -> None:
        self.params = params
        self.sp_params = sp = params.enemies.spiders
        self.world = world
        self.bees = bees
        self._kill_bees = kill_bees
        self._decision_dt = decision_dt
        self.spider_gen = rng.get("spiders")

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

        #: Ошибки ботов (трассировки) — доверенный код, но падать матчу нельзя.
        self.log: list[str] = []
        self.host = HiveHost(self.log.append)
        self.host.team = ENEMY_TEAM
        self.host.use_classes(bot_classes())
        #: Счётчики событий врагов за матч.
        self.stats = {"bees_killed_by_spiders": 0}

    @property
    def enabled(self) -> bool:
        return self.spider_flower.size > 0

    # --------------------------------------------------------------- тик решений

    def decide(
        self, tick: int, time: float, a: np.ndarray, pos: np.ndarray, vel: np.ndarray
    ) -> None:
        """Боты пауков и их укусы.

        `a, pos, vel` — пчёлы в воздухе до этого тика; погибшие здесь пчёлы
        паркуются через `kill_bees`, модуль пересобирает выборки после вызова.
        """
        if self.spider_flower.size == 0:
            return
        alive = self.bees.state[a] != FREE
        a, pos, vel = a[alive], pos[alive], vel[alive]
        agents = self._spider_sensors(tick, time, a, pos, vel)
        batch = SensorBatch(tick=tick, team=ENEMY_TEAM, budget_ms=0.0, agents=agents)
        self._apply(self.host.step(batch), self._decision_dt)

    def _spider_sensors(
        self, tick: int, time: float, a: np.ndarray, pos: np.ndarray, vel: np.ndarray
    ) -> list[dict[str, Any]]:
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

    def _apply(self, reply: CommandBatch, dt: float) -> None:
        bites: list[tuple[int, int]] = []
        for uid in sorted(reply.commands):  # фиксированный порядок — детерминизм
            flower = self._spider_of_uid.get(uid)
            if flower is None:
                continue
            bites += [(flower, int(v)) for v in reply.commands[uid].get("bites") or []
                      if isinstance(v, int) and not isinstance(v, bool)]
        if bites:
            self._resolve_bites(bites, dt)

    def _resolve_bites(self, bites: list[tuple[int, int]], dt: float) -> None:
        """Укусы пауков: только сборщики, которые сейчас собирают на цветке этого паука."""
        b = self.bees
        prey_slots, prey_flower = self.prey
        valid = {
            (int(f), int(b.uid[s])): int(s)
            for s, f in zip(prey_slots.tolist(), prey_flower.tolist(), strict=True)
        }
        bites = sorted(set(bites))
        slots = [valid[k] for k in bites if k in valid]
        if not slots:
            return
        p_tick = 1.0 - (1.0 - self.sp_params.kill_prob_per_s) ** dt
        roll = self.spider_gen.random(len(slots))
        self.bite_rolls += len(slots)
        self.bite_hazard += p_tick * len(slots)
        dead = [s for s, r in zip(slots, roll.tolist(), strict=True) if r < p_tick]
        if dead:
            self.stats["bees_killed_by_spiders"] += len(dead)
            self._kill_bees(np.array(dead, dtype=np.int64), "spider")
