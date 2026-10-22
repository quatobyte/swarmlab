"""Экономика улья (BEES_SPEC §4): склад, переработка, питание, выведение.

Чистая логика на массивах по ульям, без физики: модуль вызывает её на тике
решений с `dt` тика. Главный инвариант — **мёд не появляется сам по себе**:
единственный источник мёда — переработка нектара (`honey_per_nectar` за единицу),
плюс возврат цены отменённой личинки (ранее списанного мёда). Поэтому в любой
момент `honey ≤ start_honey + honey_per_nectar · processed_total`.

Домашние пчёлы (`house`) не имеют тела и живут только здесь: у каждой задача
`rest` / `process` / `nurse`. Потребление мёда домашними идёт первым; если мёда
не хватает — домашние на этом тике не работают (ни переработки, ни ухода за
личинками, §4.4).

Выведение — очередь: растёт одна личинка (голова очереди), скорость роста
`√max(1, n_nurse)` базовых секунд в секунду (§4.5). Цена списывается сразу при
постановке в очередь; отмена возвращает цену последней личинки этого типа.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swarmlab.bees.params import BEE_KINDS, BeeKind, EconomyParams

#: Задачи домашней пчелы.
REST, PROCESS, NURSE = 0, 1, 2
HOUSE_TASKS = ("rest", "process", "nurse")


@dataclass
class Larva:
    """Личинка в очереди выведения."""

    kind: BeeKind
    left_s: float  # базовых секунд до рождения
    cost: float  # списанный мёд (для возврата при отмене)


@dataclass(frozen=True)
class Birth:
    hive: int
    kind: BeeKind


class HiveEconomy:
    """Склады, домашние пчёлы и очереди выведения всех ульев."""

    def __init__(self, n_hives: int, params: EconomyParams, max_bees: int) -> None:
        self.params = params
        self.n_hives = n_hives
        self.max_bees = max_bees
        self.honey = np.full(n_hives, params.start_honey, dtype=np.float64)
        self.nectar = np.full(n_hives, params.start_nectar, dtype=np.float64)
        self.start_honey = self.honey.copy()
        #: Счётчики за матч, по ульям.
        self.delivered = np.zeros(n_hives)  # принесено нектара
        self.processed = np.zeros(n_hives)  # переработано нектара
        self.honey_made = np.zeros(n_hives)  # получено мёда переработкой
        self.spent_breeding = np.zeros(n_hives)
        self.spent_feeding = np.zeros(n_hives)  # заправка летающих
        self.spent_house = np.zeros(n_hives)  # питание домашних
        self.refunded = np.zeros(n_hives)
        self.stolen = np.zeros(n_hives)  # украдено шершнями
        self.working = np.ones(n_hives, dtype=bool)  # домашние работали на последнем тике

        # Домашние пчёлы — SoA по слотам (как пул тел, но без тел).
        n = n_hives * max_bees
        self.house_alive = np.zeros(n, dtype=bool)
        self.house_uid = np.full(n, -1, dtype=np.int64)
        self.house_hive = np.repeat(np.arange(n_hives, dtype=np.int64), max_bees)
        self.house_task = np.zeros(n, dtype=np.int64)

        self.queue: list[list[Larva]] = [[] for _ in range(n_hives)]

    # --------------------------------------------------------------- формулы §4

    def process_rate(self, n_process: np.ndarray | int) -> np.ndarray:
        """Скорость переработки, ед. нектара/с: `k_proc · √n` (убывающая отдача)."""
        return self.params.processing.k_proc * np.sqrt(np.asarray(n_process, dtype=np.float64))

    @staticmethod
    def nurse_speedup(n_nurse: np.ndarray | int) -> np.ndarray:
        """Во сколько раз быстрее растёт личинка: `√max(1, n_nurse)`."""
        return np.sqrt(np.maximum(1.0, np.asarray(n_nurse, dtype=np.float64)))

    def breeding_time(self, kind: BeeKind, n_nurse: int) -> float:
        """Время выведения, с: базовое / `√max(1, n_nurse)`."""
        base = self.params.breeding[kind].time_s
        return float(base / self.nurse_speedup(n_nurse))

    # --------------------------------------------------------------- домашние пчёлы

    def add_house(self, hive: int, uid: int) -> int:
        """Домашняя пчела родилась; вернуть её слот."""
        sl = self._hive_slice(hive)
        free = np.flatnonzero(~self.house_alive[sl])
        if free.size == 0:
            raise RuntimeError(f"В улье {hive} нет места для домашней пчелы")
        s = sl.start + int(free[0])
        self.house_alive[s] = True
        self.house_uid[s] = uid
        self.house_task[s] = REST
        return s

    def house_slots(self, hive: int) -> np.ndarray:
        sl = self._hive_slice(hive)
        return sl.start + np.flatnonzero(self.house_alive[sl])

    def house_count(self, hive: int, task: int | None = None) -> int:
        slots = self.house_slots(hive)
        if task is None:
            return int(slots.size)
        return int(np.count_nonzero(self.house_task[slots] == task))

    def set_task(self, slots: np.ndarray, task: int) -> None:
        self.house_task[slots] = task

    def _hive_slice(self, hive: int) -> slice:
        return slice(hive * self.max_bees, (hive + 1) * self.max_bees)

    # --------------------------------------------------------------- склад

    def deliver(self, hive: int, amount: float) -> None:
        """Сборщик выгрузил нектар."""
        if amount < 0:
            raise ValueError("Нектар не может быть отрицательным")
        self.nectar[hive] += amount
        self.delivered[hive] += amount

    def refuel(self, hive: np.ndarray, need_j: np.ndarray, dt: float) -> np.ndarray:
        """Заправка летающих пчёл в улье: вернуть выданную энергию, Дж `(K,)`.

        Каждая пчела получает до `refuel_rate · dt`, но не больше недостающего.
        Если мёда на всех не хватает, все пчёлы улья получают одну и ту же долю.
        """
        f = self.params.feeding
        hive = np.asarray(hive, dtype=np.int64)
        want = np.minimum(np.maximum(need_j, 0.0), f.refuel_rate * dt)
        if want.size == 0:
            return want
        cost = np.bincount(hive, weights=want, minlength=self.n_hives) / f.joules_per_honey
        scale = np.ones(self.n_hives)
        short = cost > self.honey
        scale[short] = self.honey[short] / cost[short]
        given = want * scale[hive]
        spent = np.minimum(cost * scale, self.honey)
        self.honey -= spent
        self.spent_feeding += spent
        return given

    def steal(self, hive: int, amount: float) -> float:
        """Шершень крадёт мёд у летка (§7.1); вернуть, сколько украдено."""
        taken = min(max(amount, 0.0), float(self.honey[hive]))
        self.honey[hive] -= taken
        self.stolen[hive] += taken
        return taken

    # --------------------------------------------------------------- выведение

    def alive_and_queued(self, hive: int, flying_alive: int) -> int:
        """Сколько мест улья занято: живые (летающие + домашние) и личинки."""
        return flying_alive + self.house_count(hive) + len(self.queue[hive])

    def breed(self, hive: int, kind: BeeKind, flying_alive: int) -> str | None:
        """Поставить личинку в очередь; `None` — успех, иначе причина отказа."""
        if kind not in BEE_KINDS:
            return f"нет такого типа пчелы: {kind!r}"
        cost = self.params.breeding[kind].cost
        if self.alive_and_queued(hive, flying_alive) >= self.max_bees:
            return f"улей полон ({self.max_bees} пчёл с личинками)"
        if self.honey[hive] < cost:
            return f"не хватает мёда: {kind} стоит {cost:g}, есть {self.honey[hive]:.2f}"
        self.honey[hive] -= cost
        self.spent_breeding[hive] += cost
        self.queue[hive].append(Larva(kind, self.params.breeding[kind].time_s, cost))
        return None

    def cancel(self, hive: int, kind: BeeKind) -> bool:
        """Снять последнюю личинку типа `kind` и вернуть её цену."""
        q = self.queue[hive]
        for i in range(len(q) - 1, -1, -1):
            if q[i].kind == kind:
                larva = q.pop(i)
                self.honey[hive] += larva.cost
                self.spent_breeding[hive] -= larva.cost
                self.refunded[hive] += larva.cost
                return True
        return False

    # --------------------------------------------------------------- тик

    def step(self, dt: float) -> list[Birth]:
        """Питание домашних, переработка, рост личинок за `dt`. Вернуть рождения."""
        p = self.params
        births: list[Birth] = []
        for h in range(self.n_hives):
            slots = self.house_slots(h)
            need = p.feeding.house_consumption * slots.size * dt
            eaten = min(need, float(self.honey[h]))
            self.honey[h] -= eaten
            self.spent_house[h] += eaten
            working = slots.size == 0 or eaten >= need - 1e-12
            self.working[h] = working
            tasks = self.house_task[slots]
            n_process = int(np.count_nonzero(tasks == PROCESS)) if working else 0
            n_nurse = int(np.count_nonzero(tasks == NURSE)) if working else 0

            if n_process and self.nectar[h] > 0:
                amount = min(float(self.process_rate(n_process)) * dt, float(self.nectar[h]))
                made = amount * p.processing.honey_per_nectar
                self.nectar[h] -= amount
                self.processed[h] += amount
                self.honey[h] += made
                self.honey_made[h] += made

            q = self.queue[h]
            if q:
                q[0].left_s -= dt * float(self.nurse_speedup(n_nurse))
                if q[0].left_s <= 0:
                    births.append(Birth(h, q.pop(0).kind))
        return births

    def honey_bound(self) -> np.ndarray:
        """Верхняя граница мёда по инварианту: старт + мёд из переработки."""
        return self.start_honey + self.params.processing.honey_per_nectar * self.processed

    def queue_view(self, hive: int) -> list[dict[str, float | str]]:
        """Очередь выведения для сенсоров: тип и оставшееся базовое время, с."""
        return [{"kind": lv.kind, "left_s": max(0.0, lv.left_s)} for lv in self.queue[hive]]
