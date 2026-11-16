"""Обучение, эталон миссии 1 (M11): сборщик ищет, собирает, летит домой.

Так программу можно собрать из блоков; тест: эта программа проходит миссию 1, а
программа прошлой миссии — нет (tests/bees/test_tutorial.py)."""

from swarmlab.bees.api import Collector, Hive, Scout


class TScout(Scout):
    def loop(self):
        self.wait(1)


class TCollector(Collector):
    def loop(self):
        flower = self.explore()
        if flower is not None:
            self.collect(flower)
        self.go_home()


class THive(Hive):
    def loop(self):
        self.wait(1)

