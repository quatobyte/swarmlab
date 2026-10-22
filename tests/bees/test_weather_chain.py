"""Погода M3 (BEES_SPEC §6): марковская цепь и переключатели."""

import numpy as np
import pytest

from swarmlab.bees.weather import Weather
from swarmlab.core.rng import RngRegistry

from .helpers import bees_params, make_sim, run_for


def _weather(*overrides, seed=42):
    p = bees_params(overrides=("weather.enabled=true", *overrides))
    rng = RngRegistry(seed)
    return Weather(p.weather, p.wind, rng.get("weather"), rng.get("weather.chain"))


def _durations(w, dt=0.1, steps=200_000):
    """Длительности состояний цепи (без первого и последнего, они обрезаны)."""
    out, since, states = [], 0.0, {w.state}
    for i in range(steps):
        if w.update(dt) is not None:
            out.append((i + 1) * dt - since)
            since = (i + 1) * dt
            states.add(w.state)
    return np.array(out[1:]), states


def test_mean_state_duration_close_to_90_s():
    w = _weather()
    durations, states = _durations(w)
    print(f"смен {durations.size}, средняя длительность {durations.mean():.1f} с")
    assert states == {"clear", "windy", "rain"}
    assert durations.size > 150
    assert durations.mean() == pytest.approx(90.0, rel=0.15)


def test_new_state_draws_wind_from_its_range():
    w = _weather()
    p = w.params
    for _ in range(50_000):
        if w.update(0.1) is not None:
            lo, hi = p.states[w.state].wind
            assert lo <= w.w_ref <= hi
            assert w.rain == p.states[w.state].rain


def test_rain_switch_off_never_rains():
    w = _weather("weather.rain=false", "weather.initial=rain")
    assert w.state == "clear" and not w.rain
    _, states = _durations(w, steps=50_000)
    assert states == {"clear", "windy"}


def test_wind_switch_off_keeps_air_calm():
    w = _weather("weather.wind=false", "weather.initial=windy")
    assert w.w_ref == 0.0
    for _ in range(20_000):
        w.update(0.1)
        assert w.w_ref == 0.0
    pos = np.array([[10.0, 5.0, 8.0]])
    assert np.all(w.wind_at(pos, np.zeros(1), 100.0) == 0.0)


def test_weather_disabled_no_chain_no_wind_no_events():
    sim = make_sim("weather.enabled=false", "weather.mean_duration_s=0.5",
                   "weather.initial=rain")
    m = sim.module
    s = m.spawn(0, "scout")
    events = []
    for _ in range(round(10.0 / sim.clock.dt)):
        sim.step()
        if sim.clock.is_decision_step:
            events += m.snapshot().events
            assert m.weather.state == "clear" and not m.weather.rain
            assert np.all(m._wind[s] == 0.0)
    assert not [e for e in events if e["type"] == "weather"]


def test_weather_changes_are_events_in_match():
    sim = make_sim("weather.enabled=true", "weather.mean_duration_s=2.0")
    m = sim.module
    events = []
    for _ in range(round(10.0 / sim.clock.dt)):
        sim.step()
        if sim.clock.is_decision_step:
            events += m.snapshot().events
    changes = [e for e in events if e["type"] == "weather"]
    assert len(changes) >= 2
    assert all(e["state"] != e["prev"] for e in changes)
    assert changes[-1]["state"] == m.weather.state


def test_chain_is_deterministic_by_seed():
    a, b = make_sim("weather.enabled=true", "weather.mean_duration_s=1.0"), make_sim(
        "weather.enabled=true", "weather.mean_duration_s=1.0"
    )
    run_for(a, 5.0)
    run_for(b, 5.0)
    assert a.module.weather.state == b.module.weather.state
    assert a.module.weather.w_ref == b.module.weather.w_ref
