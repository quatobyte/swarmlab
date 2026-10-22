"""Юнит-тесты экономики улья (BEES_SPEC §4) — без физики."""

import numpy as np
import pytest

from swarmlab.bees.economy import NURSE, PROCESS, HiveEconomy

from .helpers import bees_params

ECON = bees_params().economy


def _economy(honey: float = 20.0, nectar: float = 0.0, house: int = 0, max_bees: int = 50):
    e = HiveEconomy(1, ECON, max_bees)
    e.honey[0] = honey
    e.start_honey[0] = honey
    e.nectar[0] = nectar
    for i in range(house):
        e.add_house(0, 1000 + i)
    return e


def _set_tasks(e: HiveEconomy, process: int = 0, nurse: int = 0) -> None:
    slots = e.house_slots(0)
    e.set_task(slots[:process], PROCESS)
    e.set_task(slots[process : process + nurse], NURSE)


def test_processing_has_diminishing_returns():
    e = _economy()
    k = ECON.processing.k_proc
    assert e.process_rate(1) == pytest.approx(k)
    assert e.process_rate(4) == pytest.approx(2 * k)  # вчетверо больше пчёл — вдвое быстрее
    assert e.process_rate(9) == pytest.approx(3 * k)
    rates = e.process_rate(np.arange(1, 20))
    per_bee = rates / np.arange(1, 20)
    assert np.all(np.diff(per_bee) < 0)  # на одну пчелу — всё меньше


def test_processing_converts_one_nectar_to_half_honey():
    e = _economy(honey=20.0, nectar=100.0, house=4)
    _set_tasks(e, process=4)
    dt = 0.1
    for _ in range(100):  # 10 с
        e.step(dt)
    processed = e.processed[0]
    assert processed == pytest.approx(ECON.processing.k_proc * 2 * 10.0)
    eaten = ECON.feeding.house_consumption * 4 * 10.0
    assert e.honey[0] == pytest.approx(20.0 + 0.5 * processed - eaten)
    assert e.nectar[0] == pytest.approx(100.0 - processed)


def test_processing_stops_without_nectar():
    e = _economy(honey=20.0, nectar=0.05, house=9)
    _set_tasks(e, process=9)
    for _ in range(50):
        e.step(0.1)
    assert e.nectar[0] == 0.0
    assert e.processed[0] == pytest.approx(0.05)


def test_breeding_costs_honey_immediately_and_time_scales_with_nurses():
    e = _economy(honey=20.0, house=4)
    _set_tasks(e, nurse=4)
    assert e.breed(0, "forager", flying_alive=0) is None
    assert e.honey[0] == pytest.approx(20.0 - ECON.breeding["forager"].cost)
    assert e.breeding_time("forager", 4) == pytest.approx(ECON.breeding["forager"].time_s / 2)
    assert e.breeding_time("guard", 0) == pytest.approx(ECON.breeding["guard"].time_s)

    t, births = 0.0, []
    while not births:
        births = e.step(0.1)
        t += 0.1
    assert births[0].kind == "forager"
    assert t == pytest.approx(ECON.breeding["forager"].time_s / 2, abs=0.11)


@pytest.mark.parametrize("kind", ["scout", "forager", "guard", "house"])
def test_breeding_prices(kind):
    e = _economy(honey=10.0)
    assert e.breed(0, kind, flying_alive=0) is None
    assert e.honey[0] == pytest.approx(10.0 - ECON.breeding[kind].cost)


def test_breeding_queue_is_sequential_and_cancel_refunds():
    e = _economy(honey=20.0)
    for kind in ("scout", "guard", "scout"):
        assert e.breed(0, kind, flying_alive=0) is None
    spent = 2 * ECON.breeding["scout"].cost + ECON.breeding["guard"].cost
    assert e.honey[0] == pytest.approx(20.0 - spent)
    assert e.cancel(0, "scout")
    assert [lv.kind for lv in e.queue[0]] == ["scout", "guard"]  # снята последняя
    assert e.honey[0] == pytest.approx(20.0 - spent + ECON.breeding["scout"].cost)
    assert not e.cancel(0, "forager")


def test_breeding_refused_without_honey_or_space():
    e = _economy(honey=1.0, max_bees=5)
    assert e.breed(0, "guard", flying_alive=0) is not None
    assert e.honey[0] == 1.0  # отказ ничего не списывает
    e.honey[0] = 100.0
    assert e.breed(0, "scout", flying_alive=5) is not None  # улей полон
    assert e.breed(0, "scout", flying_alive=4) is None
    assert e.breed(0, "scout", flying_alive=4) is not None  # личинка заняла последнее место


def test_refuel_rate_and_price():
    e = _economy(honey=20.0)
    f = ECON.feeding
    given = e.refuel(np.array([0, 0]), np.array([1000.0, 5.0]), dt=0.1)
    assert given[0] == pytest.approx(f.refuel_rate * 0.1)  # не быстрее 200 Дж/с
    assert given[1] == pytest.approx(5.0)  # не больше недостающего
    assert e.honey[0] == pytest.approx(20.0 - given.sum() / f.joules_per_honey)


def test_refuel_shares_last_honey_and_stops_at_zero():
    e = _economy(honey=0.01)  # 20 Дж
    given = e.refuel(np.array([0, 0]), np.array([1000.0, 1000.0]), dt=0.1)
    assert given.sum() == pytest.approx(0.01 * ECON.feeding.joules_per_honey)
    assert given[0] == pytest.approx(given[1])
    assert e.honey[0] == pytest.approx(0.0)
    assert e.refuel(np.array([0]), np.array([1000.0]), dt=0.1)[0] == 0.0


def test_house_bees_eat_and_stop_working_without_honey():
    e = _economy(honey=1.0, nectar=50.0, house=10)
    _set_tasks(e, process=10)
    e.step(1.0)
    assert e.honey[0] == pytest.approx(
        1.0 - 10 * ECON.feeding.house_consumption + 0.5 * e.processed[0]
    )
    e.honey[0] = 0.0
    before = e.processed[0]
    e.step(1.0)
    assert not e.working[0]
    assert e.processed[0] == before  # голодные домашние не перерабатывают


def test_honey_never_appears_from_nothing_random_operations():
    """Инвариант: мёд ≤ старт + 0.5·переработанный нектар после любой операции."""
    gen = np.random.default_rng(7)
    e = _economy(honey=20.0, nectar=0.0, house=6, max_bees=60)
    kinds = ("scout", "forager", "guard", "house")
    for _ in range(5000):
        op = gen.integers(0, 6)
        if op == 0:
            e.deliver(0, float(gen.uniform(0, 1.0)))
        elif op == 1:
            e.breed(0, kinds[gen.integers(0, 4)], flying_alive=int(gen.integers(0, 40)))
        elif op == 2:
            e.cancel(0, kinds[gen.integers(0, 4)])
        elif op == 3:
            k = int(gen.integers(1, 5))
            e.refuel(np.zeros(k, dtype=np.int64), gen.uniform(0, 2000, k), 0.1)
        elif op == 4:
            slots = e.house_slots(0)
            e.set_task(slots, gen.integers(0, 3, slots.size))
        else:
            for b in e.step(float(gen.uniform(0.01, 0.5))):
                if b.kind == "house" and e.house_count(0) < 60:
                    e.add_house(0, int(gen.integers(10_000, 1_000_000)))
        assert e.honey[0] >= -1e-9
        assert e.nectar[0] >= -1e-9
        assert e.honey[0] <= e.honey_bound()[0] + 1e-9
