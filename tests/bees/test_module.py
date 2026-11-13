import numpy as np

from swarmlab.bees.module import BeesModule
from swarmlab.bees.state import FLYING
from swarmlab.core.config import load_match
from swarmlab.core.module import DebugViewable, Module, load_module
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS


def _sim(seconds: float, **kw) -> Simulation:
    cfg = load_match(CONFIGS / "matches" / "m0.yaml", cli_overrides=[f"duration_s={seconds}"])
    return Simulation(cfg, **kw)


def test_module_is_discoverable_by_name():
    m = load_module("bees")
    assert isinstance(m, BeesModule)
    assert isinstance(m, Module)
    assert isinstance(m, DebugViewable)


def test_demo_bee_visits_waypoints():
    sim = _sim(60.0)
    sim.run()
    assert sim.module.pilot.visits[0] >= 4  # облетела несколько точек маршрута


def test_simulation_is_deterministic():
    a, b = _sim(10.0), _sim(10.0)
    assert a.module.world.digest() == b.module.world.digest()
    a.run()
    b.run()
    pa, qa = a.physics.poses()
    pb, qb = b.physics.poses()
    assert pa.tobytes() == pb.tobytes() and qa.tobytes() == qb.tobytes()


def test_frames_emitted_at_frame_rate():
    frames = []
    sim = _sim(2.0, on_frame=frames.append)
    sim.run()
    assert len(frames) == 20  # 10 Гц × 2 с
    arrays = frames[-1].arrays
    assert arrays["bee_pos"].shape == (1, 3)  # в кадре только тела в воздухе — одна демо-пчела
    assert arrays["bee_pos"].dtype == np.uint16
    assert np.count_nonzero(arrays["bee_state"] == FLYING) == 1
    assert frames[0].events[0]["type"] == "birth"
    assert np.isclose(frames[-1].time, 2.0)
