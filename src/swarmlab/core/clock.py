"""Часы симуляции: фиксированный шаг физики и производные частоты.

Время считается целым числом шагов, а не накоплением float, поэтому не
дрейфует. Часы не читают системное время: темп «как в реальности» задаёт
`RealtimePacer`, которому реальное время передаёт внешний цикл (CLI, сервер).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rates:
    """Частоты симуляции, Гц. Частоты решений и кадров должны делить частоту физики."""

    physics_hz: int = 200
    decision_hz: int = 10
    frame_hz: int = 10

    def __post_init__(self) -> None:
        for name in ("decision_hz", "frame_hz"):
            hz = getattr(self, name)
            if hz <= 0 or self.physics_hz % hz != 0:
                raise ValueError(
                    f"{name}={hz} должна быть > 0 и делить physics_hz={self.physics_hz}"
                )


class Clock:
    """Счётчик шагов физики с признаками тиков решений и кадров."""

    def __init__(self, rates: Rates) -> None:
        self.rates = rates
        self.dt = 1.0 / rates.physics_hz
        self.steps_per_decision = rates.physics_hz // rates.decision_hz
        self.steps_per_frame = rates.physics_hz // rates.frame_hz
        self.step = 0

    @property
    def time(self) -> float:
        """Время симуляции, с."""
        return self.step * self.dt

    @property
    def decision_tick(self) -> int:
        """Номер текущего (или последнего прошедшего) тика решений."""
        return self.step // self.steps_per_decision

    @property
    def is_decision_step(self) -> bool:
        """На этом шаге физики начинается новый тик решений."""
        return self.step % self.steps_per_decision == 0

    @property
    def is_frame_step(self) -> bool:
        """На этом шаге физики снимается кадр."""
        return self.step % self.steps_per_frame == 0

    def advance(self) -> None:
        self.step += 1

    def steps_for(self, seconds: float) -> int:
        """Сколько шагов физики занимает `seconds` секунд симуляции (с округлением)."""
        return round(seconds * self.rates.physics_hz)


class RealtimePacer:
    """Накопитель времени для живого режима.

    Внешний цикл сообщает прошедшее реальное время, пейсер отвечает, сколько шагов
    физики пора сделать. Если машина не успевает, симуляция просто идёт медленнее
    реального времени — шаг физики не меняется. `max_lag_s` не даёт накопить
    «долг» после паузы (например, пока окно вьюера перетаскивали).
    """

    def __init__(self, dt: float, speed: float = 1.0, max_lag_s: float = 0.25) -> None:
        self.dt = dt
        self.speed = speed
        self.max_lag_s = max_lag_s
        self._budget = 0.0

    def steps_due(self, wall_elapsed_s: float) -> int:
        """Добавить прошедшее реальное время и вернуть число шагов к выполнению."""
        self._budget = min(self._budget + wall_elapsed_s * self.speed, self.max_lag_s)
        n = int(self._budget / self.dt)
        self._budget -= n * self.dt
        return n
