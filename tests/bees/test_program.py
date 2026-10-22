"""M7a: `step()` с `yield` — блокирующие команды и процедуры (DECISIONS №57–61).

Часть тестов гоняет хост раннера без процесса (точный контроль тиков и статусов),
часть — настоящий матч с раннером в отдельном процессе.
"""

import textwrap
from pathlib import Path

import numpy as np
import pytest

from swarmlab.bees.api import Forager, Sensors, wait
from swarmlab.bees.player_host import HiveHost
from swarmlab.bees.state import FREE, IN_HIVE
from swarmlab.core.config import load_match
from swarmlab.core.program import DONE, FAILED, RUNNING
from swarmlab.core.protocol import CommandBatch, SensorBatch
from swarmlab.core.replay import read_replay
from swarmlab.core.sim import Simulation

from .helpers import CALM, CONFIGS, FLAT, make_sim, run_for

#: Стартовый состав: uid 0–4 разведчики, 5–19 сборщики, 20–24 охранники, 25–34 домашние.
FIRST_FORAGER = 5
#: Хеш реплея `demo.yaml` на 30 с, снятый до M7a (коммит ddf65c7) на машине Лео.
DEMO30_HASH_BEFORE_M7A = "68fbd0aeafd47247dd3ec294206508b32b833d1c545873bf3191b8422b8bdc51"


# ===================================================================== хост без процесса


def raw_bee(uid: int, tick: int, *, wait_status=None, x: float = 0.0) -> dict:
    """Сенсоры летающего сборщика в формате протокола (BEES_SPEC §5.1)."""
    me = {
        "id": uid, "kind": "forager", "pos": [x, 0.0, 5.0], "vel": [0.0, 0.0, 0.0],
        "energy": 100.0, "energy_max": 100.0, "cargo": 0.0, "cargo_max": 1.5,
        "in_hive": False, "alive": True,
    }
    if wait_status is not None:
        me["wait"] = wait_status
    return {
        "tick": tick, "time": round(tick * 0.1, 6), "me": me,
        "home": {"pos": [0.0, 0.0, 1.0], "dir": [1.0, 0.0, 0.0], "dist": 1.0},
        "ground_z": 0.0, "airspeed": [0.0, 0.0, 0.0], "weather": "clear",
        "flowers": [], "bees": [], "enemies": [], "obstacles": [], "messages": [],
        "pheromones": {"values": [], "gradient": []},
    }


def batch(tick: int, *agents: dict) -> SensorBatch:
    view = {"tick": tick, "time": round(tick * 0.1, 6)}
    return SensorBatch(tick=tick, team=0, budget_ms=20.0, team_view=view, agents=list(agents))


def host_with(cls: type) -> tuple[HiveHost, list[str]]:
    log: list[str] = []
    host = HiveHost(log.append)
    host.use_classes({"forager": cls})
    return host, log


EVENTS: list[tuple] = []


class Courier(Forager):
    """Летит, ждёт; в `finally` отмечает закрытие."""

    def step(self, s: Sensors):
        EVENTS.append(("start", s.me.id))
        try:
            ok = yield self.fly_to(10.0, 0.0)
            EVENTS.append(("arrived", s.me.id, ok, s.me.pos.x))
            yield wait()
        finally:
            EVENTS.append(("finally", s.me.id))


def test_waiting_command_carries_seq_and_resumes_with_fresh_sensors():
    EVENTS.clear()
    host, _ = host_with(Courier)
    out = host.step(batch(0, raw_bee(5, 0)))
    cmd = out.commands[5]
    assert cmd["move"][0] == "fly_to" and cmd["wait"] >= 1
    seq = cmd["wait"]
    # Модуль подтвердил и ещё ждёт — новых команд нет, пчела продолжает fly_to.
    assert host.step(batch(1, raw_bee(5, 1, wait_status=[seq, RUNNING], x=4.0))).commands == {}
    # Выполнено — генератор продолжается; s внутри уже свежий (x = 10).
    out = host.step(batch(2, raw_bee(5, 2, wait_status=[seq, DONE], x=10.0)))
    assert EVENTS == [("start", 5), ("arrived", 5, True, 10.0)]
    assert 5 not in out.commands  # после прибытия — yield wait(): команды нет


def test_lost_command_is_sent_again_with_same_seq():
    EVENTS.clear()
    host, _ = host_with(Courier)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    # Команда не дошла (бюджет, пропуск тика): в сенсорах нет нашего seq.
    again = host.step(batch(1, raw_bee(5, 1))).commands[5]
    assert again["wait"] == seq and again["move"][0] == "fly_to"


def test_death_while_waiting_closes_program_and_new_bee_starts_over():
    """Критерий M7a: смерть → close(), finally выполнен, новая пчела — с начала."""
    EVENTS.clear()
    host, _ = host_with(Courier)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    host.step(batch(1, raw_bee(5, 1, wait_status=[seq, RUNNING])))
    host.step(batch(2))  # пчела 5 погибла — её нет в пакете
    assert EVENTS == [("start", 5), ("finally", 5)]
    assert 5 not in host.programs and 5 not in host.agents
    host.step(batch(3, raw_bee(6, 3)))  # новая пчела того же типа
    assert EVENTS[-1] == ("start", 6) and 6 in host.programs


def test_yield_from_procedure_returns_value():
    """Критерий M7a: `result = yield from proc()` возвращает значение процедуры."""
    results: list = []

    class Tripper(Forager):
        def step(self, s: Sensors):
            results.append((yield from self.trip()))

        def trip(self):
            ok = yield self.go_home()
            yield wait()
            return ("home", ok)

    host, _ = host_with(Tripper)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    host.step(batch(1, raw_bee(5, 1, wait_status=[seq, FAILED])))
    host.step(batch(2, raw_bee(5, 2)))
    assert results == [("home", False)]


def test_step_without_yield_keeps_old_semantics():
    class Plain(Forager):
        def step(self, s: Sensors):
            self.hover()
            self.fly_to(1.0, 2.0)  # последняя команда побеждает

    host, _ = host_with(Plain)
    out = host.step(batch(0, raw_bee(5, 0)))
    assert out.commands == {5: {"move": ["fly_to", 1.0, 2.0, None, None, True]}}
    assert host.programs == {}


def test_end_of_match_closes_programs():
    EVENTS.clear()
    host, _ = host_with(Courier)
    host.step(batch(0, raw_bee(5, 0)))
    host.close()
    assert EVENTS == [("start", 5), ("finally", 5)]


# ===================================================================== настоящий матч


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


def log_lines(sim, prefix: str) -> list[str]:
    return [ln for ln in sim.runners.logs[0].text().splitlines() if ln.startswith(prefix)]


def test_yield_fly_to_true_for_reachable_false_after_timeout(tmp_path):
    """Критерий M7a: `ok = yield fly_to(...)` — True у достижимой цели, False по таймауту."""
    code = f"""
        from swarmlab.bees.api import Forager, Sensors, wait

        class F(Forager):
            def step(self, s: Sensors):
                if s.me.id != {FIRST_FORAGER}:
                    return
                home = s.home.pos
                ok = yield self.fly_to(home.x + 12, home.y + 6)
                print(f"reachable={{ok}} t={{s.time:.1f}} speed={{s.me.vel.length():.2f}}")
                # Ниже рельефа: автопилот держит просвет, цель недостижима.
                ok = yield self.fly_to(home.x + 12, home.y + 6, z=s.ground_z - 30)
                print(f"unreachable={{ok}} t={{s.time:.1f}}")
                while True:
                    yield wait()
    """
    with script_sim(tmp_path, code, "program.command_timeout_s=15") as sim:
        run_for(sim, 40.0)
        reach = log_lines(sim, "reachable=")
        unreach = log_lines(sim, "unreachable=")
    assert len(reach) == 1 and reach[0].startswith("reachable=True")
    t_reach = float(reach[0].split("t=")[1].split()[0])
    assert t_reach < 15.0
    assert float(reach[0].split("speed=")[1]) <= 0.3
    assert len(unreach) == 1 and unreach[0].startswith("unreachable=False")
    t_fail = float(unreach[0].split("t=")[1])
    assert t_fail - t_reach == pytest.approx(15.0, abs=0.25)


def test_death_in_real_match_runs_finally_and_newborn_starts_over(tmp_path):
    """Критерий M7a в настоящем раннере: гибель пчелы во время ожидания."""
    code = """
        from swarmlab.bees.api import Forager, Sensors

        class F(Forager):
            def step(self, s: Sensors):
                print(f"start {s.me.id}")
                try:
                    yield self.fly_to(s.home.pos.x + 40, s.home.pos.y)
                    print(f"arrived {s.me.id}")
                finally:
                    print(f"finally {s.me.id}")
    """
    with script_sim(tmp_path, code) as sim:
        m, b = sim.module, sim.module.bees
        run_for(sim, 2.0)
        slot = int(np.flatnonzero((b.uid == FIRST_FORAGER) & (b.state != FREE))[0])
        m.kill(np.array([slot]), "test")
        run_for(sim, 0.3)
        assert f"finally {FIRST_FORAGER}" in log_lines(sim, "finally")
        assert not log_lines(sim, f"arrived {FIRST_FORAGER}")
        newborn = m.give_birth(0, "forager")
        run_for(sim, 0.3)
        assert f"start {newborn}" in log_lines(sim, "start")


def test_wait_loop_does_not_trip_cpu_budget(tmp_path):
    """Критерий M7a: `while …: yield wait()` — один шаг цикла за тик, бюджет не срабатывает."""
    code = """
        from swarmlab.bees.api import Forager, Guard, HouseBee, Scout, wait

        class F(Forager):
            def step(self, s):
                while s.me.energy > 0:
                    yield wait()

        class S(Scout):
            def step(self, s):
                while True:
                    yield wait()

        class G(Guard):
            def step(self, s):
                while True:
                    yield wait()

        class H(HouseBee):
            def step(self, s):
                while True:
                    yield wait()

        def hive_step(hive):
            while True:
                yield wait()
    """
    with script_sim(tmp_path, code, "runner.budget_ms=20") as sim:
        run_for(sim, 10.0)
        stats = sim.runners.stats[0]
        assert stats.replies == 100 and stats.missed == 0
        assert stats.over_budget == 0 and stats.agent_errors == 0
        assert stats.cpu_ms_max < 5.0


def test_hive_waits_seconds(tmp_path):
    """Критерий M7a: `yield wait(секунды)` для улья."""
    code = """
        from swarmlab.bees.api import Hive, wait

        def hive_step(hive: Hive):
            while True:
                hive.breed("house")
                print(f"breed t={hive.time:.1f}")
                yield wait(2)
    """
    with script_sim(tmp_path, code) as sim:
        run_for(sim, 5.05)
        assert log_lines(sim, "breed") == ["breed t=0.0", "breed t=2.0", "breed t=4.0"]
        assert sim.module.economy.spent_breeding[0] == pytest.approx(3 * 2.0)


def test_yield_from_in_real_runner(tmp_path):
    code = f"""
        from swarmlab.bees.api import Forager, wait

        class F(Forager):
            def step(self, s):
                if s.me.id != {FIRST_FORAGER}:
                    return
                result = yield from self.out_and_count()
                print(f"result={{result}}")
                while True:
                    yield wait()

            def out_and_count(self):
                ok = yield self.leave_hive()
                n = 0
                for _ in range(3):
                    yield wait()
                    n += 1
                return ok, n
    """
    with script_sim(tmp_path, code) as sim:
        run_for(sim, 2.0)
        assert log_lines(sim, "result=") == ["result=(True, 3)"]


# ===================================================================== условия модуля


def _team_cmd(sim, uid: int, cmd: dict) -> None:
    sim.module.apply_commands(0, CommandBatch(tick=0, commands={uid: cmd}))


def test_module_wait_conditions():
    """DECISIONS №61: go_home — в улье; unload — сразу; битый цветок — сразу «не вышло»."""
    with make_sim(*FLAT, *CALM, "enemies.hornets.enabled=false") as sim:
        m = sim.module
        b, c = m.bees, m.control
        slots = [m.spawn(0, "forager") for _ in range(3)]
        uids = [int(b.uid[s]) for s in slots]
        run_for(sim, 0.1)
        _team_cmd(sim, uids[0], {"move": ["go_home"], "wait": 1})
        _team_cmd(sim, uids[1], {"move": ["unload"], "wait": 2})  # не в улье
        _team_cmd(sim, uids[2], {"move": ["collect", 10**6], "wait": 3})
        assert c.wait_state[slots[1]] == FAILED and c.wait_state[slots[2]] == FAILED
        assert c.wait_state[slots[0]] == RUNNING
        for _ in range(300):
            run_for(sim, 0.1)
            if b.state[slots[0]] == IN_HIVE:
                break
        run_for(sim, 0.1)
        assert c.wait_state[slots[0]] == DONE
        # Новая команда без ожидания снимает ожидание.
        _team_cmd(sim, uids[0], {"move": ["hover"]})
        assert c.wait_seq[slots[0]] == 0
        # Гибель освобождает слот вместе с ожиданием.
        _team_cmd(sim, uids[1], {"move": ["hover"], "wait": 4})
        m.kill(np.array([slots[1]]), "test")
        assert c.wait_seq[slots[1]] == 0


# ===================================================================== регрессия


def test_step_without_yield_gives_same_replay_hash_as_before_m7a(tmp_path):
    """Критерий M7a: без `yield` — те же траектории (хеш реплея) и счёт `demo.yaml`, что до M7a.

    Эталон снят кодом до M7a (коммит ddf65c7) на машине Лео (DECISIONS №12: битовый
    детерминизм MuJoCo — только на одной машине). Бюджет раннера снят: превышение
    20 мс меряется часами стены и под нагрузкой отбрасывает команды тика — тогда
    хеш зависел бы от загрузки машины, а не от кода.
    """
    from swarmlab.cli import main

    out = tmp_path / "demo30.swr"
    code = main([
        "run", str(CONFIGS / "matches" / "demo.yaml"), "--headless",
        "--set", "duration_s=30",
        "--set", "runner.budget_ms=100000", "--set", "runner.hard_timeout_ms=100000",
        "--replay", str(out), "--log-dir", str(tmp_path / "logs"),
    ])
    assert code == 0
    replay = read_replay(out)
    assert replay.hash == DEMO30_HASH_BEFORE_M7A
    teams = replay.footer["score"]["teams"]
    got = {k: (v["place"], round(v["honey"], 6), round(v["delivered"], 6), v["alive"])
           for k, v in teams.items()}
    assert got == {
        "0": (3.0, 16.684345, 4.5, 34.0),
        "1": (2.0, 20.810836, 4.5, 34.0),
        "2": (1.0, 21.018007, 9.0, 35.0),
    }
