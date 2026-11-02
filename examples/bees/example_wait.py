"""Пример с ожиданием: `step()` пишется по шагам, как рецепт (M7a).

Обычный `step()` вызывается 10 раз в секунду, и каждый раз пчела заново решает,
что делать. Если в `step()` есть `yield`, пчела может **ждать**:

    ok = yield self.fly_to(x, y)    # долетела — True, не успела за 60 с — False
    yield wait()                    # подождать один тик
    yield wait(5)                   # подождать 5 секунд

Пока пчела ждёт, она выполняет команду, которую ждёт. Когда `step()` дошёл до
конца, на следующем тике он начнётся сначала.

Процедура с ожиданием — обычная функция с `yield`; вызывается через `yield from`:

    cargo = yield from self.trip(s, flower)

Запуск:  swarmlab run configs/matches/wait.yaml --headless
Смотреть:  swarmlab run configs/matches/wait.yaml --mj-viewer
Лог (print): logs/wait/hive0.log
"""

import math
import random

from swarmlab.bees.api import Forager, Hive, Sensors, wait

#: Не тратить мёд на выведение, пока его меньше — запас на заправку и еду.
HONEY_RESERVE = 24.0


class WaitingForager(Forager):
    """Сборщик по шагам: найти цветок → долететь → набрать → домой (нектар выгрузится сам)."""

    def step(self, s: Sensors):
        me = s.me
        if me.in_hive:
            yield from self.refuel(s)

        flower = s.nearest_flower(min_nectar=0.3)
        if flower is None:
            # Цветов не видно (из улья их не видно никогда) — слетать в случайную точку
            # вокруг улья и посмотреть там. Из улья fly_to сначала выводит наружу.
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(15, 50)
            x = s.home.pos.x + math.cos(angle) * r
            y = s.home.pos.y + math.sin(angle) * r
            yield self.fly_to(x, y)
            return

        cargo = yield from self.trip(s, flower)
        print(f"t={s.time:6.1f} пчела {me.id}: принесла {cargo:.2f} нектара")

    def trip(self, s: Sensors, flower):
        """Процедура: долететь до цветка, набрать нектар, вернуться. Возвращает груз."""
        me_id = s.me.id
        print(f"t={s.time:6.1f} пчела {me_id}: лечу к цветку {flower.id}")
        ok = yield self.fly_to(flower.pos.x, flower.pos.y)
        if not ok:
            print(f"t={s.time:6.1f} пчела {me_id}: не долетела до цветка {flower.id}")
            return 0.0
        print(f"t={s.time:6.1f} пчела {me_id}: над цветком {flower.id}, собираю")
        yield self.collect(flower)
        cargo = s.me.cargo  # после yield в s — свежие сенсоры
        print(f"t={s.time:6.1f} пчела {me_id}: набрала {cargo:.2f}, лечу домой")
        ok = yield self.go_home()
        if not ok:
            print(f"t={s.time:6.1f} пчела {me_id}: не долетела до дома")
            return 0.0
        return cargo

    def refuel(self, s: Sensors):
        """Процедура: дождаться в улье заправки до 90%."""
        while s.me.energy_percent < 90:
            yield wait()


def hive_step(hive: Hive):
    """Улей тоже может ждать: решение о выведении — раз в 20 секунд."""
    if hive.honey > HONEY_RESERVE + hive.costs["forager"]:
        hive.breed("forager")
        print(f"t={hive.time:6.1f} улей: вывожу сборщика (мёд {hive.honey:.1f})")
    yield wait(20)
