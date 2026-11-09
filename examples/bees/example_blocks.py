# Сгенерировано из блоков (example_blocks.blocks.json). Не правьте этот файл вручную:
# пока скрипт в режиме «Блоки», редактор перезаписывает его при каждом сохранении.
# Чтобы писать на Python, нажмите в редакторе «Перейти на Python».

from swarmlab.bees.api import Collector, Hive, Scout


def домой_с_нектаром(self):  # block:def_trip
    print("набрала нектара: " + str(self.nectar))  # block:print_cargo
    self.go_home()  # block:go_home


class MyScout(Scout):  # block:prog_scout
    def loop(self):  # block:prog_scout
        цветок = self.explore()  # block:scout_find
        if цветок is not None:  # block:scout_found
            self.go_home()  # block:scout_home
            self.say("flowers", цветок)  # block:scout_say


class MyCollector(Collector):  # block:prog_collector
    def loop(self):  # block:prog_collector
        новость = None  # block:news_none
        for m in self.heard:  # block:listen
            if m.word == "flowers":  # block:is_flowers
                новость = m  # block:news_set
        if новость is not None:  # block:has_news
            self.collect(новость)  # block:collect_news
        else:  # block:has_news
            цветок = self.nearest_flower(0.3)  # block:set_flower
            if цветок is None:  # block:no_flower
                цветок = self.explore()  # block:explore_set
            if цветок is not None:  # block:flower_seen
                self.collect(цветок)  # block:collect_flower
        if self.is_full:  # block:if_full
            домой_с_нектаром(self)  # block:call_trip


class MyHive(Hive):  # block:prog_hive
    def loop(self):  # block:prog_hive
        if self.honey > 24:  # block:enough_honey
            self.hatch(Collector)  # block:hatch
        self.wait(5)  # block:hive_wait
