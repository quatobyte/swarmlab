"""Матч M2: `example_basic.py` headless 120 с увеличивает мёд; мёд не берётся из воздуха."""

import numpy as np
import pytest

from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS


def test_example_basic_grows_honey_and_honey_invariant_holds():
    cfg = load_match(CONFIGS / "matches" / "m2_economy.yaml")
    assert cfg.duration_s == 120
    worst = -np.inf
    with Simulation(cfg) as sim:
        e = sim.module.economy
        start = float(e.honey[0])
        while not sim.finished:
            sim.step()
            if sim.clock.is_decision_step:
                worst = max(worst, float(np.max(e.honey - e.honey_bound())))
        stats = sim.runners.stats[0]
        honey = float(e.honey[0])
        print(
            f"мёд {start:.2f} → {honey:.2f}, доставлено {e.delivered[0]:.2f}, "
            f"переработано {e.processed[0]:.2f}, запас инварианта {-worst:.3f}"
        )
    assert honey > start
    assert e.delivered[0] > 0 and e.processed[0] > 0
    assert worst <= 1e-9  # мёд ≤ старт + 0.5·переработанный нектар на каждом тике
    assert stats.missed == 0 and stats.agent_errors == 0 and stats.over_budget == 0


@pytest.mark.parametrize("script", ["template.py", "example_smart.py"])
def test_other_examples_run_without_errors(script):
    cfg = load_match(
        CONFIGS / "matches" / "m2_economy.yaml",
        # Погода как в M2 — весь матч clear (с M3 цепь может включить ветер за 30 с).
        cli_overrides=(
            f"hives=[{{script: examples/bees/{script}}}]", "duration_s=30",
            "weather.mean_duration_s=1e9",
        ),
    )
    with Simulation(cfg) as sim:
        sim.run()
        stats = sim.runners.stats[0]
        log = sim.runners.logs[0].text()
        assert stats.load_error is None, stats.load_error
        assert stats.agent_errors == 0 and stats.missed == 0, log
        assert sim.module.economy.delivered[0] > 0
