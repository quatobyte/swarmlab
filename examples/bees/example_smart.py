"""Умный улей: разведка, пауки, дележ полян и расчёт мёда.

Как он устроен (BEES_SPEC §11):

* **Разведчики** ищут цветы. Нашли — подлетают ближе (паука видно только
  ближе 4 м), летят домой и рассказывают: «flowers» — где поляна,
  «spider» — где паук.
* **Улей** запоминает поляны и раз в несколько секунд повторяет их у летка —
  так новость слышат и пчёлы, которые вернутся позже.
* **Сборщики** запоминают пауков, выбирают цветок «побольше нектара, поближе,
  без паука», делят поляны (чётные и нечётные — на разные).
* **Улей** выводит пчёл, пока это окупается, и решает, когда пчёлам
  возвращаться: в начале рискуем, к концу бережём энергию.
* Домашние пчёлы (`Worker`) работают сами: делают мёд и растят личинки.
"""

from swarmlab.bees.api import Collector, Hive, Scout, Worker

#: Цветок ближе этого к пауку — считаем паучьим, м.
SPIDER_RADIUS = 0.5
#: Две поляны ближе этого — одна и та же, м.
SAME_FIELD = 12.0
#: Мёд, который улей не тратит на выведение: запас на заправку.
HONEY_RESERVE = 16.0
#: После этой секунды матча новые пчёлы уже не успеют окупиться.
HATCH_UNTIL_S = 150.0


def near_any(points, place, radius):
    """Есть ли среди точек `points` такая, что ближе `radius` к `place`."""
    return any(p.distance(place) < radius for p in points)


# ===================================================================== разведчик


class SmartScout(Scout):
    """Ищет поляны, высматривает пауков и несёт новости домой."""

    def loop(self):
        flower = self.explore()
        if flower is None:
            return
        self.fly_to(flower)  # ближе — чтобы увидеть пауков на соседних цветках
        spiders = [f.pos for f in self.flowers if f.spider]
        self.go_home()
        self.say("flowers", flower)
        for spider in spiders[:3]:
            self.say("spider", spider)


# ===================================================================== сборщик


class SmartCollector(Collector):
    """Собирает с выгодных цветов, обходит пауков, делит поляны."""

    def __init__(self):
        self.spiders = []  # где пауки (точки)
        self.fields = []  # поляны, про которые рассказали
        self.empty = {}  # номер поляны → до какого времени туда не лететь

    def listen(self):
        """Дописать в память то, что услышала."""
        for m in self.heard:
            if m.where is None:
                continue
            if m.word == "spider" and not near_any(self.spiders, m.where, SPIDER_RADIUS):
                self.spiders.append(m.where)
            elif m.word == "flowers" and not near_any(self.fields, m.where, SAME_FIELD):
                self.fields.append(m.where)

    def best_flower(self):
        """Цветок побольше нектара и поближе, без паука; `None` — такого не видно."""
        good = [f for f in self.flowers
                if f.nectar >= 0.4 and not f.spider
                and not near_any(self.spiders, f.pos, SPIDER_RADIUS)]
        if not good:
            return None
        return max(good, key=lambda f: f.nectar / (f.distance + 4.0))

    def choose_field(self):
        """Поляна, куда лететь: не пустая, поближе; пчёлы делятся по размеру бака."""
        options = [(i, p) for i, p in enumerate(self.fields)
                   if self.empty.get(i, 0.0) <= self.time]
        if not options:
            return None
        options.sort(key=lambda o: self.home.distance(o[1]))
        # Баки у всех разные: «чётный» бак — на ближнюю поляну, «нечётный» — на вторую.
        return options[int(self.max_energy) % 2 % len(options)]

    def loop(self):
        self.listen()
        if self.is_full:
            self.go_home()
            return
        flower = self.best_flower()
        if flower:
            self.collect(flower)
            return
        field = self.choose_field()
        if field is None:
            self.explore()  # карты ещё нет — ищем сами
            return
        i, place = field
        if self.search(place) is None:
            self.empty[i] = self.time + 60.0  # пусто — минуту не возвращаться


# ===================================================================== улей


class SmartHive(Hive):
    """Пересказ полян, выведение с расчётом, порог возврата по времени матча."""

    def __init__(self):
        self.fields = []
        self.turn = 0

    def loop(self):
        spiders = []
        for m in self.heard:
            if m.where is None:
                continue
            if m.word == "flowers" and not near_any(self.fields, m.where, SAME_FIELD):
                self.fields.append(m.where)
            elif m.word == "spider" and not near_any(spiders, m.where, SPIDER_RADIUS):
                spiders.append(m.where)
        for spider in spiders[:3]:  # передать дальше тем, кто дома (за тик — до 4 сообщений)
            self.say("spider", spider)

        # Пересказ: по очереди каждую поляну.
        if self.fields:
            self.say("flowers", self.fields[self.turn % len(self.fields)])
            self.turn += 1

        # Энергия: в начале рискуем, к концу бережём пчёл.
        self.set_home_energy(25 if self.time < 120 else 40)

        # Выведение: домашних — по числу сборщиков, остальное — сборщики.
        if self.time < HATCH_UNTIL_S:
            kind = Worker if self.count(Worker) < 6 + self.count(Collector) // 4 else Collector
            if self.honey >= HONEY_RESERVE + 4:
                self.hatch(kind)
        self.wait(2)
