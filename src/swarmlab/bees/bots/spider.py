"""Бот паука (BEES_SPEC §7.2) — написан так же, как код игрока.

Паук сидит на цветке и кусает каждого сборщика, который на этом цветке собирает
нектар. Смертелен ли укус, решает мир: вероятность гибели за секунду сбора
задаёт матч (`enemies.spiders.kill_prob_per_s`).
"""

from __future__ import annotations

from swarmlab.bees.api import Spider, SpiderSensors


class SpiderBot(Spider):
    def step(self, s: SpiderSensors) -> None:
        for bee in s.prey:
            self.bite(bee)
