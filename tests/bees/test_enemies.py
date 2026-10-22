"""Враги M3 (BEES_SPEC §7): шершни, тепловой шар, грабёж, пауки, переключатели."""

import math

import numpy as np
import pytest

from swarmlab.bees.control import INTERCEPT
from swarmlab.bees.state import FREE

from .helpers import CALM, FLAT, make_sim, run_for

#: Шершни включены, но волн нет — тест сам ставит шершня (`enemies.spawn`).
HORNETS = ("enemies.hornets.enabled=true", "enemies.hornets.first_wave_s=1e9")


def _ground_point(m, xy, agl):
    xy = np.asarray(xy, dtype=np.float64)
    return np.array([xy[0], xy[1], float(m.world.ground_height(xy[None])[0]) + agl])


def _events(sim, seconds, types=None):
    out = []
    steps = round(seconds / sim.clock.dt)
    for _ in range(steps):
        sim.step()
        if sim.clock.is_decision_step:
            out += sim.module.snapshot().events
    return [e for e in out if types is None or e["type"] in types]


# ------------------------------------------------------------------ тепловой шар


def test_three_guards_surround_hornet_and_it_dies_or_flees():
    sim = make_sim(*FLAT, *CALM, *HORNETS)
    m = sim.module
    center = _ground_point(m, [40.0, 40.0], 8.0)
    h = m.enemies.spawn(center)
    hornet_uid = int(m.enemies.uid[h])
    guards = []
    for k in range(3):
        a = 2 * math.pi * k / 3
        g = m.spawn(0, "guard", center + np.array([4 * math.cos(a), 4 * math.sin(a), 0.0]))
        m.control.mode[g] = INTERCEPT
        m.control.target[g] = hornet_uid
        guards.append(g)

    # Убегающий шершень (7 м/с) быстрее охранников (6 м/с): до края «Малой» карты ~10 с.
    events = _events(sim, 30.0)
    kinds = [e["type"] for e in events]
    gone = [e for e in events if e["type"] in ("hornet_death", "hornet_left")
            and e["hornet"] == hornet_uid]
    lost_guards = [e for e in events if e["type"] == "death" and e["cause"] == "hornet"]
    print(f"события: {sorted(set(kinds))}; итог шершня: {gone}; погибло охранников "
          f"{len(lost_guards)}")
    assert "heat_ball" in kinds
    assert gone, "шершень не погиб и не улетел за 30 с"
    assert not m.enemies.alive[h]
    assert len(lost_guards) <= 2  # шершень кусает по одной пчеле за раз


def test_single_guard_does_not_hurt_hornet():
    sim = make_sim(*FLAT, *CALM, *HORNETS, "enemies.hornets.attack=false")
    m = sim.module
    center = _ground_point(m, [40.0, 40.0], 8.0)
    h = m.enemies.spawn(center)
    g = m.spawn(0, "guard", center + np.array([3.0, 0.0, 0.0]))
    m.control.mode[g] = INTERCEPT
    m.control.target[g] = int(m.enemies.uid[h])
    run_for(sim, 6.0)
    assert m.enemies.hp[h] == pytest.approx(m.params.enemies.hornets.hp)


def test_heat_ball_switch_off_keeps_hornet_alive():
    sim = make_sim(*FLAT, *CALM, *HORNETS, "enemies.hornets.heat_ball=false",
                   "enemies.hornets.attack=false")
    m = sim.module
    center = _ground_point(m, [40.0, 40.0], 8.0)
    h = m.enemies.spawn(center)
    for k in range(3):
        g = m.spawn(0, "guard", center + np.array([3.0 * (k - 1), 3.0, 0.0]))
        m.control.mode[g] = INTERCEPT
        m.control.target[g] = int(m.enemies.uid[h])
    events = _events(sim, 6.0)
    assert m.enemies.hp[h] == pytest.approx(m.params.enemies.hornets.hp)
    assert not [e for e in events if e["type"] == "heat_ball"]


# ------------------------------------------------------------------ атака


@pytest.mark.parametrize("attack", [True, False])
def test_hornet_kills_lone_bee_after_continuous_contact(attack):
    sim = make_sim(*FLAT, *CALM, *HORNETS, f"enemies.hornets.attack={str(attack).lower()}")
    m = sim.module
    spot = _ground_point(m, [-40.0, 30.0], 6.0)
    s = m.spawn(0, "forager", spot)
    uid = int(m.bees.uid[s])
    m.enemies.spawn(spot + np.array([2.0, 0.0, 0.0]))
    events = _events(sim, 6.0)
    deaths = [e for e in events if e["type"] == "death" and e["bee"] == uid]
    attacks = [e for e in events if e["type"] == "attack" and e["bee"] == uid]
    if attack:
        assert deaths and deaths[0]["cause"] == "hornet"
        assert attacks
        # Не раньше kill_contact_s после начала контакта.
        assert deaths[0]["time"] - attacks[0]["time"] >= 1.5 - 1e-6
        assert m.bees.state[s] == FREE or m.bees.uid[s] != uid
    else:
        assert not deaths and not attacks
        assert m.bees.uid[s] == uid


# ------------------------------------------------------------------ грабёж


@pytest.mark.parametrize("case", ["rob", "guard_near", "switch_off"])
def test_hornet_robs_hive_without_guards(case):
    extra = ("enemies.hornets.rob=false",) if case == "switch_off" else ()
    sim = make_sim(*FLAT, *CALM, *HORNETS, "enemies.hornets.attack=false", *extra)
    m = sim.module
    e = m.economy
    entrance = m.world.hive_entrance[0]
    if case == "guard_near":
        # Охранник висит рядом с летком (ближе rob_guard_radius к шершню).
        m.spawn(0, "guard", entrance + np.array([2.0, 3.0, 1.5]))
    m.enemies.spawn(entrance + np.array([6.0, 0.0, 2.0]))
    honey0 = float(e.honey[0])
    events = _events(sim, 15.0)
    robbed = [ev for ev in events if ev["type"] == "rob"]
    stolen = float(e.stolen[0])
    if case == "rob":
        assert robbed and robbed[0]["hive"] == 0
        # 0.2 ед./с, пока шершень у летка (он подлетает за пару секунд).
        assert 1.0 < stolen <= 0.2 * 15.0 + 1e-9
        assert float(e.honey[0]) == pytest.approx(honey0 - stolen)
    else:
        assert not robbed and stolen == 0.0


# ------------------------------------------------------------------ волны


def test_hornet_waves_grow_and_respect_max():
    sim = make_sim(
        *FLAT, *CALM, "enemies.hornets.enabled=true", "enemies.hornets.first_wave_s=5",
        "enemies.hornets.wave_interval_s=5", "enemies.hornets.wave_growth_s=10",
    )
    m = sim.module
    cap = m.params.enemies.hornets.max  # «Малый» профиль — 3
    spawned = []
    for _ in range(round(21.0 / sim.clock.dt)):
        sim.step()
        if sim.clock.is_decision_step:
            spawned += [e for e in m.snapshot().events if e["type"] == "hornet_spawn"]
            assert m.enemies.alive.sum() <= cap
    times = [round(e["time"], 1) for e in spawned]
    # t=5: 1 шершень; t=10: волна 2, но мест 2 → 2; t=15, 20: мест нет.
    assert times == [5.0, 10.0, 10.0]
    half = m.world.half_size
    for e in spawned:
        assert max(abs(e["pos"][0]), abs(e["pos"][1])) == pytest.approx(half - 2.0, abs=1e-6)


def test_hornets_disabled_removes_bodies_and_events():
    sim = make_sim(
        *FLAT, "enemies.hornets.enabled=false", "enemies.hornets.first_wave_s=0",
        "enemies.hornets.wave_interval_s=1",
    )
    m = sim.module
    assert m.enemies.n == 0
    assert m.backend.n_bodies == m.bees.n
    events = _events(sim, 5.0)
    assert not [e for e in events if e["type"].startswith("hornet")]


# ------------------------------------------------------------------ пауки


def _forager_on_flowers(sim, n):
    """`n` сборщиков сразу над разными цветками в режиме `collect`."""
    from swarmlab.bees.control import COLLECT

    m = sim.module
    flowers = np.arange(n)
    slots = []
    for f in flowers.tolist():
        s = m.spawn(0, "forager", m.world.flower_pos[f] + np.array([0.0, 0.0, 1.0]))
        m.control.mode[s] = COLLECT
        m.control.target[s] = f
        slots.append(s)
    return np.array(slots)


def test_spider_deaths_match_expected_rate_fixed_seed():
    """Статистика пауков: число гибелей ≈ сумма вероятностей укусов (±3σ), seed фиксирован."""
    sim = make_sim(
        *CALM, "enemies.spiders.enabled=true", "enemies.spiders.flower_fraction=1.0",
        "pool.max_bees_per_hive=60", seed=7,
    )
    m = sim.module
    n = 48
    slots = _forager_on_flowers(sim, n)
    uids = set(m.bees.uid[slots].tolist())
    events = _events(sim, 12.0)
    deaths = [e for e in events if e["type"] == "death" and e["bee"] in uids]
    assert all(e["cause"] == "spider" for e in deaths)
    en = m.enemies
    p = m.params.enemies.spiders.kill_prob_per_s
    p_tick = 1 - (1 - p) ** m._decision_dt
    expected = en.bite_hazard
    sigma = math.sqrt(en.bite_rolls * p_tick * (1 - p_tick))
    exposure = en.bite_rolls * m._decision_dt  # секунд сбора на цветках с пауком
    # Та же величина через «0.15 в секунду»: ожидаемая доля погибших за время сбора.
    per_bee = exposure / n
    print(
        f"сборщиков {n}, бросков {en.bite_rolls}, сбор {exposure:.1f} с ({per_bee:.2f} с на "
        f"пчелу), погибло {len(deaths)}, ожидалось {expected:.1f} ± {sigma:.1f}"
    )
    assert en.bite_rolls > 500
    assert abs(len(deaths) - expected) <= 3 * sigma
    # Сбор до полного груза — 4 с, гибель за это время ≈ 1 − 0.85^4 ≈ 48%.
    frac = len(deaths) / n
    assert 0.25 <= frac <= 0.70


def test_spiders_disabled_no_spider_flowers_no_deaths():
    sim = make_sim(
        *CALM, "enemies.spiders.enabled=false", "enemies.spiders.flower_fraction=1.0",
        "enemies.spiders.kill_prob_per_s=1.0",
    )
    m = sim.module
    assert not m.world.flower_spider.any()
    _forager_on_flowers(sim, 10)
    events = _events(sim, 6.0)
    assert not [e for e in events if e["type"] == "death"]
    assert m.enemies.bite_rolls == 0


def test_guard_sees_hornet_in_sensors():
    sim = make_sim(*FLAT, *CALM, *HORNETS)
    m = sim.module
    spot = _ground_point(m, [20.0, -30.0], 6.0)
    g = m.spawn(0, "guard", spot)
    h = m.enemies.spawn(spot + np.array([5.0, 0.0, 0.0]))
    run_for(sim, 0.2)
    rows = [r for r in m.hive_sensors(0) if r["me"]["id"] == int(m.bees.uid[g])]
    enemies = rows[0]["enemies"]
    assert [e["id"] for e in enemies] == [int(m.enemies.uid[h])]
    assert enemies[0]["kind"] == "hornet"
