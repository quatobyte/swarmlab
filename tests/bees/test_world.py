import numpy as np
import pytest

from swarmlab.bees.world import generate_world
from swarmlab.core.rng import RngRegistry

from .helpers import bees_params


def _world(seed: int, profile: str = "medium", **kw):
    p = bees_params(profile)
    return generate_world(p.world, RngRegistry(seed), **kw)


def test_same_seed_same_world():
    a, b = _world(42), _world(42)
    assert a.digests() == b.digests()
    assert a.digest() == b.digest()


def test_different_seed_different_world():
    a, b = _world(42), _world(43)
    da, db = a.digests(), b.digests()
    for group in ("terrain", "obstacles", "flowers"):
        assert da[group] != db[group], group
    assert a.digest() != b.digest()


def test_world_contents_medium():
    w = _world(1)
    assert w.terrain.shape == (128, 128)
    assert w.terrain.min() == pytest.approx(0.0)
    assert w.terrain.max() == pytest.approx(8.0)
    assert w.n_hives == 3
    # Ульи — треугольник со стороной ~150 м.
    d = np.linalg.norm(w.hive_pos[:, None, :2] - w.hive_pos[None, :, :2], axis=-1)
    assert np.allclose(d[~np.eye(3, dtype=bool)], 150.0)
    assert len(w.tree_pos) == round(7.0 * 9)  # 7 деревьев/га × 9 га
    half = w.half_size
    for arr in (w.tree_pos, w.rock_pos, w.flower_pos, w.hive_pos):
        assert np.all(np.abs(arr[:, :2]) <= half)


def test_obstacles_keep_away_from_hives():
    w = _world(5)
    for pos in (w.tree_pos, w.rock_pos):
        d = np.linalg.norm(pos[:, None, :2] - w.hive_pos[None, :, :2], axis=-1)
        assert d.min() >= 15.0


def test_flowers_fair_between_hives():
    w = _world(9)
    counts = np.bincount(w.flower_hive, minlength=w.n_hives)
    assert np.all(counts == counts[0]) and counts[0] > 0
    # Среднее расстояние цветов до своего улья сопоставимо (±20%).
    mean_d = [
        np.linalg.norm(w.flower_pos[w.flower_hive == h, :2] - w.hive_pos[h, :2], axis=1).mean()
        for h in range(w.n_hives)
    ]
    assert max(mean_d) / min(mean_d) < 1.2


def test_flowers_sit_on_terrain():
    w = _world(2)
    assert np.allclose(w.flower_pos[:, 2] - w.ground_height(w.flower_pos[:, :2]), 0.3)


def test_spiders_do_not_change_rest_of_world():
    plain = _world(4)
    spiders = _world(4, spiders_enabled=True, spider_fraction=0.1)
    assert spiders.flower_spider.sum() == round(0.1 * len(spiders.flower_pos))
    a, b = plain.digests(), spiders.digests()
    assert a["terrain"] == b["terrain"] and a["obstacles"] == b["obstacles"]


def test_ground_height_at_nodes():
    w = _world(3)
    n = w.terrain.shape[0]
    xs = np.linspace(-w.half_size, w.half_size, n)
    iy, ix = 17, 101
    assert w.ground_height(np.array([xs[ix], xs[iy]])) == pytest.approx(w.terrain[iy, ix])
