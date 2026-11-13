"""Простой улей: разведчики ищут цветы и рассказывают, сборщики летят собирать.

Как он устроен:

* **Разведчик** ищет цветы. Нашёл — летит домой и говорит «flowers» с местом.
* **Сборщик** слушает. Услышал про цветы — летит туда собирать, иначе ищет сам.
  Полный — домой (нектар выгрузится сам).
* **Улей** выводит сборщиков, пока есть мёд сверх запаса.
* Домашние пчёлы работают сами: делают мёд из нектара и растят личинки.
* Когда энергии мало, пчела сама летит домой и заправляется (порог задаёт улей).

Запуск:  swarmlab run configs/matches/m2_economy.yaml --headless
"""

from swarmlab.bees.api import Collector, Hive, Scout

#: Не тратить мёд на выведение, пока его меньше — запас на заправку и еду.
HONEY_RESERVE = 24.0


class BasicScout(Scout):
    """Ищет цветы; нашёл — летит домой и рассказывает, где они."""

    def loop(self):
        flower = self.explore()
        if flower:
            self.go_home()
            self.say("flowers", flower)


class BasicCollector(Collector):
    """Собирает там, где нашли цветы разведчики; полный — домой."""

    def loop(self):
        news = [m for m in self.heard if m.word == "flowers"]
        if news:
            self.collect(news[-1])  # долететь к месту и собрать с ближайшего цветка
        else:
            flower = self.nearest_flower(min_nectar=0.3) or self.explore()
            if flower:
                self.collect(flower)
        if self.is_full:
            self.go_home()


class BasicHive(Hive):
    """Выводит сборщиков, пока мёда больше запаса."""

    def loop(self):
        if self.honey >= HONEY_RESERVE:
            self.hatch(Collector)
        self.wait(5)
