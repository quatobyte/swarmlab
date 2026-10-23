"""Матч M3: детерминизм реплея demo.yaml, переключатели, счёт и выбывание, показ реплея."""

import numpy as np
import pytest

from swarmlab.bees.module import dequantize
from swarmlab.core.config import MatchConfig, load_match
from swarmlab.core.module import load_module
from swarmlab.core.replay import ReplayWriter, make_header, read_replay
from swarmlab.core.rng import RngRegistry
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS


def _run_with_replay(path, match, *overrides):
    cfg = load_match(CONFIGS / "matches" / match, cli_overrides=overrides)
    with Simulation(cfg) as sim:
        writer = ReplayWriter(path, make_header(cfg, sim.teams, sim.module.scene()))
        sim.on_frame = writer
        sim.run()
        digest = writer.close(sim.module.score())
        stats = list(sim.runners.stats.values()) if sim.runners else []
    return digest, writer, stats


# ------------------------------------------------------------------ детерминизм


def test_demo_twice_gives_same_replay_hash(tmp_path):
    """Критерий M3: demo.yaml дважды → одинаковый хеш (в тесте — первые 60 с матча)."""
    h1, w1, s1 = _run_with_replay(tmp_path / "a.swr", "demo.yaml", "duration_s=60")
    h2, _, s2 = _run_with_replay(tmp_path / "b.swr", "demo.yaml", "duration_s=60")
    print(f"хеш {h1}; кадров {w1.frames}; события {dict(w1.events)}")
    # Раннеры не пропускали тиков — иначе решения зависели бы от часов стены.
    assert all(s.missed == 0 and s.over_budget == 0 for s in s1 + s2)
    assert w1.frames == 600
    assert h1 == h2
    assert read_replay(tmp_path / "a.swr").hash_ok


# ------------------------------------------------------------------ переключатели в матче

#: Эффекты часто: шершни со 2-й секунды, все цветы с пауками, погода меняется раз в ~3 с.
_BUSY = (
    "enemies.hornets.first_wave_s=2", "enemies.hornets.wave_interval_s=3",
    "enemies.spiders.flower_fraction=1.0", "enemies.spiders.kill_prob_per_s=0.5",
    "weather.mean_duration_s=3", "duration_s=30",
)


@pytest.mark.parametrize("off", [None, "enemies.hornets", "enemies.spiders", "weather"])
def test_enabled_false_removes_effect_completely(tmp_path, off):
    extra = (f"{off}.enabled=false",) if off else ()
    cfg = load_match(CONFIGS / "matches" / "m2_economy.yaml",
                     cli_overrides=(*_BUSY, "enemies.hornets.enabled=true",
                                    "enemies.spiders.enabled=true", *extra))
    events = []
    wind_seen = 0.0
    with Simulation(cfg, on_frame=lambda f: events.extend(f.events)) as sim:
        m = sim.module
        while not sim.finished:
            sim.run(max_steps=200)
            wind_seen = max(wind_seen, float(np.abs(m._wind).max()))
    types = {e["type"] for e in events}
    causes = {e.get("cause") for e in events if e["type"] == "death"}
    hornets = bool(types & {"hornet_spawn", "attack", "heat_ball", "rob"})
    print(f"выключено {off}: события {sorted(types)}, причины гибели {causes}, "
          f"ветер до {wind_seen:.2f} м/с")
    assert hornets == (off != "enemies.hornets")
    assert ("spider" in causes) == (off != "enemies.spiders")
    assert ("weather" in types) == (off != "weather")
    if off == "enemies.hornets":
        assert m.enemies.n == 0 and m.backend.n_bodies == m.bees.n
    if off == "enemies.spiders":
        assert not m.world.flower_spider.any() and m.enemies.bite_rolls == 0
    if off == "weather":
        assert wind_seen == 0.0 and m.weather.state == "clear"


# ------------------------------------------------------------------ счёт и выбывание


def _kill_everyone(m, hive):
    b = m.bees
    sl = b.hive_slots(hive)
    alive = np.arange(sl.start, sl.stop)[b.state[sl] != 0]
    if alive.size:
        m.kill(alive, "test")
    m.economy.house_alive[m.economy.house_slots(hive)] = False


def test_places_winner_and_early_finish():
    cfg = load_match(
        CONFIGS / "matches" / "demo.yaml",
        cli_overrides=(
            "hives=[{script: examples/bees/example_basic.py}, "
            "{script: examples/bees/example_basic.py}, {color: '#ffffff'}]",
            "enemies.hornets.enabled=false",
        ),
    )
    with Simulation(cfg) as sim:
        m = sim.module
        m.economy.honey[:] = [30.0, 10.0, 99.0]
        board = m.score()
        assert board.teams[0]["place"] == 1 and board.teams[1]["place"] == 2
        assert board.teams[2]["place"] == 0  # улей без скрипта не участвует
        assert board.winner == 0
        assert not sim.finished

        _kill_everyone(m, 0)
        events = []
        sim.on_frame = lambda f: events.extend(f.events)
        sim.run(max_steps=40)
        out = [e for e in events if e["type"] == "eliminated"]
        assert [e["hive"] for e in out] == [0]
        board = m.score()
        assert board.teams[0]["eliminated"] == 1 and board.teams[0]["place"] == 2
        assert board.winner == 1
        assert sim.finished  # остался один улей — матч окончен досрочно
        assert sim.time < cfg.duration_s


def test_no_flying_bees_and_no_honey_eliminates_single_hive():
    cfg = load_match(CONFIGS / "matches" / "m2_economy.yaml",
                     cli_overrides=("duration_s=60",))
    with Simulation(cfg) as sim:
        m = sim.module
        b = m.bees
        sl = b.hive_slots(0)
        m.kill(np.arange(sl.start, sl.stop)[b.state[sl] != 0], "test")  # домашние живы
        m.economy.honey[0] = 2.5  # дешевле любой летающей пчелы (разведчик — 3)
        sim.run(max_steps=40)
        assert m.score().teams[0]["eliminated"] == 1
        assert sim.finished


# ------------------------------------------------------------------ показ реплея


def test_replay_frame_restores_body_positions(tmp_path):
    """Кадр реплея → тела модели там же, где были в матче (с точностью квантования)."""
    cfg = load_match(CONFIGS / "matches" / "m1_swarm.yaml",
                     cli_overrides=("duration_s=3", "profile=small",
                                    "demo.swarm.per_hive={scout: 5, forager: 10, guard: 5}"))
    truth = {}
    with Simulation(cfg) as sim:
        m = sim.module
        writer = ReplayWriter(tmp_path / "r.swr", make_header(cfg, sim.teams, m.scene()))

        def on_frame(frame):
            a = m.bees.airborne
            truth[frame.tick] = (a.copy(), m.backend.body_state(a)[0].copy())
            writer(frame)

        sim.on_frame = on_frame
        sim.run()
        writer.close(m.score())

    rp = read_replay(tmp_path / "r.swr")
    scene = rp.header["scene"]
    lo, hi = scene["pos_lo"], scene["pos_hi"]
    step = (hi - lo) / 65535
    frame = rp.frames[-1]
    slots, pos = truth[frame.tick]
    assert np.array_equal(frame.arrays["bee_slot"], slots)
    err = np.abs(dequantize(frame.arrays["bee_pos"], lo, hi) - pos)
    assert np.all(err <= step / 2 + 1e-9)
    assert step.max() < 0.005  # шаг меньше 5 мм

    # Тот же мир по seed из заголовка, тела — по кадру.
    cfg2 = MatchConfig.model_validate(rp.header["config"])
    module = load_module(cfg2.module)
    module.build(cfg2, RngRegistry(cfg2.seed))
    assert module.scene()["world_digest"] == scene["world_digest"]
    module.apply_frame(frame)
    placed, _ = module.backend.body_state(slots)
    assert np.allclose(placed, pos, atol=step.max())
    # Интерполяция к следующему кадру — посередине.
    prev = rp.frames[-2]
    module.apply_frame(prev, frame, 0.5)
    both = np.intersect1d(prev.arrays["bee_uid"], frame.arrays["bee_uid"])
    i = np.flatnonzero(np.isin(frame.arrays["bee_uid"], both))
    j = np.flatnonzero(np.isin(prev.arrays["bee_uid"], both))
    mid = 0.5 * (dequantize(prev.arrays["bee_pos"][j], lo, hi)
                 + dequantize(frame.arrays["bee_pos"][i], lo, hi))
    got, _ = module.backend.body_state(prev.arrays["bee_slot"][j].astype(np.int64))
    assert np.allclose(got, mid, atol=1e-9)


# ------------------------------------------------------------------ гибели по причинам (M7c)


def test_deaths_by_cause_in_score_match_death_events(tmp_path):
    """Критерий M7c: гибели в счёте (энергия / шершень / паук) = события `death` реплея.

    Разведчики с малым запасом энергии падают, цветы с пауками кусают сборщиков, а
    шершня тест ставит вплотную к пчёлам в воздухе (волна сама до них не долетела бы).
    """
    cfg = load_match(CONFIGS / "matches" / "m2_economy.yaml", cli_overrides=(
        *_BUSY, "enemies.hornets.enabled=true", "enemies.hornets.first_wave_s=1e9",
        "enemies.spiders.enabled=true", "bee_types.scout.energy_max=40"))
    path = tmp_path / "d.swr"
    with Simulation(cfg) as sim:
        m = sim.module
        writer = ReplayWriter(path, make_header(cfg, sim.teams, m.scene()))
        sim.on_frame = writer
        while not sim.finished:
            sim.run(max_steps=sim.clock.steps_for(3.0))
            air = m.bees.airborne
            if air.size and m.enemies.alive.sum() < 2:
                pos, _ = m.backend.body_state(air[:1])
                m.enemies.spawn(pos[0] + np.array([1.5, 0.0, 0.0]))
        writer.close(m.score())
    rp = read_replay(path)
    counted: dict[tuple[int, str], int] = {}
    for f in rp.frames:
        for e in f.events:
            if e["type"] == "death":
                key = (e["hive"], e["cause"])
                counted[key] = counted.get(key, 0) + 1
    print(f"гибели по событиям: {counted}")
    teams = rp.footer["score"]["teams"]
    for cause in ("energy", "hornet", "spider"):
        assert any(c == cause for _, c in counted), f"в матче нет гибелей «{cause}»"
        for hive, row in teams.items():
            assert row[f"deaths_{cause}"] == counted.get((int(hive), cause), 0), (hive, cause)
