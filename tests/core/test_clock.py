import pytest

from swarmlab.core.clock import Clock, Rates, RealtimePacer


def test_decision_and_frame_steps():
    c = Clock(Rates(physics_hz=200, decision_hz=10, frame_hz=20))
    decisions, frames = [], []
    for _ in range(100):
        if c.is_decision_step:
            decisions.append(c.step)
        if c.is_frame_step:
            frames.append(c.step)
        c.advance()
    assert decisions == [0, 20, 40, 60, 80]
    assert frames == list(range(0, 100, 10))


def test_time_does_not_drift():
    c = Clock(Rates())
    for _ in range(200 * 3600):
        c.advance()
    assert c.time == 3600.0
    assert c.decision_tick == 36000


def test_rates_must_divide_physics():
    with pytest.raises(ValueError):
        Rates(physics_hz=200, decision_hz=30)


def test_pacer_accumulates_and_caps_lag():
    p = RealtimePacer(dt=0.005, max_lag_s=0.25)
    assert p.steps_due(0.012) == 2  # 0.012 → 2 шага, 0.002 в остатке
    assert p.steps_due(0.004) == 1  # 0.002 + 0.004 → 1 шаг
    assert p.steps_due(10.0) == 50  # после паузы — не больше max_lag_s
    assert RealtimePacer(dt=0.005, speed=2.0).steps_due(0.01) == 4
