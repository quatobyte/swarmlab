"""Умный улей: разведка, общая карта полян и пауков, тепловой шар, расчёт мёда.

Как он устроен (BEES_SPEC §11):

* **Разведчики** разлетаются веером, у найденной поляны облетают её низко
  (паука видно только ближе 4 м), потом летят к летку и рассказывают:
  где поляна и на каких цветах пауки.
* **Улей** собирает рассказы в память (`hive.memory`) — это «карта» улья — и
  пересказывает её каждой пчеле, которая вылетает: по очереди поляны и пауков.
* **Сборщики** помнят карту, выбирают цветок «побольше нектара, поближе»,
  обходят цветы с пауками, а увидев шершня — летят домой, к охране.
* **Охранники** держатся позади улья, не загораживая леток (шершень не может
  грабить, пока они рядом), и бросаются на шершня только втроём и больше —
  тепловой шар.
* **Домашние пчёлы** перерабатывают нектар и нянчат личинок.
* **Улей** выводит пчёл, пока это окупается, и держит охрану.

Сообщения (до 8 чисел):
    (FIELD, x, y, нектар)              — поляна
    (SPIDER, x1, y1, x2, y2, x3, y3)   — до трёх цветов с пауками
"""

import math

from swarmlab.bees.api import (
    HIVE_ID,
    Forager,
    Guard,
    Hive,
    HouseBee,
    HouseSensors,
    Scout,
    Sensors,
    Vec,
)

FIELD, SPIDER = 1.0, 2.0

#: Цветок ближе этого к пауку из карты — считаем паучьим, м.
SPIDER_RADIUS = 0.5
#: Две поляны ближе этого — одна и та же, м.
SAME_FIELD = 12.0
#: Мёд, который улей не тратит на выведение: запас на заправку.
HONEY_RESERVE = 16.0
#: После этой секунды матча новые пчёлы уже не успеют окупиться.
BREED_UNTIL_S = 150.0
#: Сколько охранников держать.
GUARDS_WANTED = 5
#: Охранники атакуют, когда рядом столько своих охранников (вместе со мной).
BALL_SIZE = 3


def _golden_angle(n: int) -> float:
    """Угол для n-й пчелы — так разные пчёлы смотрят в разные стороны."""
    return (n * 2.399963) % (2 * math.pi)


def _read_map(messages, fields: list, spiders: list) -> None:
    """Дописать в карту поляны и пауков из сообщений."""
    for m in messages:
        v = m.values
        if len(v) >= 4 and v[0] == FIELD:
            _add_field(fields, v[1], v[2], v[3])
        elif len(v) >= 3 and v[0] == SPIDER:
            for i in range(1, len(v) - 1, 2):
                _add_spider(spiders, v[i], v[i + 1])


def _add_field(fields: list, x: float, y: float, nectar: float) -> None:
    for f in fields:
        if math.hypot(f[0] - x, f[1] - y) < SAME_FIELD:
            f[2] = nectar  # свежая оценка нектара
            return
    fields.append([x, y, nectar])


def _add_spider(spiders: list, x: float, y: float) -> None:
    for sx, sy in spiders:
        if math.hypot(sx - x, sy - y) < SPIDER_RADIUS:
            return
    spiders.append((x, y))


def _is_spider(spiders: list, pos: Vec) -> bool:
    return any(math.hypot(sx - pos.x, sy - pos.y) < SPIDER_RADIUS for sx, sy in spiders)


# ===================================================================== разведчик


class SmartScout(Scout):
    """Ищет поляны, облетает их низко, ищет пауков и несёт новости домой."""

    def __init__(self):
        self.fields = []  # [x, y, нектар] — найденные мной поляны
        self.spiders = []  # (x, y) — замеченные мной пауки
        self.plan = []  # точки облёта поляны
        self.news = False  # есть что рассказать улью
        self.trip = 0  # номер вылета — каждый раз в новую сторону

    def step(self, s: Sensors):
        me = s.me
        if me.in_hive:
            if me.energy_percent > 90:
                self.trip += 1
                self.leave_hive()
            return

        # Всё, что вижу: пауков — на карту.
        for f in s.flowers:
            if f.spider:
                if not _is_spider(self.spiders, f.pos):
                    self.news = True
                _add_spider(self.spiders, f.pos.x, f.pos.y)

        if me.energy_percent < 35:
            self._go_report(s)
            return

        # Новая поляна — облететь её низко, чтобы увидеть пауков.
        rich = [f for f in s.flowers if f.nectar > 0.3]
        if rich and not self.plan:
            cx = sum(f.pos.x for f in rich) / len(rich)
            cy = sum(f.pos.y for f in rich) / len(rich)
            if not any(math.hypot(f[0] - cx, f[1] - cy) < SAME_FIELD for f in self.fields):
                self.fields.append([cx, cy, sum(f.nectar for f in rich)])
                self.news = True
                self.plan = [Vec(cx + 3 * math.cos(a), cy + 3 * math.sin(a))
                             for a in (0.0, 1.6, 3.1, 4.7)]
        if self.plan:
            p = self.plan[0]
            if me.pos.dist_xy(p) < 1.5:
                self.plan.pop(0)
                if not self.plan:
                    self._go_report(s)
                    return
            self.fly_to(p.x, p.y, s.ground_z + 3.0)  # низко: пауки видны ближе 4 м
            return

        # С новостями — к летку.
        if self.news:
            self._go_report(s)
            return

        # Разведка: веер направлений, каждый вылет — дальше и в новую сторону.
        angle = _golden_angle(me.id * 3 + self.trip)
        reach = 30.0 + 25.0 * (self.trip % 4)
        target = s.home.pos + Vec(math.cos(angle), math.sin(angle)) * reach
        if me.pos.dist_xy(target) < 4.0:
            self.trip += 1
        self.fly_to(target.x, target.y)

    def _go_report(self, s: Sensors):
        """Лететь домой и по дороге рассказывать (слышат все свои в 15 м)."""
        tick = s.tick
        if self.spiders and tick % 2:
            k = (tick // 2) % ((len(self.spiders) + 2) // 3)
            chunk = self.spiders[3 * k: 3 * k + 3]
            self.signal(SPIDER, *[c for xy in chunk for c in xy])
        elif self.fields:
            f = self.fields[(tick // 2) % len(self.fields)]
            self.signal(FIELD, f[0], f[1], f[2])
        if s.home.dist < 10.0:
            self.news = False
        self.go_home()


# ===================================================================== сборщик


class SmartForager(Forager):
    """Собирает с выгодных цветов, обходит пауков, от шершня — к охране."""

    def __init__(self):
        self.fields = []  # карта полян, которую рассказал улей
        self.spiders = []  # пауки из карты
        self.empty = {}  # поляна (номер в fields) → до какого времени не лететь
        self.target = None  # поляна, куда лечу

    def step(self, s: Sensors):
        me = s.me
        _read_map(s.messages, self.fields, self.spiders)
        if me.in_hive:
            if me.cargo > 0:
                self.unload()
            elif me.energy_percent > 70:
                self.leave_hive()
            return

        # Шершень рядом — домой, к охранникам.
        enemy = s.nearest_enemy()
        if me.is_full or me.energy_percent < 30 or (enemy is not None and enemy.dist < 8):
            self.go_home()
            return

        # Цветок: побольше нектара, поближе, без паука.
        room = me.cargo_max - me.cargo
        good = [f for f in s.flowers
                if f.nectar >= 0.4 and not f.spider and not _is_spider(self.spiders, f.pos)]
        if good:
            best = max(good, key=lambda f: min(f.nectar, room) / (f.dist + 4.0))
            self.collect(best)
            return

        # Цветов не видно — на лучшую поляну из карты.
        if self.target is not None and me.pos.dist_xy(self.target[1]) < 4.0:
            self.empty[self.target[0]] = s.time + 60.0  # пусто — минуту не возвращаться
            self.target = None
        if self.target is None:
            self.target = self._choose_field(s)
        if self.target is not None:
            p = self.target[1]
            self.fly_to(p.x, p.y)
            return

        # Карты ещё нет — ищем сами вокруг улья.
        angle = _golden_angle(me.id + int(s.time // 20))
        p = s.home.pos + Vec(math.cos(angle), math.sin(angle)) * 45.0
        self.fly_to(p.x, p.y)

    def _choose_field(self, s: Sensors):
        options = []
        for i, (x, y, nectar) in enumerate(self.fields):
            if self.empty.get(i, 0.0) > s.time:
                continue
            p = Vec(x, y)
            options.append(((nectar + 3.0) / (s.home.pos.dist_xy(p) + 20.0), i, p))
        if not options:
            return None
        options.sort(reverse=True)
        # Не все на одну поляну: чётные — на лучшую, нечётные — на вторую.
        _, i, p = options[min(s.me.id % 2, len(options) - 1)]
        return (i, p)


# ===================================================================== охранник


class SmartGuard(Guard):
    """Кольцо у летка; на шершня — только тепловым шаром (3 охранника и больше)."""

    def step(self, s: Sensors):
        me = s.me
        if me.in_hive:
            if me.energy_percent > 90:
                self.leave_hive()
            return
        if me.energy_percent < 35:
            self.go_home()
            return

        enemy = s.nearest_enemy()
        if enemy is not None and enemy.pos.dist_xy(s.home.pos) < 30.0:
            guards = 1 + sum(1 for b in s.bees if b.friend and b.kind == "guard" and b.dist < 10)
            if guards >= BALL_SIZE:
                self.intercept(enemy)
                return

        # Своё место на дуге позади улья: леток смотрит на +x, вход не загораживаем,
        # но шершень у летка окажется рядом с охраной.
        angle = math.pi / 2 + (_golden_angle(me.id) % math.pi)
        center = s.home.pos - Vec(2.5, 0.0)
        p = center + Vec(math.cos(angle), math.sin(angle)) * 3.5
        self.fly_to(p.x, p.y, s.home.pos.z + 3.0)


# ===================================================================== домашние


class SmartHouse(HouseBee):
    """Двое нянчат личинок, если они есть; остальные перерабатывают нектар."""

    def step(self, s: HouseSensors):
        index = s.me.id % max(1, s.counts.house)
        if s.breeding_queue and index < 2:
            self.nurse()
        elif s.hive_nectar > 0.05:
            self.process()
        elif s.breeding_queue:
            self.nurse()
        else:
            self.rest()


# ===================================================================== улей


def hive_step(hive: Hive):
    """Карта полян и пауков, пересказ вылетающим, выведение с расчётом."""
    fields = hive.memory.setdefault("fields", [])
    spiders = hive.memory.setdefault("spiders", [])
    _read_map((m for m in hive.messages if m.from_id != HIVE_ID), fields, spiders)

    # Пересказ: через тик — поляны (лучшие чаще) и пауки (по три).
    if hive.tick % 2 == 0 and fields:
        ranked = sorted(fields, key=lambda f: -f[2])
        f = ranked[(hive.tick // 2) % len(ranked)]
        hive.signal(FIELD, f[0], f[1], f[2])
    elif spiders:
        k = (hive.tick // 2) % ((len(spiders) + 2) // 3)
        chunk = spiders[3 * k: 3 * k + 3]
        hive.signal(SPIDER, *[c for xy in chunk for c in xy])

    # Выведение.
    if hive.queue:
        return
    c = hive.counts
    if c.guard < GUARDS_WANTED:
        kind = "guard"  # охрану восполняем всегда
    elif hive.time > BREED_UNTIL_S:
        return  # поздно: пчела не успеет принести больше, чем стоит
    elif c.house < 6 + c.forager // 4:
        kind = "house"
    else:
        kind = "forager"
    if hive.honey >= HONEY_RESERVE + hive.costs[kind]:
        hive.breed(kind)
