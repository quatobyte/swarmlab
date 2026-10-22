"""Бот шершня (BEES_SPEC §7.1) — написан так же, как код игрока.

* Здоровья мало (`s.me.fleeing`) — улетает к ближайшему краю карты.
* Иначе ищет добычу: ближайшую видимую пчелу, у которой рядом не больше
  `max_allies` союзников (одиночку проще поймать), и преследует её.
* Добычи не видно — летит к «своему» улью и висит у летка: если охранников
  рядом нет, шершень грабит мёд (это правило мира, команда не нужна).
"""

from __future__ import annotations

from swarmlab.bees.api import BeeInfo, Hornet, HornetSensors

#: Цель бегства — на столько метров за краем карты (автопилот всё равно не выпустит).
_EDGE_BEYOND = 10.0
#: Множитель для выбора улья по номеру шершня: шершни разлетаются по разным ульям.
_HIVE_MIX = 7919


class HornetBot(Hornet):
    #: Добыча — пчела, у которой рядом не больше стольких союзников.
    max_allies: int = 1
    #: … в этом радиусе, м.
    ally_radius: float = 3.0

    def step(self, s: HornetSensors) -> None:
        me = s.me
        if me.fleeing:
            self._flee(s)
            return
        prey = self._prey(s.bees)
        if prey is not None:
            self.intercept(prey)
            return
        if not s.hives:
            self.hover()
            return
        hive = s.hives[(me.id * _HIVE_MIX) % len(s.hives)]
        self.fly_to(hive.pos.x, hive.pos.y, hive.pos.z)

    def _prey(self, bees: list[BeeInfo]) -> BeeInfo | None:
        """Ближайшая пчела, у которой не больше `max_allies` союзников в `ally_radius`."""
        for b in bees:  # уже отсортированы по расстоянию
            allies = sum(
                1
                for o in bees
                if o is not b and o.team == b.team and o.pos.dist(b.pos) <= self.ally_radius
            )
            if allies <= self.max_allies:
                return b
        return None

    def _flee(self, s: HornetSensors) -> None:
        x, y = s.me.pos.x, s.me.pos.y
        edge = s.map_half_size + _EDGE_BEYOND
        if abs(x) >= abs(y):
            x = edge if x >= 0 else -edge
        else:
            y = edge if y >= 0 else -edge
        self.fly_to(x, y)
