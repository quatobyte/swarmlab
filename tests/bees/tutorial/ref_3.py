"""Обучение, эталон миссии 3 (M11): улей выводит сборщика, когда мёда хватает.

Так программу можно собрать из блоков; тест: эта программа проходит миссию 3, а
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
        if self.honey >= 12:
            self.hatch(Collector)
        self.wait(5)
