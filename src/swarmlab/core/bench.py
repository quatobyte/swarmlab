"""Бенчмарк профилей: какой профиль тянет эта машина (ARCHITECTURE §6, DECISIONS №41).

Для каждого профиля есть матч `configs/bench/<профиль>.yaml` с нагрузкой как в
настоящем матче (раннеры кода игрока, враги, погода, почти полный улей) — ядро
не знает, что внутри, оно просто запускает эти файлы. Прогон: сборка мира и
раннеров, прогрев (`warmup_s` симуляции — пчёлы вылетают из ульев), затем замер
`min(seconds симуляции, wall_limit_s реального времени)` с записью реплея во
временный файл. RTF = время симуляции / время стены.

Рекомендация — самый тяжёлый (по числу тел физики) профиль с RTF ≥ `THRESHOLD`.
Результат кэшируется в `~/.swarmlab/bench.json` (папку меняет `SWARMLAB_HOME`).
Часы стены здесь — только для замера; в состояние симуляции они не попадают.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from swarmlab.core.config import load_match
from swarmlab.core.module import Replayable
from swarmlab.core.replay import ReplayWriter, make_header
from swarmlab.core.sim import Simulation

#: Профиль подходит, если симуляция быстрее реального времени с этим запасом.
THRESHOLD = 1.2
DEFAULT_SECONDS = 10.0
DEFAULT_WARMUP_S = 3.0


@dataclass
class BenchResult:
    """Замер одного профиля."""

    profile: str
    match: str
    bodies: int  # тел в физической модели (пул)
    teams: int  # команд с кодом игрока (раннеров)
    build_s: float  # сборка мира и запуск раннеров, с
    sim_s: float  # время симуляции в замере, с
    wall_s: float  # время стены в замере, с
    steps: int
    rtf: float

    @property
    def ok(self) -> bool:
        return self.rtf >= THRESHOLD


@dataclass
class BenchReport:
    results: list[BenchResult] = field(default_factory=list)
    created: str = ""
    machine: dict[str, Any] = field(default_factory=dict)
    seconds: float = DEFAULT_SECONDS
    threshold: float = THRESHOLD

    @property
    def recommended(self) -> str | None:
        """Самый тяжёлый профиль с RTF ≥ порога."""
        good = [r for r in self.results if r.ok]
        return max(good, key=lambda r: r.bodies).profile if good else None

    def to_json(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "machine": self.machine,
            "seconds": self.seconds,
            "threshold": self.threshold,
            "recommended": self.recommended,
            "results": [asdict(r) for r in self.results],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BenchReport:
        return cls(
            results=[BenchResult(**r) for r in data.get("results", [])],
            created=data.get("created", ""),
            machine=data.get("machine", {}),
            seconds=data.get("seconds", DEFAULT_SECONDS),
            threshold=data.get("threshold", THRESHOLD),
        )


def machine_info() -> dict[str, Any]:
    return {
        "system": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpus": os.cpu_count(),
        "python": platform.python_version(),
    }


def bench_matches(configs_dir: Path, profiles: list[str] | None = None) -> list[Path]:
    """Матчи бенчмарка `configs/bench/*.yaml` (или только перечисленные профили)."""
    folder = Path(configs_dir) / "bench"
    if profiles:
        paths = [folder / f"{p}.yaml" for p in profiles]
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"Нет матчей бенчмарка: {', '.join(missing)}")
        return paths
    return sorted(folder.glob("*.yaml"))


def run_profile(
    match: Path,
    *,
    seconds: float = DEFAULT_SECONDS,
    wall_limit_s: float = DEFAULT_SECONDS,
    warmup_s: float = DEFAULT_WARMUP_S,
) -> BenchResult:
    """Прогнать один матч бенчмарка и измерить RTF."""
    cfg = load_match(match, cli_overrides=[f"duration_s={warmup_s + seconds + 10.0}"])
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="swarmlab-bench-") as tmp, Simulation(
        cfg, log_dir=Path(tmp) / "logs"
    ) as sim:
        build_s = time.perf_counter() - t0
        writer = None
        if isinstance(sim.module, Replayable):
            header = make_header(cfg, sim.teams, sim.module.scene())
            writer = ReplayWriter(Path(tmp) / "bench.swr", header)
            sim.on_frame = writer
        sim.run(max_steps=sim.clock.steps_for(warmup_s))
        chunk = sim.clock.steps_for(1.0 / cfg.timing.decision_hz)
        limit = sim.clock.steps_for(seconds)
        steps = 0
        start = time.perf_counter()
        while steps < limit and time.perf_counter() - start < wall_limit_s and not sim.finished:
            steps += sim.run(max_steps=min(chunk, limit - steps)).steps
        wall = time.perf_counter() - start
        if writer is not None:
            writer.close()
        sim_s = steps * sim.clock.dt
        return BenchResult(
            profile=cfg.profile,
            match=str(match),
            bodies=sim.physics.n_bodies,
            teams=len(sim.teams),
            build_s=build_s,
            sim_s=sim_s,
            wall_s=wall,
            steps=steps,
            rtf=sim_s / wall if wall > 0 else float("inf"),
        )


def run_bench(
    configs_dir: Path,
    profiles: list[str] | None = None,
    *,
    seconds: float = DEFAULT_SECONDS,
    warmup_s: float = DEFAULT_WARMUP_S,
    on_result: Callable[[BenchResult], None] | None = None,
) -> BenchReport:
    """Прогнать все матчи бенчмарка; профили — по возрастанию нагрузки."""
    report = BenchReport(
        created=dt.datetime.now().isoformat(timespec="seconds"),
        machine=machine_info(),
        seconds=seconds,
    )
    for match in bench_matches(configs_dir, profiles):
        r = run_profile(match, seconds=seconds, wall_limit_s=seconds, warmup_s=warmup_s)
        report.results.append(r)
        if on_result is not None:
            on_result(r)
    report.results.sort(key=lambda r: r.bodies)
    return report


def cache_path() -> Path:
    home = os.environ.get("SWARMLAB_HOME")
    return (Path(home) if home else Path.home() / ".swarmlab") / "bench.json"


def save_cache(report: BenchReport, path: Path | None = None) -> Path:
    path = path or cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cache(path: Path | None = None) -> BenchReport | None:
    path = path or cache_path()
    try:
        return BenchReport.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None
