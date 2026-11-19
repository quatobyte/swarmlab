"""Обучение (M11): программа, с которой игрок начинает кампанию — пустые программы типов."""

from swarmlab.bees.api import Collector, Hive, Scout


class TScout(Scout):
    def loop(self):
        pass


class TCollector(Collector):
    def loop(self):
        pass


class THive(Hive):
    def loop(self):
        pass
