"""Цикл симуляции: три частоты (физика, решения, кадры) поверх `Module`.

Симуляция не читает системное время: headless-прогон, живой режим, вьюеры и
сервер — внешние циклы, которые вызывают `step()`. Единственный ввод-вывод —
обмен с раннерами кода игрока (`RunnerPool`) на тике решений; таймауты раннеров
идут по часам стены и в состояние симуляции не попадают (ARCHITECTURE §3.4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from swarmlab.core.clock import Clock
from swarmlab.core.config import MatchConfig
from swarmlab.core.module import Frame, Module, load_module
from swarmlab.core.physics import PhysicsBackend
from swarmlab.core.rng import RngRegistry
from swarmlab.core.runner_host import RunnerPool

FrameCallback = Callable[[Frame], None]


@dataclass(frozen=True)
class RunStats:
    """Итог прогона: сколько шагов сделано и сколько прошло времени симуляции."""

    steps: int
    sim_time: float


class Simulation:
    """Матч: модуль + физика + часы + раннеры кода игрока.

    Если у модуля есть команды с кодом игрока, при создании запускаются раннеры
    (по процессу на команду). Их нужно закрыть: `close()` или `with Simulation(...)`.
    """

    def __init__(
        self,
        cfg: MatchConfig,
        module: Module | None = None,
        on_frame: FrameCallback | None = None,
        *,
        log_dir: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.module = module if module is not None else load_module(cfg.module)
        self.rng = RngRegistry(cfg.seed)
        self.clock = Clock(cfg.timing.rates())
        self.on_frame = on_frame

        self.module.build(cfg, self.rng)
        self.physics: PhysicsBackend = self.module.physics()
        if abs(self.physics.timestep - self.clock.dt) > 1e-12:
            raise ValueError(
                f"Шаг физики модуля {self.physics.timestep} "
                f"не совпадает с шагом ядра {self.clock.dt}"
            )
        self.teams = self.module.agent_teams()
        self.runners: RunnerPool | None = None
        if self.teams:
            self.runners = RunnerPool(
                self.teams, module=cfg.module, seed=cfg.seed, cfg=cfg.runner, log_dir=log_dir
            )
            try:
                self.runners.start()
            except BaseException:
                self.runners.close()
                raise

    @property
    def time(self) -> float:
        return self.clock.time

    @property
    def finished(self) -> bool:
        return self.clock.time >= self.cfg.duration_s or self.module.is_finished()

    def step(self) -> None:
        """Один шаг физики (и, если пора, тик решений и кадр)."""
        clock = self.clock
        if clock.is_decision_step:
            self.module.decide(clock.decision_tick)
            if self.runners is not None:
                self._exchange()
        self.module.pre_physics(clock.dt)
        self.physics.step(1)
        self.module.post_physics(clock.dt)
        clock.advance()
        # Кадр — по частоте кадров и ещё один, если матч только что закончился
        # досрочно: события последних шагов (например, «улей выбыл») не теряются.
        if self.on_frame is not None and (clock.is_frame_step or self.finished):
            self.on_frame(self.module.snapshot())

    def _exchange(self) -> None:
        """Сенсоры → раннеры (параллельно) → команды."""
        assert self.runners is not None
        batches = {t.team: self.module.collect_sensors(t.team) for t in self.teams}
        for team, reply in self.runners.exchange(batches).items():
            self.module.apply_commands(team, reply)

    def close(self) -> None:
        """Остановить раннеры кода игрока."""
        if self.runners is not None:
            self.runners.close()

    def __enter__(self) -> Simulation:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def run(self, max_steps: int | None = None) -> RunStats:
        """Шагать до конца матча (или `max_steps` шагов)."""
        start = self.clock.step
        while not self.finished and (max_steps is None or self.clock.step - start < max_steps):
            self.step()
        return RunStats(self.clock.step - start, (self.clock.step - start) * self.clock.dt)
