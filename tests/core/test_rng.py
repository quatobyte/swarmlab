import numpy as np
import pytest

from swarmlab.core.rng import RngRegistry


def test_same_seed_same_stream():
    a = RngRegistry(7).get("world").random(5)
    b = RngRegistry(7).get("world").random(5)
    assert np.array_equal(a, b)


def test_different_seed_or_name_differs():
    base = RngRegistry(7).get("world").random(5)
    assert not np.array_equal(base, RngRegistry(8).get("world").random(5))
    assert not np.array_equal(base, RngRegistry(7).get("weather").random(5))


def test_new_stream_does_not_shift_others():
    r1 = RngRegistry(3)
    w1 = r1.get("world").random(4)
    r2 = RngRegistry(3)
    r2.get("enemies").random(100)  # новая подсистема, использованная раньше
    w2 = r2.get("world").random(4)
    assert np.array_equal(w1, w2)


def test_get_returns_same_generator_and_fresh_restarts():
    r = RngRegistry(1)
    g = r.get("x")
    first = g.random()
    assert r.get("x") is g
    assert r.fresh("x").random() == first


def test_negative_seed_rejected():
    with pytest.raises(ValueError):
        RngRegistry(-1)
