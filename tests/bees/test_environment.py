"""Ветер и дождь, силы, калибровка, детерминизм роя M1."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from swarmlab.bees.physics import forces
from swarmlab.bees.weather import Weather
from swarmlab.cli import main
from swarmlab.core.config import load_match
from swarmlab.core.rng import RngRegistry
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS, FLAT, bees_params, make_sim, run_for

ROOT = Path(__file__).resolve().parents[2]
M1 = CONFIGS / "matches" / "m1_swarm.yaml"


def _weather(*overrides, seed=5):
    p = bees_params(overrides=overrides)
    return Weather(p.weather, p.wind, RngRegistry(seed).get("weather"))


def test_weather_disabled_means_no_wind_no_rain():
    w = _weather("weather.enabled=false", "weather.initial=rain")
    pos = np.array([[0.0, 0.0, 5.0], [30.0, -20.0, 12.0]])
    assert np.all(w.wind_at(pos, np.zeros(2), 10.0) == 0.0)
    assert not w.rain and w.state == "clear"


def test_wind_profile_gusts_and_determinism():
    w = _weather("weather.enabled=true", "weather.initial=windy")
    lo, hi = w.params.states["windy"].wind
    assert lo <= w.w_ref <= hi and not w.rain
    xy = np.zeros((4, 2))
    z = np.array([0.3, 1.0, 10.0, 25.0])
    pos = np.column_stack([xy, z])
    wind = w.wind_at(pos, np.zeros(4), 0.0)
    speed = np.linalg.norm(wind, axis=1)
    assert np.all(wind[:, 2] == 0.0)
    assert speed[0] == pytest.approx(speed[1])  # ниже 1 м — как на 1 м
    assert speed[3] / speed[2] == pytest.approx((25.0 / 10.0) ** 0.14)
    # Порывы: ветер меняется во времени и в пространстве, но в пределах амплитуды.
    t = np.linspace(0, 60, 200)
    p10 = np.array([[0.0, 0.0, 10.0]])
    series = np.array([w.wind_at(p10, np.zeros(1), ti)[0] for ti in t])
    s = np.linalg.norm(series, axis=1)
    assert s.std() > 0.01 * w.w_ref
    assert np.all(s <= w.w_ref * (1 + 0.3 * 2.0)) and np.all(s >= w.w_ref * (1 - 0.3 * 2.0))
    # Тот же seed — тот же ветер.
    w2 = _weather("weather.enabled=true", "weather.initial=windy")
    assert np.array_equal(w2.wind_at(pos, np.zeros(4), 7.0), w.wind_at(pos, np.zeros(4), 7.0))


def test_rain_state_adds_force_and_extra_drag():
    sim = make_sim(*FLAT, "weather.enabled=true", "weather.initial=rain",
                   "wind.gust_harmonics=0")
    m = sim.module
    assert m.weather.rain
    s = m.spawn(0, "forager", np.array([20.0, 20.0, 5.0]))
    run_for(sim, 5.0)
    pos, _ = m.backend.body_state(np.array([s]))
    # Автопилот держит высоту в дождь (компенсирует силу дождя).
    assert pos[0, 2] == pytest.approx(5.0, abs=0.1)
    thrust = m.bees.thrust[s]
    weight = m.bees.mass[s] * m.gravity
    rain = m.params.physics.rain_force_coef * m.bees.radius[s] ** 2
    assert thrust[2] == pytest.approx(weight + rain, rel=0.05)
    assert rain == pytest.approx(0.1 * weight, rel=0.05)  # ≈10% веса (calibrate.py)


def test_forces_unit():
    vel = np.array([[2.0, 0.0, 0.0]])
    wind = np.array([[0.0, 1.0, 0.0]])
    d = forces.drag(vel, wind, np.array([0.5]))
    air = vel - wind
    assert np.allclose(d, -0.5 * np.linalg.norm(air) * air)
    walls = forces.boundary_force(
        np.array([[52.0, -10.0, 40.0], [0.0, 0.0, 5.0]]), np.array([5.0, 0.0]), np.ones(2),
        half_size=50.0, ceiling_agl=30.0, stiffness=2.0,
    )
    assert np.allclose(walls, [[-4.0, 0.0, -10.0], [0.0, 0.0, 0.0]])
    p = forces.power(np.array([[0.0, 0.0, 4.0]]), np.array([1.0]), np.array([0.5]))
    assert p[0] == pytest.approx(1.0 + 0.5 * 8.0)


def test_terrain_clearance_and_soft_walls():
    sim = make_sim("weather.enabled=false")
    m = sim.module
    s = m.spawn(0, "scout", np.array([0.0, 10.0, m.world.hive_entrance[0, 2] + 3.0]))
    # Цель за краем карты и ниже рельефа: автопилот обрежет её по карте и просвету.
    m.autopilot.fly_to(np.array([s]), np.array([[500.0, 10.0]]), agl=0.0)
    clear = []

    def watch(sim_):
        pos, _ = m.backend.body_state(np.array([s]))
        clear.append(pos[0, 2] - float(m.world.ground_height(pos[0, :2])) - m.bees.radius[s])

    run_for(sim, 25.0, watch)
    pos, _ = m.backend.body_state(np.array([s]))
    assert min(clear) > 0.5  # ни разу не задела рельеф
    assert pos[0, 0] <= m.world.half_size  # не вылетела за карту


def _load_calibrate():
    spec = importlib.util.spec_from_file_location("calibrate", ROOT / "tools" / "calibrate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibrate"] = mod  # dataclasses ищут модуль класса в sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_defaults_match_calibration_script():
    cal = _load_calibrate()
    defaults = yaml.safe_load((CONFIGS / "bees" / "defaults.yaml").read_text(encoding="utf-8"))
    result, k_rain = cal.calibrate(defaults)
    for kind, c in result.items():
        t = defaults["bee_types"][kind]
        for name in ("drag_coef", "energy_max", "power_idle", "power_coef"):
            assert t[name] == getattr(c, name), (kind, name)
        # Формулы целей.
        g = defaults["physics"]["gravity"]
        budget = np.sqrt(t["thrust_max"] ** 2 - (t["mass"] * g) ** 2)
        assert c.drag_coef * t["cruise_speed"] ** 2 == pytest.approx(budget, rel=1e-4)
        assert c.energy_max == pytest.approx(t["flight_time_s"] * c.power_cruise, rel=1e-4)
    assert defaults["physics"]["rain_force_coef"] == k_rain


def test_calibrate_write_roundtrip(tmp_path):
    cal = _load_calibrate()
    src = (CONFIGS / "bees" / "defaults.yaml").read_text(encoding="utf-8")
    path = tmp_path / "defaults.yaml"
    path.write_text(src.replace("drag_coef: 0.017112", "drag_coef: null    "), encoding="utf-8")
    assert cal.main(["--defaults", str(path), "--write"]) == 0
    assert path.read_text(encoding="utf-8") == src  # значения и комментарии на местах


def test_m1_swarm_is_deterministic_and_flies():
    def run():
        cfg = load_match(M1, cli_overrides=["duration_s=3"])
        sim = Simulation(cfg)
        sim.run()
        return sim

    a, b = run(), run()
    pa, _ = a.physics.poses()
    pb, _ = b.physics.poses()
    assert pa.tobytes() == pb.tobytes()
    m = a.module
    assert len(m.bees.airborne) == 300
    row = m.score().teams[0]
    counts = {k: row[k] for k in ("scout", "forager", "guard", "house", "alive")}
    assert counts == {"scout": 20.0, "forager": 60.0, "guard": 20.0, "house": 0.0, "alive": 100.0}
    _, vel = m.backend.body_state(m.bees.airborne)
    assert np.median(np.linalg.norm(vel, axis=1)) > 2.0  # рой разлетается по точкам


def test_cli_runs_m1_swarm(capsys):
    assert main(["run", str(M1), "--headless", "--duration", "1"]) == 0
    assert "RTF =" in capsys.readouterr().out
