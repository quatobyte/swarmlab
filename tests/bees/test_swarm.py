"""Критерии приёмки M1: толпа, цветок, скорости и время полёта, груз, ветер, гибель."""

import numpy as np
import pytest

from swarmlab.bees.params import FLYING_KINDS
from swarmlab.bees.state import FALLING, FLYING, FREE

from .helpers import CALM, FLAT, make_sim, run_for


def _ground_point(m, xy, agl):
    xy = np.asarray(xy, dtype=np.float64)
    return np.array([xy[0], xy[1], float(m.world.ground_height(xy)) + agl])


# ------------------------------------------------------------------ толпа


def test_crowd_keeps_distance():
    """100 пчёл 60 с летят в одну точку — центры всегда ≥ 0.9·(r1 + r2)."""
    sim = make_sim(*FLAT, *CALM, "pool.max_bees_per_hive=100")
    m = sim.module
    target = np.array([40.0, 40.0])
    kinds = [FLYING_KINDS[i % 3] for i in range(100)]
    # Старт — квадрат 10×10 с шагом 3 м в 20–50 м от цели.
    grid = np.stack(np.meshgrid(np.arange(10), np.arange(10)), -1).reshape(-1, 2) * 3.0
    slots = np.array(
        [m.spawn(0, k, _ground_point(m, [-35.0 + g[0], -35.0 + g[1]], 6.0))
         for k, g in zip(kinds, grid, strict=True)]
    )
    m.autopilot.fly_to(slots, np.tile(target, (100, 1)), agl=6.0)
    r = m.bees.radius[slots]
    r_sum = r[:, None] + r[None, :]
    iu = np.triu_indices(100, 1)
    worst = [np.inf]

    def check(s):
        pos, _ = s.module.backend.body_state(slots)
        d = np.linalg.norm(pos[:, None] - pos[None, :], axis=-1)
        worst[0] = min(worst[0], float((d[iu] / r_sum[iu]).min()))

    run_for(sim, 60.0, check)
    print(f"толпа: минимум d/(r1+r2) за 60 с = {worst[0]:.3f}")
    pos, _ = m.backend.body_state(slots)
    assert np.all(m.bees.state[slots] == FLYING)
    # Рой действительно собрался у цели (иначе тест ничего не проверяет).
    assert np.median(np.linalg.norm(pos[:, :2] - target, axis=1)) < 3.0
    assert worst[0] >= 0.9, f"минимум d/(r1+r2) = {worst[0]:.3f}"


# ------------------------------------------------------------------ цветок


def test_hover_over_flower_no_contact():
    """Пчела висит над цветком: контактов нет, цветок не сдвигается, условия сбора §4.2."""
    sim = make_sim(*CALM)
    m = sim.module
    f = 0
    flower = m.world.flower_pos[f].copy()
    nectar = m.world.flower_nectar.copy()
    s = m.spawn(0, "forager", flower + np.array([6.0, 0.0, 3.0]))
    # Ниже допустимого: автопилот сам поднимет до просвета 1.5 м над рельефом.
    m.autopilot.fly_to(np.array([s]), flower[None, :2], z=np.array([flower[2] + 0.3]))
    contacts = []

    def check(sim_):
        a, b = sim_.module.backend.contact_pairs()
        contacts.append(int(np.sum((a == s) | (b == s))))

    run_for(sim, 15.0, check)
    pos, vel = m.backend.body_state(np.array([s]))
    rel = pos[0] - flower
    assert sum(contacts) == 0
    assert np.array_equal(m.world.flower_pos[f], flower)
    assert np.array_equal(m.world.flower_nectar, nectar)
    # Цветы в модели MuJoCo — сайты, а не геометрии: столкнуться не с чем.
    import mujoco

    geom_names = [mujoco.mj_id2name(m.backend.model, mujoco.mjtObj.mjOBJ_GEOM, i)
                  for i in range(m.backend.model.ngeom)]
    assert not any(n and n.startswith("flower") for n in geom_names)
    # Условия сбора (BEES_SPEC §4.2): горизонтально ≤ 1 м, высота ≤ 1.5 м, скорость < 0.7 м/с.
    assert np.hypot(rel[0], rel[1]) <= 1.0
    assert 0.0 < rel[2] <= 1.5
    assert np.linalg.norm(vel[0]) < 0.7


# ------------------------------------------------------------------ скорость и время полёта


def test_cruise_speed_and_flight_time_within_15_percent():
    """По типам: установившаяся скорость и время до E = 0 — в пределах ±15% от целей."""
    sim = make_sim(*FLAT, *CALM, "world.map_size=3000")
    m = sim.module
    slots = []
    for i, kind in enumerate(FLYING_KINDS):
        y = -20.0 + 20.0 * i
        s = m.spawn(0, kind, _ground_point(m, [-1450.0, y], 5.0))
        m.autopilot.fly_to(np.array([s]), np.array([[1450.0, y]]))  # speed=None — крейсерская
        slots.append(s)
    slots = np.array(slots)
    speeds: list[np.ndarray] = []
    empty_at = np.full(3, np.nan)

    def watch(s_):
        t = s_.time
        _, vel = m.backend.body_state(slots)
        if 30.0 <= t <= 150.0:
            speeds.append(np.linalg.norm(vel[:, :2], axis=1))
        for i, slot in enumerate(slots):
            if np.isnan(empty_at[i]) and m.bees.state[slot] in (FALLING, FREE):
                empty_at[i] = t

    while np.any(np.isnan(empty_at)) and sim.time < 400.0:
        sim.step()
        watch(sim)
    speed = np.array(speeds).mean(axis=0)
    for i, kind in enumerate(FLYING_KINDS):
        t = m.params.bee_types.of(kind)
        print(f"{kind}: скорость {speed[i]:.2f} м/с (цель {t.cruise_speed}), "
              f"время полёта {empty_at[i]:.0f} с (цель {t.flight_time_s:.0f})")
        assert speed[i] == pytest.approx(t.cruise_speed, rel=0.15), kind
        assert empty_at[i] == pytest.approx(t.flight_time_s, rel=0.15), kind


# ------------------------------------------------------------------ груз


def test_cargo_mass_slows_acceleration_in_mujoco():
    """Одинаковая сила → ускорение обратно пропорционально массе (body_mass меняется на лету)."""
    sim = make_sim(*FLAT, *CALM)
    m = sim.module
    empty = m.spawn(0, "forager", _ground_point(m, [20.0, -10.0], 10.0))
    full = m.spawn(0, "forager", _ground_point(m, [20.0, 10.0], 10.0))
    m.set_cargo(np.array([full]), 1.0)
    slots = np.array([empty, full])
    mass = m.bees.mass[slots]
    assert mass[1] == pytest.approx(mass[0] + 0.04)
    b = m.backend
    force = np.column_stack([np.full(2, 0.2), np.zeros(2), mass * m.gravity])
    for _ in range(100):  # 0.5 с без автопилота и сопротивления — только бэкенд
        b.set_forces(slots, force)
        b.step(1)
    _, vel = b.body_state(slots)
    ratio = vel[1, 0] / vel[0, 0]
    assert ratio == pytest.approx(mass[0] / mass[1], rel=1e-3)
    assert abs(vel[1, 2]) < 1e-6  # вес с грузом тоже учтён: висит


def test_loaded_forager_accelerates_slower_same_command():
    """Сборщик с полным грузом разгоняется медленнее пустого при той же команде автопилоту."""
    sim = make_sim(*FLAT, *CALM)
    m = sim.module
    empty = m.spawn(0, "forager", _ground_point(m, [-40.0, -10.0], 5.0))
    full = m.spawn(0, "forager", _ground_point(m, [-40.0, 10.0], 5.0))
    m.set_cargo(np.array([full]), m.bees.cargo_max[full])
    slots = np.array([empty, full])
    run_for(sim, 1.0)  # устоялись в висении
    m.autopilot.fly_to(slots, np.array([[60.0, -10.0], [60.0, 10.0]]), agl=5.0, speed=5.0)
    run_for(sim, 0.2)  # фаза разгона: тяга обеих в насыщении
    _, vel = m.backend.body_state(slots)
    # Запас горизонтальной тяги у полного меньше, а масса больше: √(T²−(mg)²)/m.
    assert vel[1, 0] < 0.85 * vel[0, 0]
    assert vel[1, 0] > 0.5  # но всё же разгоняется
    run_for(sim, 2.0)
    _, vel = m.backend.body_state(slots)
    # Та же команда в итоге выполнена — насколько позволяет тяга: с полным грузом
    # предел скорости ниже крейсерской пустого, √(√(T²−(mg)²)/c_d).
    p = m.params
    t = p.bee_types.forager
    mass = t.mass + float(m.bees.cargo[full]) * p.physics.cargo_unit_mass
    v_max = (np.sqrt(t.thrust_max**2 - (mass * p.physics.gravity) ** 2) / t.drag_coef) ** 0.5
    assert vel[1, 0] == pytest.approx(min(5.0, v_max), abs=0.6)


# ------------------------------------------------------------------ ветер


WIND3 = (
    "weather.enabled=true",
    "weather.initial=windy",
    "weather.states.windy.wind=[3.0, 3.0]",
    "wind.gust_harmonics=0",
    "wind.turn_rate_deg_s=0",
)


def test_crosswind_drifts_without_correction_autopilot_compensates():
    sim = make_sim(*FLAT, *WIND3)
    m = sim.module
    wind_dir = np.append(m.weather.base_direction(0.0), 0.0)
    across = np.array([-wind_dir[1], wind_dir[0], 0.0])
    # Пчёлы разнесены поперёк ветра, чтобы снесённая не налетела на висящую.
    start = [_ground_point(m, c, 10.0) for c in (30.0 * across[:2], [0.0, 0.0])]
    passive = m.spawn(0, "forager", start[0])  # тяга = вес, без коррекции
    holder = m.spawn(0, "forager", start[1])  # автопилот висит на месте
    m.set_thrust(np.array([passive]), np.array([[0.0, 0.0, m.bees.mass[passive] * m.gravity]]))
    run_for(sim, 15.0)
    pos, _ = m.backend.body_state(np.array([passive, holder]))
    drift = pos[0] - start[0]
    assert drift @ wind_dir > 20.0  # снесло по ветру
    assert np.linalg.norm(pos[1] - start[1]) < 0.5  # автопилот удержал точку


def test_autopilot_flies_straight_across_wind():
    sim = make_sim(*FLAT, *WIND3)
    m = sim.module
    wind_dir = np.append(m.weather.base_direction(0.0), 0.0)
    across = np.array([-wind_dir[1], wind_dir[0], 0.0])
    a = _ground_point(m, [0.0, 0.0], 10.0) - 30.0 * across
    b = a + 60.0 * across
    s = m.spawn(0, "forager", a)
    m.autopilot.fly_to(np.array([s]), b[None, :2], z=np.array([b[2]]), speed=3.0)
    cross = []

    def watch(sim_):
        pos, _ = m.backend.body_state(np.array([s]))
        cross.append(abs((pos[0] - a) @ wind_dir))

    run_for(sim, 35.0, watch)
    pos, _ = m.backend.body_state(np.array([s]))
    assert np.linalg.norm(pos[0] - b) < 0.5  # долетела
    assert max(cross) < 1.0  # сноса с линии почти нет


# ------------------------------------------------------------------ энергия и гибель


def test_zero_energy_falls_dies_and_slot_returns_to_pool():
    sim = make_sim(*FLAT, *CALM)
    m = sim.module
    start = _ground_point(m, [30.0, 30.0], 8.0)
    s = m.spawn(0, "scout", start)
    uid = int(m.bees.uid[s])
    run_for(sim, 0.5)
    m.bees.energy[s] = 0.0
    sim.step()
    assert m.bees.state[s] == FALLING
    events = []
    t0 = sim.time
    while m.bees.state[s] != FREE and sim.time - t0 < 5.0:
        sim.step()
        events += sim.module.snapshot().events
    assert m.bees.state[s] == FREE
    death = [e for e in events if e["type"] == "death"]
    assert death and death[0]["bee"] == uid and death[0]["cause"] == "energy"
    assert m.backend.is_parked(np.array([s]))[0]
    pos, _ = m.backend.body_state(np.array([s]))
    assert pos[0, 2] < -10.0  # под картой
    # Упала почти вертикально и погибла у земли.
    assert sim.time - t0 < 2.0
    # Слот снова выдаётся, у новой пчелы новый id.
    s2 = m.spawn(0, "guard")
    assert s2 == s and m.bees.uid[s2] != uid
    assert m.bees.radius[s2] == pytest.approx(m.params.bee_types.guard.radius)
    assert m.backend.model.geom_size[m.backend.geom_id(s2), 0] == pytest.approx(0.35)


# ------------------------------------------------------------------ возвращение домой


def test_go_home_from_behind_the_hive_enters():
    """Пчёлы за ульем (леток на другой грани) облетают его сбоку и входят (M6).

    Раньше прямой путь к летку упирался в заднюю стенку, и сборщики висели там с грузом.
    """
    from swarmlab.bees.control import GO_HOME
    from swarmlab.bees.state import IN_HIVE

    sim = make_sim(*CALM)
    m = sim.module
    w = m.world
    hive, half, ent = w.hive_pos[0], w.hive_half[0], w.hive_entrance[0]
    starts = [(-6.0, 0.0), (-12.0, 0.5), (-20.0, -1.0), (-5.0, 3.0), (-30.0, 0.0), (-3.0, -4.0)]
    points = [np.array([hive[0] - half[0] + dx, hive[1] + dy]) for dx, dy in starts]
    slots = np.array([
        m.spawn(0, "forager", np.array([*p, max(ent[2], w.ground_height(p) + 2.0)]))
        for p in points
    ])
    m.control.mode[slots] = GO_HOME
    run_for(sim, 30.0)
    assert np.all(m.bees.state[slots] == IN_HIVE), m.bees.state[slots]
