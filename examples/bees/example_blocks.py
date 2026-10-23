# Сгенерировано из блоков (example_blocks.blocks.json). Не правьте этот файл вручную:
# пока скрипт в режиме «Блоки», редактор перезаписывает его при каждом сохранении.
# Чтобы писать на Python, нажмите в редакторе «Перейти на Python».

import random

from swarmlab.bees.api import Forager, HouseBee, wait


def рейс(self, s, цветок):  # block:def_trip
    yield self.fly_to(цветок.pos.x, цветок.pos.y)  # block:fly_to_flower
    yield self.collect(цветок)  # block:collect
    print("набрала нектара: " + str(s.me.cargo))  # block:print_cargo
    yield self.go_home()  # block:go_home


def отдых_дома(self, s):  # block:def_rest
    if s.me.cargo > 0:  # block:if_cargo
        yield self.unload()  # block:unload
    while s.me.energy_percent < 90:  # block:while_refuel
        yield wait()  # block:wait_tick
    yield self.leave_hive()  # block:leave_hive


class MyForager(Forager):  # block:prog_forager
    def step(self, s):  # block:prog_forager
        if s.me.in_hive:  # block:if_in_hive
            yield from отдых_дома(self, s)  # block:call_rest
        else:  # block:if_in_hive
            цветок = s.nearest_flower(min_nectar=0.3)  # block:set_flower
            if цветок is not None:  # block:if_flower
                yield from рейс(self, s, цветок)  # block:call_trip
            else:  # block:if_flower
                yield self.fly_to(s.home.pos.x + random.randint(-40, 40), s.home.pos.y + random.randint(-40, 40))  # block:fly_search


class MyHouse(HouseBee):  # block:prog_house
    def step(self, s):  # block:prog_house
        if s.hive_nectar > 0.05:  # block:if_house
            self.process()  # block:process
        elif len(s.breeding_queue) > 0:  # block:if_house
            self.nurse()  # block:nurse
        else:  # block:if_house
            self.rest()  # block:rest


def hive_step(hive):  # block:prog_hive
    if hive.honey > 24 + hive.costs.get("forager"):  # block:if_honey
        hive.breed("forager")  # block:breed_forager
    yield wait(20)  # block:hive_wait
