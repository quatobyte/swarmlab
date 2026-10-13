import mujoco
import numpy as np
import pytest

from swarmlab.bees.physics.backend import MujocoBackend
from swarmlab.bees.physics.mjcf import BodySlot, build_mjcf
from swarmlab.bees.world import generate_world
from swarmlab.core.physics import STATIC, PhysicsBackend
from swarmlab.core.rng import RngRegistry

from .helpers import bees_params


@pytest.fixture(scope="module")
def world():
    return generate_world(bees_params("small").world, RngRegistry(11))


def _backend(world, slots):
    xml = build_mjcf(world, slots, timestep=0.005, gravity=9.81)
    return MujocoBackend(xml, [s.name for s in slots], angular_damping=0.002)


def test_backend_satisfies_contract(world):
    b = _backend(world, [BodySlot("bee0", 0.25, 0.08, (0.0, 5.0, 20.0))])
    assert isinstance(b, PhysicsBackend)
    pos, quat = b.poses()
    assert pos.shape == (1, 3) and quat.shape == (1, 4)
    assert b.velocities().shape == (1, 6)


def test_heightfield_matches_world_terrain(world):
    """Рельеф MuJoCo совпадает с массивом мира (проверка ориентации heightfield)."""
    b = _backend(world, [])
    n = world.terrain.shape[0]
    xs = np.linspace(-world.half_size, world.half_size, n)
    rng = np.random.default_rng(0)
    geom = np.zeros(1, np.int32)
    tid = mujoco.mj_name2id(b.model, mujoco.mjtObj.mjOBJ_GEOM, "terrain")
    for iy, ix in rng.integers(1, n - 1, (40, 2)):
        x, y = xs[ix], xs[iy]
        dist = mujoco.mj_ray(
            b.model, b.data, np.array([x, y, 50.0]), np.array([0, 0, -1.0]), None, 1, -1, geom
        )
        if geom[0] != tid:
            continue  # луч попал в дерево/камень
        assert 50.0 - dist == pytest.approx(world.terrain[iy, ix], abs=1e-3)


def test_thrust_equal_to_weight_hovers(world):
    m = 0.08
    b = _backend(world, [BodySlot("bee0", 0.25, m, (0.0, 5.0, 20.0))])
    b.set_forces(np.array([0]), np.array([[0.0, 0.0, m * 9.81]]))
    b.step(200)
    assert np.linalg.norm(b.velocities()[0, :3]) < 1e-6


def test_contacts_and_parking(world):
    xy = np.array([10.0, 10.0])
    z = float(world.ground_height(xy)) + 2.0
    b = _backend(world, [BodySlot("bee0", 0.25, 0.08, (xy[0], xy[1], z))])
    b.step(400)  # падает на землю
    c = b.contacts()
    assert len(c) >= 1
    assert STATIC in set(c.body_a) | set(c.body_b)
    assert 0 in set(c.body_a) | set(c.body_b)
    assert np.all(c.normal_force >= 0)

    b.set_active(np.array([0]), np.array([False]))
    b.step(400)
    assert len(b.contacts()) == 0
    assert b.poses()[0][0, 2] < world.ground_height(xy) - 1.0  # провалилась — столкновений нет
