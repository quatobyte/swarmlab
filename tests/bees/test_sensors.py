"""Сенсоры (BEES_SPEC §5.1), сообщения и феромоны (§5.2)."""

import msgpack
import numpy as np
import pytest

from swarmlab.bees.params import PheromoneParams
from swarmlab.bees.pheromones import PheromoneField
from swarmlab.core.protocol import SensorBatch

from .helpers import CALM, FLAT, make_sim, run_for

ME_KEYS = {"id", "kind", "pos", "vel", "energy", "energy_max", "cargo", "cargo_max",
           "in_hive", "alive"}
TOP_KEYS = {"tick", "time", "me", "home", "ground_z", "airspeed", "weather", "flowers", "bees",
            "enemies", "obstacles", "messages", "pheromones"}


def _plain(x):
    """Только типы протокола: dict/list/float/int/bool/str."""
    if isinstance(x, dict):
        return all(isinstance(k, str) and _plain(v) for k, v in x.items())
    if isinstance(x, list):
        return all(_plain(v) for v in x)
    return isinstance(x, (float, int, bool, str))


def _point(m, xy, agl):
    xy = np.asarray(xy, dtype=np.float64)
    return np.array([xy[0], xy[1], float(m.world.ground_height(xy)) + agl])


def test_sensor_format_matches_spec_and_serializes():
    sim = make_sim(*CALM, profile="medium")
    m = sim.module
    entrance = m.world.hive_entrance
    a = m.spawn(0, "scout", entrance[0] + np.array([3.0, 0.0, 2.0]))
    b = m.spawn(0, "forager", entrance[0] + np.array([6.0, 0.0, 2.0]))
    c = m.spawn(1, "guard", entrance[1] + np.array([3.0, 0.0, 2.0]))
    run_for(sim, 0.1)
    batch = m.collect_sensors(0)
    assert isinstance(batch, SensorBatch) and batch.team == 0
    agents = batch.agents
    assert [s["me"]["id"] for s in agents] == [int(m.bees.uid[a]), int(m.bees.uid[b])]
    for s in agents:
        assert set(s) == TOP_KEYS
        assert set(s["me"]) == ME_KEYS
        assert set(s["home"]) == {"pos", "dir", "dist"}
        assert set(s["pheromones"]) == {"values", "gradient"}
        assert np.array(s["pheromones"]["values"]).shape == (3, 3, 4)
        assert np.array(s["pheromones"]["gradient"]).shape == (4, 2)
        assert s["weather"] == "clear" and s["enemies"] == []
        assert _plain(s)
    # Протокол M2 — msgpack без pickle: сериализуется и читается обратно без потерь.
    raw = msgpack.packb(agents)
    assert msgpack.unpackb(raw, strict_map_key=False) == agents
    scout = agents[0]
    assert scout["me"]["kind"] == "scout" and scout["me"]["energy"] > 0
    # Видит соседку своего улья (3 м), но не охранника другого улья (далеко).
    seen = {x["id"]: x for x in scout["bees"]}
    assert int(m.bees.uid[b]) in seen and int(m.bees.uid[c]) not in seen
    rel = np.array(seen[int(m.bees.uid[b])]["rel_pos"])
    assert np.allclose(rel, [3.0, 0.0, 0.0], atol=0.05)
    assert seen[int(m.bees.uid[b])]["kind"] == "forager" and seen[int(m.bees.uid[b])]["team"] == 0
    # Дом: направление единичное, расстояние согласовано с позицией.
    pos = np.array(scout["me"]["pos"])
    assert np.isclose(np.linalg.norm(scout["home"]["dir"]), 1.0)
    assert np.isclose(scout["home"]["dist"], np.linalg.norm(entrance[0] - pos))
    # Улей 1 видит только свою пчелу.
    assert [s["me"]["id"] for s in m.collect_sensors(1).agents] == [int(m.bees.uid[c])]


def test_view_radius_rain_and_spider_visibility():
    sim = make_sim(*FLAT, *CALM, "enemies.spiders.enabled=true",
                   "enemies.spiders.flower_fraction=1.0")
    m = sim.module
    f = m.world.flower_pos[0]
    scout = m.spawn(0, "scout", f + np.array([3.0, 0.0, 1.5]))
    forager = m.spawn(0, "forager", f + np.array([-3.0, 0.0, 1.5]))
    far = m.spawn(0, "forager", f + np.array([0.0, 20.0, 1.5]))
    run_for(sim, 0.1)
    by_id = {s["me"]["id"]: s for s in m.collect_sensors(0).agents}
    sc, fo = by_id[int(m.bees.uid[scout])], by_id[int(m.bees.uid[forager])]
    near_sc = [x for x in sc["flowers"] if np.linalg.norm(x["rel_pos"]) <= 4.0]
    assert near_sc and all(x["spider"] is True for x in near_sc)  # разведчик видит паука
    assert all("spider" not in x for x in sc["flowers"] if np.linalg.norm(x["rel_pos"]) > 4.0)
    assert fo["flowers"] and all("spider" not in x for x in fo["flowers"])  # сборщик — нет
    # Обзор сборщика 8 м: пчела в 20 м не видна; все видимые цветы ближе 8 м.
    assert int(m.bees.uid[far]) not in {x["id"] for x in fo["bees"]}
    assert max(np.linalg.norm(x["rel_pos"]) for x in fo["flowers"]) <= 8.0
    # В дождь обзор ×0.7: сборщик видит не дальше 5.6 м.
    m.weather.rain = True
    m.decide(sim.clock.decision_tick)
    fo_rain = {s["me"]["id"]: s for s in m.collect_sensors(0).agents}[int(m.bees.uid[forager])]
    assert max(np.linalg.norm(x["rel_pos"]) for x in fo_rain["flowers"]) <= 5.6
    assert len(fo_rain["flowers"]) < len(fo["flowers"])


def test_sensor_noise_only_when_enabled():
    def scout_pos(noise: bool):
        sim = make_sim(*CALM, f"sensor_noise={str(noise).lower()}")
        m = sim.module
        s = m.spawn(0, "scout", m.world.hive_entrance[0] + np.array([3.0, 0.0, 2.0]))
        run_for(sim, 0.1)
        true_pos, _ = m.backend.body_state(np.array([s]))
        return np.array(m.collect_sensors(0).agents[0]["me"]["pos"]) - true_pos[0]

    assert np.allclose(scout_pos(False), 0.0)
    err = scout_pos(True)
    assert np.linalg.norm(err) > 1e-3 and np.all(np.abs(err) < 5 * 0.3)


def test_obstacles_seen_and_avoided():
    """Пчела летит сквозь дерево: видит его в сенсорах и облетает без контакта."""
    sim = make_sim(*CALM, "world.terrain.max_relief=0", "world.rocks.per_ha=0")
    m = sim.module
    obs = m.obstacles
    trunk = int(np.flatnonzero(obs.kind == obs.TRUNK)[0])
    base = np.append(obs.xy[trunk], obs.z0[trunk])
    height = obs.z1[trunk] - obs.z0[trunk]
    agl = 0.5 * height  # на уровне ствола
    a = base + np.array([-15.0, 0.1, agl])
    b = base + np.array([15.0, 0.1, agl])
    s = m.spawn(0, "forager", a)
    m.autopilot.fly_to(np.array([s]), b[None, :2], z=np.array([b[2]]))
    run_for(sim, 2.0)  # ствол уже в радиусе обзора сборщика (8 м)
    sens = m.collect_sensors(0).agents[0]
    radii = sorted(o["radius"] for o in sens["obstacles"])
    assert any(np.isclose(r, obs.radius[trunk]) for r in radii)
    touched = []

    def watch(sim_):
        ca, cb = sim_.module.backend.contact_pairs()
        touched.append(bool(np.any((ca == s) | (cb == s))))

    run_for(sim, 25.0, watch)
    pos, _ = m.backend.body_state(np.array([s]))
    assert not any(touched)
    assert np.linalg.norm(pos[0, :2] - b[:2]) < 1.0  # долетела за дерево


def test_messages_delivered_next_tick_to_own_hive_in_radius():
    sim = make_sim(*CALM, profile="medium")
    m = sim.module
    e = m.world.hive_entrance
    sender = m.spawn(0, "scout", e[0] + np.array([5.0, 0.0, 2.0]))
    near = m.spawn(0, "forager", e[0] + np.array([15.0, 0.0, 2.0]))  # 10 м
    far = m.spawn(0, "forager", e[0] + np.array([5.0, 0.0, 25.0]))  # 23 м — вне радиуса 15
    other = m.spawn(1, "forager", e[0] + np.array([8.0, 0.0, 2.0]))  # чужой улей рядом
    run_for(sim, 0.1)  # на тике 1
    m.signal(sender, [1.0, 2.5])
    with pytest.raises(ValueError):
        m.signal(sender, list(range(9)))
    got = {s["me"]["id"]: s["messages"] for s in m.collect_sensors(0).agents}
    assert all(v == [] for v in got.values())  # на этом же тике — ещё нет
    run_for(sim, 0.1)  # следующий тик решений
    s0 = {s["me"]["id"]: s["messages"] for s in m.collect_sensors(0).agents}
    msgs = s0[int(m.bees.uid[near])]
    assert len(msgs) == 1 and msgs[0]["from_id"] == int(m.bees.uid[sender])
    assert msgs[0]["values"] == [1.0, 2.5]
    assert np.allclose(msgs[0]["rel_pos"], [-10.0, 0.0, 0.0], atol=0.1)
    assert s0[int(m.bees.uid[far])] == [] and s0[int(m.bees.uid[sender])] == []
    assert m.collect_sensors(1).agents[0]["messages"] == []
    assert m._delivery.hive_inbox[0].tolist() == [0]  # леток в 5 м — улей тоже слышит
    assert other is not None
    run_for(sim, 0.1)  # и только один раз
    assert all(s["messages"] == [] for s in m.collect_sensors(0).agents)


def test_pheromones_mark_decay_gradient():
    f = PheromoneField(2, 20.0, PheromoneParams(cell=2.0, channels=4, half_life_s=60.0,
                                                neighborhood=3))
    f.mark(np.array([0]), np.array([[1.0, 1.0]]), np.array([2]), np.array([4.0]))
    win, grad = f.sample(np.array([0, 1]), np.array([[1.0, 1.0], [1.0, 1.0]]))
    assert win.shape == (2, 3, 3, 4) and grad.shape == (2, 4, 2)
    assert win[0, 1, 1, 2] == 4.0 and win[1].sum() == 0.0  # чужой улей не видит
    # Справа от метки: градиент по x отрицательный (к метке — назад).
    _, g = f.sample(np.array([0]), np.array([[3.0, 1.0]]))
    assert g[0, 2, 0] == pytest.approx(-4.0 / 4.0) and g[0, 2, 1] == 0.0
    for _ in range(600):  # 60 с по 0.1 с
        f.decay(0.1)
    assert f.values[0].sum() == pytest.approx(2.0)
    # За краем карты — нули.
    win, _ = f.sample(np.array([0]), np.array([[-9.5, -9.5]]))
    assert win[0, 0, :, :].sum() == 0.0 and win[0, :, 0, :].sum() == 0.0
    with pytest.raises(ValueError):
        f.mark(np.array([0]), np.array([[0.0, 0.0]]), np.array([4]), np.array([1.0]))


def test_mark_via_module_reaches_sensors():
    sim = make_sim(*CALM)
    m = sim.module
    s = m.spawn(0, "scout", m.world.hive_entrance[0] + np.array([5.0, 0.0, 2.0]))
    run_for(sim, 0.1)
    m.mark(s, 1, 3.0)
    run_for(sim, 0.1)
    p = m.collect_sensors(0).agents[0]["pheromones"]["values"]
    assert p[1][1][1] == pytest.approx(3.0 * 0.5 ** (0.1 / 60.0), rel=1e-6)
