"""Простой улей: сборщики носят нектар, улей выводит сборщиков.

Разведчики здесь не переопределены — они ведут себя по умолчанию. Домашние пчёлы
работают сами: перерабатывают нектар в мёд и нянчат личинки.
Запуск:  swarmlab run configs/matches/m2_economy.yaml --headless
"""

import math
import random

from swarmlab.bees.api import Forager, Hive, Sensors, Vec

#: Не тратить мёд на выведение, пока его меньше — запас на заправку и еду.
HONEY_RESERVE = 24.0


class BasicForager(Forager):
    """Летит к ближайшему цветку с нектаром; полный — домой; цветов не видно — ищет."""

    def step(self, s: Sensors):
        me = s.me

        # В улье нектар уже выгружен; ждём, пока заправимся.
        if me.in_hive and me.energy_percent <= 80:
            return

        # Полный груз или мало энергии — домой.
        if not me.in_hive and (me.is_full or me.energy_percent < 30):
            self.go_home()
            return

        # Видим цветок с нектаром — собираем.
        flower = s.nearest_flower(min_nectar=0.3)
        if flower is not None:
            self.collect(flower)
            return

        # Цветов не видно — летим в случайную точку вокруг улья (из улья — сразу вылет).
        target = getattr(self, "search", None)
        if target is None or me.pos.dist_xy(target) < 3.0:
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(15, 60)
            target = s.home.pos + Vec(math.cos(angle), math.sin(angle)) * dist
            self.search = target
        self.fly_to(target.x, target.y)


def hive_step(hive: Hive):
    """Выводим сборщиков, пока есть мёд сверх запаса и в очереди пусто."""
    if hive.honey >= HONEY_RESERVE + hive.costs["forager"] and not hive.queue:
        hive.breed("forager")
