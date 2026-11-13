"""Юнит-тесты экономики улья (BEES_SPEC §4) — без физики."""

import numpy as np
import pytest

from swarmlab.bees.economy import HiveEconomy

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
    dt = 0.1
    for _ in range(100):  # 10 с
        e.step(dt)
    processed = e.processed[0]
    assert processed == pytest.approx(ECON.processing.k_proc * 2 * 10.0)
    eaten = ECON.feeding.house_consumption * 4 * 10.0
    assert e.honey[0] == pytest.approx(20.0 + 0.5 * processed - eaten)
    assert e.nectar[0] == pytest.approx(100.0 - processed)


def test_processing_stops_at_min_nectar():
    """Домашние перерабатывают сами, пока нектара больше `min_nectar` (DECISIONS №82)."""
    e = _economy(honey=20.0, nectar=1.0, house=9)
    for _ in range(100):
        e.step(0.1)
    left = e.nectar[0]
    assert 0.0 < left <= ECON.processing.min_nectar
    assert e.processed[0] == pytest.approx(1.0 - left)
    for _ in range(50):
        e.step(0.1)
    assert e.nectar[0] == left  # остаток не трогают


def test_house_bees_process_first_then_nurse():
    """Все домашние улья работают по одному правилу: нектар → переработка, иначе личинки."""
    e = _economy(honey=50.0, nectar=10.0, house=4)
    assert e.breed(0, "forager", flying_alive=0) is None
    base = ECON.breeding["forager"].time_s
    e.step(1.0)  # нектар есть — все перерабатывают, личинка растёт без нянек
    assert e.processed[0] == pytest.approx(ECON.processing.k_proc * 2 * 1.0)
    assert e.queue[0][0].left_s == pytest.approx(base - 1.0)
    e.nectar[0] = 0.0
    e.step(1.0)  # нектара нет — все четверо нянчат: вдвое быстрее
    assert e.queue[0][0].left_s == pytest.approx(base - 1.0 - 2.0)


def test_breeding_costs_honey_immediately_and_time_scales_with_nurses():
    e = _economy(honey=20.0, house=4)  # нектара нет — домашние нянчат сами
    assert e.breed(0, "forager", flying_alive=0) is None
    assert e.honey[0] == pytest.approx(20.0 - ECON.breeding["forager"].cost)
    assert e.breeding_time("forager", 4) == pytest.approx(ECON.breeding["forager"].time_s / 2)
    assert e.breeding_time("scout", 0) == pytest.approx(ECON.breeding["scout"].time_s)

    t, births = 0.0, []
    while not births:
        births = e.step(0.1)
        t += 0.1
    assert births[0].kind == "forager"
    assert t == pytest.approx(ECON.breeding["forager"].time_s / 2, abs=0.11)


@pytest.mark.parametrize("kind", ["scout", "forager", "house"])
def test_breeding_prices(kind):
    e = _economy(honey=10.0)
    assert e.breed(0, kind, flying_alive=0) is None
    assert e.honey[0] == pytest.approx(10.0 - ECON.breeding[kind].cost)


def test_breeding_queue_is_sequential():
    e = _economy(honey=20.0)
    for kind in ("scout", "house", "scout"):
        assert e.breed(0, kind, flying_alive=0) is None
    spent = 2 * ECON.breeding["scout"].cost + ECON.breeding["house"].cost
    assert e.honey[0] == pytest.approx(20.0 - spent)
    births = []
    for _ in range(int(ECON.breeding["scout"].time_s * 10) + 1):
        births += e.step(0.1)
    assert [b.kind for b in births] == ["scout"]  # растёт только голова очереди
    assert [lv.kind for lv in e.queue[0]] == ["house", "scout"]


def test_breeding_refused_without_honey_or_space():
    e = _economy(honey=1.0, max_bees=5)
    assert e.breed(0, "forager", flying_alive=0) is not None
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
    kinds = ("scout", "forager", "house")
    for _ in range(5000):
        op = gen.integers(0, 4)
        if op == 0:
            e.deliver(0, float(gen.uniform(0, 1.0)))
        elif op == 1:
            e.breed(0, kinds[gen.integers(0, 3)], flying_alive=int(gen.integers(0, 40)))
        elif op == 2:
            k = int(gen.integers(1, 5))
            e.refuel(np.zeros(k, dtype=np.int64), gen.uniform(0, 2000, k), 0.1)
        else:
            for b in e.step(float(gen.uniform(0.01, 0.5))):
                if b.kind == "house" and e.house_count(0) < 60:
                    e.add_house(0, int(gen.integers(10_000, 1_000_000)))
        assert e.honey[0] >= -1e-9
        assert e.nectar[0] >= -1e-9
        assert e.honey[0] <= e.honey_bound()[0] + 1e-9
