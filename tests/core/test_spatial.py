import numpy as np
import pytest

from swarmlab.core.spatial import UniformGrid, expand


def test_expand():
    owner, local = expand(np.array([2, 0, 3]))
    assert owner.tolist() == [0, 0, 2, 2, 2]
    assert local.tolist() == [0, 1, 0, 1, 2]


def _brute(q, p, r, exclude_self):
    d = np.linalg.norm(p[None, :, :] - q[:, None, :], axis=-1)
    hit = d <= r[:, None]
    if exclude_self:
        np.fill_diagonal(hit, False)
    qi, pj = np.nonzero(hit)
    return set(zip(qi.tolist(), pj.tolist(), strict=True))


@pytest.mark.parametrize("cell", [1.0, 5.0, 40.0])
def test_within_matches_brute_force(cell):
    rng = np.random.default_rng(1)
    # Часть точек — за пределами карты: они должны находиться так же.
    p = np.column_stack([rng.uniform(-60, 60, (400, 2)), rng.uniform(0, 20, 400)])
    r = rng.uniform(0.5, 15.0, 400)
    grid = UniformGrid(50.0, cell)
    grid.build(p)
    pairs = grid.within(p, r, exclude_self=True)
    got = set(zip(pairs.query.tolist(), pairs.point.tolist(), strict=True))
    assert got == _brute(p, p, r, True)
    # Отсортировано по запросу, delta и dist согласованы.
    assert np.all(np.diff(pairs.query) >= 0)
    assert np.allclose(pairs.delta, p[pairs.point] - p[pairs.query])
    assert np.allclose(pairs.dist, np.linalg.norm(pairs.delta, axis=1))


def test_queries_differ_from_points_and_empty():
    grid = UniformGrid(10.0, 2.0)
    grid.build(np.zeros((0, 3)))
    assert len(grid.within(np.zeros((3, 3)), 5.0)) == 0
    pts = np.array([[0.0, 0.0], [3.0, 0.0], [9.0, 9.0]])
    grid.build(pts)
    pairs = grid.within(np.array([[0.5, 0.0]]), 2.6)
    assert pairs.point.tolist() == [0, 1]
    assert pairs.counts(1).tolist() == [2]


def test_deterministic_order():
    rng = np.random.default_rng(3)
    p = rng.uniform(-20, 20, (200, 3))
    a, b = UniformGrid(20.0, 3.0), UniformGrid(20.0, 3.0)
    a.build(p)
    b.build(p.copy())
    pa, pb = a.within(p, 6.0), b.within(p, 6.0)
    assert np.array_equal(pa.query, pb.query) and np.array_equal(pa.point, pb.point)
