"""Цикл симуляции: три частоты (физика, решения, кадры) поверх `Module`.

Симуляция не читает системное время и не делает ввод-вывод: headless-прогон,
живой режим, вьюеры и сервер — внешние циклы, которые вызывают `step()`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from swarmlab.core.clock import Clock
from swarmlab.core.config import MatchConfig
from swarmlab.core.module import Frame, Module, load_module
from swarmlab.core.physics import PhysicsBackend
from swarmlab.core.rng import RngRegistry

FrameCallback = Callable[[Frame], None]


@dataclass(frozen=True)
class RunStats:
    """Итог прогона: сколько шагов сделано и сколько прошло времени симуляции."""

    steps: int
    sim_time: float


class Simulation:
    """Матч: модуль + физика + часы."""

    def __init__(
        self,
        cfg: MatchConfig,
        module: Module | None = None,
        on_frame: FrameCallback | None = None,
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
        if self.teams:
            # Раннеры кода игрока появятся в вехе M2.
            raise NotImplementedError("Команды с кодом игрока поддерживаются начиная с вехи M2")

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
        self.module.pre_physics(clock.dt)
        self.physics.step(1)
        self.module.post_physics(clock.dt)
        clock.advance()
        if self.on_frame is not None and clock.is_frame_step:
            self.on_frame(self.module.snapshot())

    def run(self, max_steps: int | None = None) -> RunStats:
        """Шагать до конца матча (или `max_steps` шагов)."""
        start = self.clock.step
        while not self.finished and (max_steps is None or self.clock.step - start < max_steps):
            self.step()
        return RunStats(self.clock.step - start, (self.clock.step - start) * self.clock.dt)
