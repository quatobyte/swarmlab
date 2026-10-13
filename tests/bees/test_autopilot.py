"""Автопилот: точность прибытия и отсутствие колебаний (критерий приёмки M0)."""

import numpy as np
import pytest

from swarmlab.bees.autopilot import Autopilot, clip_norm, limit_thrust
from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS, bees_params


def test_limit_thrust_vertical_priority():
    t = np.array([[3.0, 4.0, 1.0], [10.0, 0.0, 2.0], [1.0, 0.0, -5.0], [0.0, 0.0, 9.0]])
    tmax = np.array([10.0, 2.0, 3.0, 3.0])
    out = limit_thrust(t, tmax)
    assert np.allclose(out[0], t[0])  # укладывается — не трогаем
    assert np.allclose(out[1], [0.0, 0.0, 2.0])  # вся тяга ушла на вертикаль
    assert np.allclose(out[2], [1.0, 0.0, 0.0])  # тяга вниз запрещена
    assert np.allclose(out[3], [0.0, 0.0, 3.0])
    assert np.all(np.linalg.norm(out, axis=1) <= tmax + 1e-12)


def test_clip_norm():
    v = np.array([[3.0, 4.0, 0.0], [0.3, 0.4, 0.0]])
    assert np.allclose(clip_norm(v, np.array([1.0, 1.0])), [[0.6, 0.8, 0], [0.3, 0.4, 0]])


def test_reference_follows_terrain_and_clearance():
    p = bees_params().autopilot
    ground = lambda xy: np.full(len(xy), 2.0)  # noqa: E731
    ap = Autopilot(2, p, gravity=9.81, ground=ground, map_half_size=50, ceiling_agl=30)
    ap.fly_to(np.array([0, 1]), np.array([[10.0, 0.0], [100.0, 0.0]]), agl=4.0, speed=5.0)
    ap.fly_to(np.array([1]), np.array([[100.0, 0.0]]), z=np.array([0.5]), speed=5.0)
    ref = ap.reference(np.zeros((2, 3)))
    assert ref[0].tolist() == [10.0, 0.0, 6.0]  # 4 м над рельефом
    assert ref[1].tolist() == [49.0, 0.0, 3.5]  # цель обрезана картой, просвет 1.5 м


def _flight(kind_targets: list[tuple[str, list[float]]], seconds: float = 25.0):
    """Матч M0, в котором демо-пчёлы летят в одну точку каждая и зависают."""
    bees = [
        {"kind": k, "hive": 0, "waypoints": [wp], "loop": False, "dwell_s": 0.0}
        for k, wp in kind_targets
    ]
    cfg = load_match(
        CONFIGS / "matches" / "m0.yaml",
        cli_overrides=[f"demo.bees={bees}", f"duration_s={seconds}"],
    )
    sim = Simulation(cfg)
    m = sim.module
    entrance = m.world.hive_entrance[0, :2]
    targets = []
    for _, (dx, dy, agl) in kind_targets:
        xy = entrance + np.array([dx, dy])
        targets.append([xy[0], xy[1], float(m.world.ground_height(xy)) + agl])
    targets = np.array(targets)
    start = sim.physics.poses()[0].copy()
    traj, speed = [], []
    while not sim.finished:
        sim.step()
        pos = sim.physics.poses()[0]
        traj.append(pos.copy())
        speed.append(np.linalg.norm(sim.physics.velocities()[:, :3], axis=1))
    return start, targets, np.array(traj), np.array(speed)


@pytest.mark.parametrize(
    "targets",
    [
        [("forager", [30.0, 20.0, 8.0])],
        # Векторно: три типа пчёл одновременно, у каждой своя цель.
        [
            ("scout", [40.0, -10.0, 6.0]),
            ("forager", [-20.0, 25.0, 10.0]),
            ("guard", [5.0, 5.0, 3.0]),
        ],
    ],
)
def test_bee_reaches_target_without_oscillation(targets):
    start, target, traj, speed = _flight(targets)
    for b in range(len(targets)):
        dist = np.linalg.norm(traj[:, b] - target[b], axis=1)
        arrived = np.flatnonzero(dist <= 0.5)
        assert arrived.size, f"пчела {b} не долетела: минимум {dist.min():.2f} м"
        after = traj[arrived[0] :, b]
        # Достигла цели с точностью 0.5 м и осталась там.
        assert dist[-1] <= 0.5
        assert np.max(np.linalg.norm(after - target[b], axis=1)) <= 0.5
        # Перелёт вдоль направления подлёта не больше 0.3 м.
        approach = (target[b] - start[b]) / np.linalg.norm(target[b] - start[b])
        overshoot = np.max((traj[:, b] - target[b]) @ approach)
        assert overshoot <= 0.3, f"перелёт {overshoot:.2f} м"
        # После прибытия пчела «стоит»: размах положения ≤ 0.3 м, скорость в конце ≈ 0.
        assert np.ptp(after, axis=0).max() <= 0.3 + 0.5  # с учётом дотягивания с 0.5 м до цели
        settled = traj[-200:, b]  # последняя секунда
        assert np.ptp(settled, axis=0).max() <= 0.3
        assert speed[-1, b] < 0.05
