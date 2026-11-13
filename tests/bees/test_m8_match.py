"""M8 в настоящем матче: раннер в отдельном процессе, модуль, физика (DECISIONS №84–88)."""

import json
import math
import struct
import textwrap
from pathlib import Path

import numpy as np
import pytest
import zstandard

from swarmlab.bees.state import FLYING, IN_HIVE
from swarmlab.core.config import load_match
from swarmlab.core.replay import MAGIC, ReplayError, pack, read_replay
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS, FLAT, make_sim, run_for

#: Стартовый состав: uid 0–4 разведчики, 5–19 сборщики, 20–29 домашние.
FIRST_FORAGER = 5


def script_sim(tmp_path: Path, code: str, *overrides: str, duration: float = 600.0):
    script = tmp_path / "player.py"
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    cfg = load_match(
        CONFIGS / "matches" / "m2_economy.yaml",
        cli_overrides=(
            f"hives=[{{script: '{script.as_posix()}'}}]",
            f"duration_s={duration}",
            "weather.enabled=false",
            "enemies.spiders.enabled=false",
            *FLAT,
            *overrides,
        ),
    )
    return Simulation(cfg)


def results(sim) -> dict[str, str]:
    """Строки `R имя значение` из лога игрока → {имя: значение}."""
    out = {}
    for line in sim.runners.logs[0].text().splitlines():
        if line.startswith("R "):
            _, name, value = line.split(" ", 2)
            out[name] = value
    return out


# ===================================================================== возвраты команд

COMMANDS = """
    import json
    from pathlib import Path
    from swarmlab.bees.api import Collector, Hive, Point, Scout, Flower, Worker

    TESTER = []
    W = {}

    def r(name, value):
        print("R", name, value)

    class Idle(Scout):
        def loop(self):
            self.wait(1000)

    class Tester(Collector):
        def loop(self):
            if not TESTER:
                TESTER.append(self)
            if self is not TESTER[0]:
                self.wait(1000)
                return
            W.update(json.loads(Path(__file__).with_name("world.json").read_text()))
            r("fly_near", self.fly_to(*W["near"]))
            r("fly_slow", self.fly_to(*W["far"], speed=0.5))
            r("search_none", self.search(*W["empty"]))
            f = self.search(Point(*W["flower"]))
            r("search_flower", isinstance(f, Flower) and f.nectar >= 0.3)
            r("collect_flower", self.collect(f))
            r("full", self.is_full)
            r("go_home", self.go_home())
            r("at_home", self.at_home)
            r("nectar_after_home", self.nectar)
            r("collect_place_empty", self.collect(*W["empty"]))
            r("go_home2", self.go_home())
            r("refuel", self.refuel(100))
            r("energy", round(self.energy, 1))
            r("collect_place", self.collect(Point(*W["flower"])))
            ex = self.explore()
            r("explore", ex is None or isinstance(ex, Flower))
            r("done", self.time)
            self.wait(1000)

    class H(Hive):
        def loop(self):
            got = [self.hatch(Collector) for _ in range(2)]
            r("hatch", ",".join(str(g) for g in got))
            self.set_home_energy(0)
            self.wait(1000)
"""


def _world_json(sim, path: Path) -> None:
    """Точки для скрипта: рядом с летком, медленно далеко, пустое место, цветок."""
    w = sim.module.world
    e = w.hive_entrance[0, :2]
    fxy = w.flower_pos[:, :2]
    near = e + np.array([10.0, 0.0])
    flower = fxy[np.argmin(np.linalg.norm(fxy - e, axis=1))]
    # Пустое место: в 15 м от точки near, и вокруг отрезка к нему 15 м нет цветов.
    for a in np.linspace(0, 2 * np.pi, 32, endpoint=False):
        empty = near + 15.0 * np.array([math.cos(a), math.sin(a)])
        seg = near + np.linspace(0, 1, 30)[:, None] * (empty - near)
        d = np.linalg.norm(fxy[:, None, :] - seg[None], axis=2).min()
        if d > 15.0 and np.all(np.abs(empty) < w.half_size - 10):
            break
    else:  # pragma: no cover
        raise AssertionError("нет пустого места рядом с ульем")
    far = near + 20.0 * (near - e) / np.linalg.norm(near - e)
    path.write_text(json.dumps({
        "near": near.tolist(), "far": far.tolist(), "empty": empty.tolist(),
        "flower": flower.tolist(),
    }))


def test_commands_wait_and_return_results(tmp_path):
    """fly_to True/False, search цветок/None, collect цветка и места, go_home, refuel, hatch."""
    sim = script_sim(tmp_path, COMMANDS, "program.command_timeout_s=20",
                     "energy.home_energy=0", "economy.breeding.forager.cost=15", duration=400)
    with sim:
        _world_json(sim, tmp_path / "world.json")
        for _ in range(400):
            run_for(sim, 1.0)
            if "done" in results(sim):
                break
        r = results(sim)
        print(r)
        assert sim.runners.stats[0].agent_errors == 0, sim.runners.logs[0].text()
    assert r["fly_near"] == "True"
    assert r["fly_slow"] == "False"  # 0.5 м/с на 20 м не успеть за 20 с
    assert r["search_none"] == "None"
    assert r["search_flower"] == "True"
    assert r["collect_flower"] == "True" and r["full"] == "True"
    assert r["go_home"] == "True" and r["at_home"] == "True" and r["nectar_after_home"] == "0.0"
    assert r["collect_place_empty"] == "False"
    assert r["go_home2"] == "True" and r["refuel"] == "True" and float(r["energy"]) >= 99.9
    assert r["collect_place"] == "True"
    assert r["explore"] == "True"
    assert r["hatch"] == "True,False"  # мёд 20, сборщик стоит 15: второй — не хватает


# ===================================================================== автовозврат


AUTO = """
    from swarmlab.bees.api import Collector, Hive, Scout

    TESTER = []

    def r(name, value):
        print("R", name, value)

    class Idle(Scout):
        def loop(self):
            self.wait(1000)

    class Far(Collector):
        def __init__(self):
            self.passes = 0

        def loop(self):
            if not TESTER:
                TESTER.append(self)
            if self is not TESTER[0]:
                self.wait(1000)
                return
            self.passes += 1
            r(f"start{self.passes}", round(self.energy, 1))
            try:
                hx, hy = self.home.x, self.home.y
                n = (hx * hx + hy * hy) ** 0.5  # 60 м через центр карты, медленно
                to = (hx - 60 * hx / n, hy - 60 * hy / n)
                r(f"fly{self.passes}", self.fly_to(*to, speed=0.5))
                r(f"after{self.passes}", self.at_home)
                self.wait(1000)
            finally:
                r(f"finally{self.passes}", round(self.time, 1))

    class H(Hive):
        def loop(self):
            self.set_home_energy(THRESHOLD)
            self.set_refuel_energy(95)
            self.wait(1000)
"""


def test_auto_return_below_threshold_refuels_and_restarts_loop(tmp_path):
    sim = script_sim(tmp_path, AUTO.replace("THRESHOLD", "90"), "program.command_timeout_s=200")
    with sim:
        b = sim.module.bees
        slot = int(np.flatnonzero(b.uid == FIRST_FORAGER)[0])
        went_home = False
        for _ in range(200):
            run_for(sim, 1.0)
            went_home |= bool(b.state[slot] == IN_HIVE and sim.time > 5)
            if "start2" in results(sim):
                break
        r = results(sim)
        print(r)
    assert r["start1"] == "100.0"
    assert r["fly1"] == "False"  # ниже 90 % — текущая команда «не вышло»
    assert went_home
    assert "finally1" in r  # поток закрыт: finally выполнился
    assert float(r["start2"]) >= 95.0  # заправилась до set_refuel_energy(95), loop() сначала


def test_auto_return_threshold_zero_never_returns(tmp_path):
    sim = script_sim(tmp_path, AUTO.replace("THRESHOLD", "0"), "program.command_timeout_s=200")
    with sim:
        b = sim.module.bees
        slot = int(np.flatnonzero(b.uid == FIRST_FORAGER)[0])
        run_for(sim, 90.0)
        pct = 100 * b.energy[slot] / b.energy_max[slot]
        assert b.state[slot] == FLYING and pct < 90  # энергии меньше прежнего порога — летит
        assert not sim.module.control.auto_home[slot]
        assert "fly1" not in results(sim)


# ===================================================================== бак


def _tanks(*overrides: str) -> np.ndarray:
    sim = make_sim(*overrides)
    m = sim.module
    slots = [m.spawn(0, "forager") for _ in range(30)]
    base = m.params.bee_types.forager.energy_max
    return m.bees.energy_max[slots] / base


def test_tank_random_within_spread_same_for_same_seed():
    a, b = _tanks(), _tanks()
    assert np.all((a >= 0.8 - 1e-9) & (a <= 1.2 + 1e-9))
    assert np.ptp(a) > 0.2  # действительно разные
    assert np.array_equal(a, b)
    assert not np.array_equal(a, _tanks("seed=7"))
    flat = _tanks("energy.tank_spread=0")
    assert np.all(flat == 1.0)


# ===================================================================== связь


def test_say_radius_15_m_and_hive_hears_at_entrance_and_bees_inside_hear():
    sim = make_sim("pool.max_bees_per_hive=10", "economy.start_bees={}")
    m = sim.module
    e = m.world.hive_entrance[0]
    speaker = m.spawn(0, "scout", e + np.array([5.0, 0.0, 3.0]))
    near = m.spawn(0, "forager", e + np.array([5.0, 14.0, 3.0]))
    far = m.spawn(0, "forager", e + np.array([5.0, -16.0, 3.0]))
    away = m.spawn(0, "scout", e + np.array([40.0, 0.0, 3.0]))
    inside = m.bees.uid[m.bees.allocate(0, "forager", IN_HIVE)]
    run_for(sim, 0.1)
    m.say(speaker, "flowers", (1.0, 2.0))
    m.say(away, "far", (math.nan, math.nan))
    run_for(sim, 0.1)
    rows = {r["me"]["id"]: r for r in m.hive_sensors(0)}
    uid = m.bees.uid
    heard = {k: [x["word"] for x in rows[int(uid[k])]["messages"]] for k in (near, far, away)}
    assert heard == {near: ["flowers"], far: [], away: []}
    msg = rows[int(uid[near])]["messages"][0]
    assert msg["where"] == [1.0, 2.0] and msg["from_id"] == int(uid[speaker])
    assert [x["word"] for x in rows[int(inside)]["messages"]] == ["flowers"]  # дома — у летка
    assert [x["word"] for x in m.team_view(0)["messages"]] == ["flowers"]


# ===================================================================== реплей


def test_same_seed_and_scripts_same_replay_hash_old_replay_is_clear_error(tmp_path):
    from swarmlab.core.replay import ReplayWriter, make_header

    def run(path):
        cfg = load_match(CONFIGS / "matches" / "demo.yaml", cli_overrides=("duration_s=40",))
        with Simulation(cfg) as sim:
            writer = ReplayWriter(path, make_header(cfg, sim.teams, sim.module.scene()))
            sim.on_frame = writer
            sim.run()
            digest = writer.close(sim.module.score())
            stats = list(sim.runners.stats.values())
        assert all(s.missed == 0 and s.over_budget == 0 and s.agent_errors == 0 for s in stats)
        return digest

    assert run(tmp_path / "a.swr") == run(tmp_path / "b.swr")
    assert read_replay(tmp_path / "a.swr").hash_ok

    old = tmp_path / "old.swr"
    body = pack({"t": "header", "format": 1})
    old.write_bytes(MAGIC + zstandard.ZstdCompressor().compress(struct.pack("<I", len(body))
                                                                + body))
    with pytest.raises(ReplayError, match="реплей старой версии"):
        read_replay(old)
