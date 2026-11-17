"""Обучение (M11, DECISIONS №100): миры миссий на настоящем движке.

Для каждой миссии эталон (`tests/bees/tutorial/ref_N.py`) проходит цель, а программа прошлой
миссии — нет: без нового приёма миссию не пройти. Миссия 8 — экзамен без нового приёма
(DECISIONS №102): её не проходит программа миссии 5. Цель судит тот же
`web/js/modules/bees/missions.js`, что и браузер, — под Node (`tests/web/missions_check.mjs`)
по счёту матча раз в секунду. Без Node.js прогоны пропускаются.

Прогоны долгие (до минуты на матч) — метка `tutorial`; только они:
    .venv\\Scripts\\python -m pytest -m tutorial
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
REF = Path(__file__).parent / "tutorial"
JUDGE = ROOT / "tests" / "web" / "missions_check.mjs"
MATCHES = sorted((CONFIGS / "matches").glob("tutorial_*.yaml"))
# Чья программа обязана провалить миссию, если не программа прошлой (DECISIONS №102).
FAILS_WITH = {1: "empty.py", 8: "ref_5.py"}
NODE = shutil.which("node")


def _number(path: Path) -> int:
    return int(path.stem.split("_")[1])


def _config(n: int, program: Path, extra: tuple[str, ...] = ()):
    path = CONFIGS / "matches" / f"tutorial_{n}.yaml"
    hives = yaml.safe_load(path.read_text(encoding="utf-8"))["hives"]
    hives[0]["script"] = str(program)
    return load_match(path, configs_dir=CONFIGS,
                      cli_overrides=(f"hives={json.dumps(hives)}", *extra))


class Judge:
    """Судья миссии в процессе Node: строка счёта → решение."""

    def __init__(self, mission: int, duration: float, code: str) -> None:
        self.proc = subprocess.Popen(
            [NODE, str(JUDGE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            encoding="utf-8")
        self.rule = self._ask({"mission": mission, "duration": duration, "code": code})["rule"]

    def _ask(self, msg: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "судья миссии упал"
        return json.loads(line)

    def step(self, time: float, rows: dict, end: bool = False) -> dict:
        return self._ask({"time": time, "rows": rows, "end": end})

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)


def play(n: int, program: Path, tmp_path: Path) -> dict:
    """Сыграть миссию `n` программой `program`; итог судьи и время решения."""
    cfg = _config(n, program)
    judge = Judge(n, cfg.duration_s, program.read_text(encoding="utf-8"))
    sim = Simulation(cfg, log_dir=tmp_path / f"m{n}-{program.stem}")
    try:
        every = sim.clock.steps_for(1.0)
        out = {"done": False}
        while not out["done"] and not sim.finished:
            sim.run(max_steps=every)
            rows = {str(h): r for h, r in sim.module.score().teams.items()}
            out = judge.step(sim.time, rows)
        if not out["done"]:
            out = judge.step(sim.time, rows, end=True)
        out["time"] = sim.time
        return out
    finally:
        sim.close()
        judge.close()


def test_tutorial_matches_load_and_use_readonly_rivals():
    assert [_number(p) for p in MATCHES] == list(range(1, len(MATCHES) + 1))
    for path in MATCHES:
        cfg = load_match(path, configs_dir=CONFIGS)
        assert cfg.params["world"]["n_hives"] == len(cfg.params["hives"]), path.name
        for hive in cfg.params["hives"][1:]:
            name = Path(hive["script"]).name
            assert name.startswith("example_rival_"), name  # соперники — примеры только для чтения
            assert (ROOT / hive["script"]).is_file(), hive["script"]


@pytest.mark.skipif(NODE is None, reason="нет Node.js — судья миссий не запустится")
def test_missions_js_knows_every_tutorial_match():
    src = (ROOT / "web/js/modules/bees/missions_ru.js").read_text(encoding="utf-8")
    for path in MATCHES:
        assert f'match: "{path.name}"' in src, path.name


@pytest.mark.tutorial
@pytest.mark.skipif(NODE is None, reason="нет Node.js — судья миссий не запустится")
@pytest.mark.parametrize("n", [_number(p) for p in MATCHES])
def test_reference_passes_and_previous_program_fails(n, tmp_path):
    ok = play(n, REF / f"ref_{n}.py", tmp_path)
    assert ok["win"], f"эталон миссии {n} не прошёл: {ok}"
    prev = REF / FAILS_WITH.get(n, f"ref_{n - 1}.py")
    bad = play(n, prev, tmp_path)
    assert bad["win"] is False, (
        f"миссию {n} прошла программа без нового приёма ({prev.name}): {bad}")
