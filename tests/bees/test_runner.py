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
            *overrides,
        ),
    )
    return Simulation(cfg)


def test_runner_is_separate_spawned_process(tmp_path):
    with script_sim(tmp_path, "from swarmlab.bees.api import Collector") as sim:
        link = sim.runners.links[0]
        proc = link._proc
        assert proc.args[:3] == [sys.executable, "-m", "swarmlab.runner"]
        assert proc.pid != __import__("os").getpid()
        assert link.ready_info["ok"] and link.ready_info["classes"]["forager"] == "Collector"
        run_for(sim, 1.0)
        assert sim.runners.stats[0].replies == 10
    assert proc.poll() is not None  # после close() процесс завершён
    print(f"platform={sys.platform}, runner pid={proc.pid}")


def test_infinite_loop_without_commands_skips_ticks_then_restarts(tmp_path):
    """Бесконечный цикл без команд не вешает матч: бюджет, пропуск тиков, перезапуск."""
    code = """
        from swarmlab.bees.api import Hive

        class Stuck(Hive):
            def loop(self):
                if self.time >= 0.5:
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
        assert "пропущен" in log and "перезапускается" in log and "loop()" in log
    print(f"пропущено {stats.missed}, перезапусков {stats.restarts}")


def test_exception_in_one_bee_others_keep_working(tmp_path):
    code = """
        from swarmlab.bees.api import Collector

        VICTIM = []

        class Crashy(Collector):
            def loop(self):
                if not VICTIM:
                    VICTIM.append(self)
                if self is VICTIM[0]:
                    self.fly_to(self.home.x + 8, self.home.y)
                    print("сейчас упаду")
                    return 1 / 0
                super().loop()
    """
    with script_sim(tmp_path, code) as sim:
        module = sim.module
        b = module.bees
        run_for(sim, 6.0)
        victim = int(np.flatnonzero(b.uid == FIRST_FORAGER)[0])
        assert b.state[victim] == FLYING
        others = np.flatnonzero((b.kind == 1) & (b.state == FLYING) & (b.uid != FIRST_FORAGER))
        p0, _ = module.backend.body_state(np.array([victim]))
        q0, _ = module.backend.body_state(others)
        run_for(sim, 3.0)
        p1, _ = module.backend.body_state(np.array([victim]))
        q1, _ = module.backend.body_state(others)

        assert np.linalg.norm(p1 - p0) < 1.0  # остаётся у своей точки
        moved = np.linalg.norm(q1 - q0, axis=1)
        assert np.count_nonzero(moved > 2.0) >= 5  # остальные летают
        stats = sim.runners.stats[0]
        assert stats.agent_errors >= 10 and stats.missed == 0 and stats.restarts == 0
        log = sim.runners.logs[0].text()
        assert "ZeroDivisionError" in log
        assert "player.py\", line 13, in loop" in log  # трассировка указывает на строку игрока
        assert "loop() начнётся сначала" in log
        assert "сейчас упаду" in log  # print попал в лог, а не в протокол
        assert "уже 10 раз" in log  # повторы не засоряют лог


def test_budget_overrun_is_counted_and_commands_dropped(tmp_path):
    code = """
        import time
        from swarmlab.bees.api import Hive, Worker

        class Slow(Hive):
            def loop(self):
                self.hatch(Worker)
                if self.time >= 0.15:
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
        from swarmlab.bees.api import Collector

        class Broken(Collector):
            def loop(self)
                pass
    """
    with script_sim(tmp_path, code) as sim:
        stats = sim.runners.stats[0]
        assert stats.disabled and stats.load_error is not None
        assert "SyntaxError" in stats.load_error and "line 5" in stats.load_error
        run_for(sim, 1.0)
        assert stats.restarts == 0
        assert np.all(sim.module.bees.state[sim.module.bees.state != 0] == IN_HIVE)
