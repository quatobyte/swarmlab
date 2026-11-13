"""Враги (BEES_SPEC §7): пауки и переключатели. Шершней нет (DECISIONS №82)."""

import math

import numpy as np

from .helpers import CALM, make_sim, run_for


def _events(sim, seconds, types=None):
    out = []
    steps = round(seconds / sim.clock.dt)
    for _ in range(steps):
        sim.step()
        if sim.clock.is_decision_step:
            out += sim.module.snapshot().events
    return [e for e in out if types is None or e["type"] in types]


# ------------------------------------------------------------------ пауки


def _forager_on_flowers(sim, n):
    """`n` сборщиков сразу над разными цветками в режиме `collect`."""
    from swarmlab.bees.control import COLLECT

    m = sim.module
    flowers = np.arange(n)
    slots = []
    for f in flowers.tolist():
        s = m.spawn(0, "forager", m.world.flower_pos[f] + np.array([0.0, 0.0, 1.0]))
        m.control.mode[s] = COLLECT
        m.control.target[s] = f
        slots.append(s)
    return np.array(slots)


def test_spider_deaths_match_expected_rate_fixed_seed():
    """Статистика пауков: число гибелей ≈ сумма вероятностей укусов (±3σ), seed фиксирован."""
    sim = make_sim(
        *CALM, "enemies.spiders.enabled=true", "enemies.spiders.flower_fraction=1.0",
        "pool.max_bees_per_hive=60", seed=7,
    )
    m = sim.module
    n = 48
    slots = _forager_on_flowers(sim, n)
    uids = set(m.bees.uid[slots].tolist())
    events = _events(sim, 12.0)
    deaths = [e for e in events if e["type"] == "death" and e["bee"] in uids]
    assert all(e["cause"] == "spider" for e in deaths)
    en = m.enemies
    p = m.params.enemies.spiders.kill_prob_per_s
    p_tick = 1 - (1 - p) ** m._decision_dt
    expected = en.bite_hazard
    sigma = math.sqrt(en.bite_rolls * p_tick * (1 - p_tick))
    exposure = en.bite_rolls * m._decision_dt  # секунд сбора на цветках с пауком
    # Та же величина через «0.15 в секунду»: ожидаемая доля погибших за время сбора.
    per_bee = exposure / n
    print(
        f"сборщиков {n}, бросков {en.bite_rolls}, сбор {exposure:.1f} с ({per_bee:.2f} с на "
        f"пчелу), погибло {len(deaths)}, ожидалось {expected:.1f} ± {sigma:.1f}"
    )
    assert en.bite_rolls > 500
    assert abs(len(deaths) - expected) <= 3 * sigma
    # Сбор до полного груза — 4 с, гибель за это время ≈ 1 − 0.85^4 ≈ 48%.
    frac = len(deaths) / n
    assert 0.25 <= frac <= 0.70


def test_spiders_disabled_no_spider_flowers_no_deaths():
    sim = make_sim(
        *CALM, "enemies.spiders.enabled=false", "enemies.spiders.flower_fraction=1.0",
        "enemies.spiders.kill_prob_per_s=1.0",
    )
    m = sim.module
    assert not m.world.flower_spider.any()
    _forager_on_flowers(sim, 10)
    events = _events(sim, 6.0)
    assert not [e for e in events if e["type"] == "death"]
    assert m.enemies.bite_rolls == 0


def test_no_hornets_bodies_scene_or_enemy_sensors():
    """Шершней нет: в модели только тела пчёл, в сцене и кадре — ни следа, сенсора врагов нет."""
    sim = make_sim(*CALM)
    m = sim.module
    assert m.backend.n_bodies == m.bees.n
    scene = m.scene()
    assert not [k for k in scene if "hornet" in k]
    assert scene["kinds"] == ["scout", "forager"]
    assert scene["hive_counts"] == ["scout", "forager", "house", "in_hive"]
    s = m.spawn(0, "scout")
    run_for(sim, 0.2)
    frame = m.snapshot()
    assert not [k for k in frame.arrays if "hornet" in k]
    assert frame.arrays["hive_counts"].shape[1] == len(scene["hive_counts"])
    row = next(r for r in m.hive_sensors(0) if r["me"]["id"] == int(m.bees.uid[s]))
    assert "enemies" not in row
