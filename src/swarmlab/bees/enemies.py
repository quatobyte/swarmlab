"""Враги (BEES_SPEC §7): пауки — правило мира.

Шершней и охранников в игре нет (DECISIONS №82). Паук — отметка на цветке
(`world.flower_spider`), тела и кода у него нет (DECISIONS №89, заменяет
ботов №36): он кусает каждого сборщика, который сейчас собирает нектар на его
цветке; укус убивает с вероятностью `1 − (1 − p)^dt` за тик (`p` —
`kill_prob_per_s`), кубик — `rng("spiders")`, броски — по порядку слотов.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from swarmlab.bees.params import BeesParams
from swarmlab.bees.state import FREE, BeeState
from swarmlab.bees.world import World
from swarmlab.core.rng import RngRegistry

KillBees = Callable[[np.ndarray, str], None]


class Enemies:
    """Пауки: на каких цветках сидят и кого кусают."""

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

        #: Счётчики событий врагов за матч.
        self.stats = {"bees_killed_by_spiders": 0}

    @property
    def enabled(self) -> bool:
        return self.spider_flower.size > 0

    # --------------------------------------------------------------- тик решений

    def decide(self) -> None:
        """Укусы пауков на тике решений.

        Добыча (`prey`) — сборщики, собиравшие на цветках с пауком за прошлый тик;
        погибшие паркуются через `kill_bees`, модуль пересобирает выборки после вызова.
        """
        if self.spider_flower.size == 0:
            return
        slots = self.prey[0]
        slots = slots[self.bees.state[slots] != FREE]
        if slots.size:
            self._resolve_bites(slots, self._decision_dt)

    def _resolve_bites(self, slots: np.ndarray, dt: float) -> None:
        """Укусы сборщиков, которые собирают на цветке с пауком (по порядку слотов)."""
        slots = np.sort(slots)
        p_tick = 1.0 - (1.0 - self.sp_params.kill_prob_per_s) ** dt
        roll = self.spider_gen.random(slots.size)
        self.bite_rolls += int(slots.size)
        self.bite_hazard += p_tick * int(slots.size)
        dead = slots[roll < p_tick]
        if dead.size:
            self.stats["bees_killed_by_spiders"] += int(dead.size)
            self._kill_bees(dead.astype(np.int64), "spider")
