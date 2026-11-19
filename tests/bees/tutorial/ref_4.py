"""Обучение, эталон миссии 4 (M11): улей держит трёх разведчиков.

Так программу можно собрать из блоков; тест: эта программа проходит миссию 4, а
программа прошлой миссии — нет (tests/bees/test_tutorial.py)."""

from swarmlab.bees.api import Collector, Hive, Scout


class TScout(Scout):
    def loop(self):
        flower = self.explore()
        if flower is not None:
            self.go_home()
            self.say("flowers", flower)


class TCollector(Collector):
    def loop(self):
        news = None
        for m in self.heard:
            if m.word == "flowers":
                news = m
        if news is not None:
            self.collect(news)
        else:
            flower = self.explore()
            if flower is not None:
                self.collect(flower)
        self.go_home()


class THive(Hive):
    def loop(self):
        if self.count(Scout) < 3 and self.honey >= 4:
            self.hatch(Scout)
        if self.honey >= 12:
            self.hatch(Collector)
        self.wait(5)
