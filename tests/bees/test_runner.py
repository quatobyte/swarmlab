"""Раннер кода игрока в настоящем отдельном процессе (`sys.executable -m swarmlab.runner`).

Тесты запускают реальные процессы: на Windows это проверка spawn-пути (без fork).
"""

import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from swarmlab.bees.state import FLYING, IN_HIVE
from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS, run_for

#: Стартовый состав: uid 0–4 разведчики, 5–19 сборщики, 20–24 охранники, 25–34 домашние.
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
            *overrides,
        ),
    )
    return Simulation(cfg)


def test_runner_is_separate_spawned_process(tmp_path):
    with script_sim(tmp_path, "from swarmlab.bees.api import Forager\n") as sim:
        link = sim.runners.links[0]
        proc = link._proc
        assert proc.args[:3] == [sys.executable, "-m", "swarmlab.runner"]
        assert proc.pid != __import__("os").getpid()
        assert link.ready_info["ok"] and link.ready_info["classes"]["forager"] == "Forager"
        run_for(sim, 1.0)
        assert sim.runners.stats[0].replies == 10
    assert proc.poll() is not None  # после close() процесс завершён
    print(f"platform={sys.platform}, runner pid={proc.pid}")


def test_infinite_loop_skips_ticks_then_restarts(tmp_path):
    code = """
        from swarmlab.bees.api import Hive

        def hive_step(hive: Hive):
            if hive.tick >= 5:
                while True:
                    pass
    """
    sim = script_sim(tmp_path, code, "runner.hard_timeout_ms=100")
    with sim:
        first_pid = sim.runners.links[0].pid
        run_for(sim, 3.0)
        stats = sim.runners.stats[0]
        assert sim.time == pytest.approx(3.0)  # матч идёт дальше
        assert stats.missed >= 3
        assert stats.restarts >= 1
        assert sim.runners.links[0].pid != first_pid
        log = sim.runners.logs[0].text()
        assert "пропущен" in log and "перезапускается" in log and "self" in log
    print(f"пропущено {stats.missed}, перезапусков {stats.restarts}")


def test_exception_in_one_bee_others_keep_working(tmp_path):
    code = f"""
        from swarmlab.bees.api import Forager, Sensors

        class Crashy(Forager):
            def step(self, s: Sensors):
                if s.me.id == {FIRST_FORAGER} and s.time >= 4.0:
                    print("сейчас упаду")
                    return 1 / 0
                super().step(s)
    """
    with script_sim(tmp_path, code) as sim:
        module = sim.module
        b = module.bees
        run_for(sim, 4.5)
        victim = int(np.flatnonzero(b.uid == FIRST_FORAGER)[0])
        assert b.state[victim] == FLYING
        others = np.flatnonzero((b.kind == 1) & (b.state == FLYING) & (b.uid != FIRST_FORAGER))
        p0, _ = module.backend.body_state(np.array([victim]))
        q0, _ = module.backend.body_state(others)
        run_for(sim, 3.0)
        p1, v1 = module.backend.body_state(np.array([victim]))
        q1, _ = module.backend.body_state(others)

        assert np.linalg.norm(p1 - p0) < 0.5 and np.linalg.norm(v1) < 0.3  # висит
        moved = np.linalg.norm(q1 - q0, axis=1)
        assert np.count_nonzero(moved > 2.0) >= 5  # остальные летают
        stats = sim.runners.stats[0]
        assert stats.agent_errors >= 25 and stats.missed == 0 and stats.restarts == 0
        log = sim.runners.logs[0].text()
        assert "ZeroDivisionError" in log
        assert "player.py\", line 8, in step" in log  # трассировка указывает на строку игрока
        assert "сейчас упаду" in log  # print попал в лог, а не в протокол
        assert "уже 10 раз" in log  # повторы не засоряют лог


def test_budget_overrun_is_counted_and_commands_dropped(tmp_path):
    code = """
        import time
        from swarmlab.bees.api import Hive

        def hive_step(hive: Hive):
            hive.breed("house")
            if hive.tick >= 2:
                t = time.perf_counter()
                while time.perf_counter() - t < 0.05:
                    pass
    """
    with script_sim(tmp_path, code, "runner.budget_ms=20", "runner.hard_timeout_ms=1000") as sim:
        run_for(sim, 1.5)
        stats = sim.runners.stats[0]
        assert stats.over_budget >= 12
        assert stats.missed == 0
        assert stats.cpu_ms_max >= 50.0
        # Выведение прошло только на тиках 0–1 (в бюджете), дальше команды отброшены.
        assert sim.module.economy.spent_breeding[0] == pytest.approx(2 * 2.0)
        assert "бюджете 20 мс" in sim.runners.logs[0].text()


def test_syntax_error_is_reported_with_line_and_match_goes_on(tmp_path):
    code = """
        from swarmlab.bees.api import Forager

        class Broken(Forager):
            def step(self, s)
                pass
    """
    with script_sim(tmp_path, code) as sim:
        stats = sim.runners.stats[0]
        assert stats.disabled and stats.load_error is not None
        assert "SyntaxError" in stats.load_error and "line 5" in stats.load_error
        run_for(sim, 1.0)
        assert stats.restarts == 0
        assert np.all(sim.module.bees.state[sim.module.bees.state != 0] == IN_HIVE)


def test_commands_go_home_collect_unload_and_breed(tmp_path):
    """Цепочка команд игрока: вылет, сбор, домой, выгрузка, выведение."""
    code = """
        from swarmlab.bees.api import Forager, Hive, Sensors

        FLOWER = -1

        class F(Forager):
            def step(self, s: Sensors):
                me = s.me
                if me.in_hive:
                    if me.cargo > 0:
                        self.unload()
                    elif not getattr(self, "done", False):
                        self.done = True
                        self.collect(FLOWER)
                    return
                mine = [f for f in s.flowers if f.id == FLOWER]
                if me.is_full or (me.cargo > 0 and mine and mine[0].nectar < 0.05):
                    self.go_home()

        def hive_step(hive: Hive):
            if hive.tick == 1:
                hive.breed("scout", 2)
    """
    with script_sim(tmp_path, code) as sim:
        m = sim.module
        # Ближайший к улью цветок — его номер подставляем в скрипт.
        flower = int(np.argmin(np.linalg.norm(
            m.world.flower_pos - m.world.hive_entrance[0], axis=1)))
    code = code.replace("FLOWER = -1", f"FLOWER = {flower}")
    with script_sim(tmp_path, code) as sim:
        e = sim.module.economy
        run_for(sim, 60.0)
        # 15 сборщиков опустошили цветок (3 ед.), вернулись и выгрузили нектар.
        assert e.delivered[0] >= 2.5
        assert e.spent_breeding[0] == pytest.approx(2 * 3.0)
        assert sim.module.invalid_commands[0] == 0
