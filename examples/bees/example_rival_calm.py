"""Соперник обучения, миссия 6 «Первый соперник» (M11, DECISIONS №100).

Осторожный рой: разведчик подлетает к найденному цветку, проверяет пауков и зовёт сборщиков
только к цветку без паука; сборщики садятся на названный цветок. Улей держит двух
разведчиков и выводит сборщика, когда мёда не меньше 10.
"""

from swarmlab.bees.api import Collector, Hive, Scout


class RivalScout(Scout):
    def loop(self):
        flower = self.explore()
        if flower is not None:
            self.fly_to(flower)
            best = None
            for f in self.flowers:
                if f.spider is False and f.nectar >= 0.3:
                    if best is None or f.nectar > best.nectar:
                        best = f
            if best is not None:
                self.go_home()
                self.say("flowers", best)


class RivalCollector(Collector):
    def loop(self):
        spot = None
        for m in self.heard:
            if m.word == "flowers":
                spot = m.where
        while spot is not None:
            self.fly_to(spot)
            target = None
            for f in self.flowers:
                if f.nectar >= 0.3 and f.pos.distance(spot) < 0.5:
                    target = f
            if target is None:
                spot = None
            else:
                self.collect(target)
                self.go_home()
                for m in self.heard:
                    if m.word == "flowers":
                        spot = m.where
        self.wait(2)


class RivalHive(Hive):
    def loop(self):
        if self.count(Scout) < 2 and self.honey >= 4:
            self.hatch(Scout)
        if self.honey >= 10:
            self.hatch(Collector)
        self.wait(5)
