"""Контракт физического бэкенда.

Ядро и модуль работают с физикой только через `PhysicsBackend`. Пчёлки реализуют
его на MuJoCo, «Карьер» — на MuJoCo + Chrono, «Город» — своим упрощённым
движком. Ядро не знает, какой движок внутри.

Тела адресуются индексами бэкенда `0..n_bodies-1` (а не идентификаторами движка),
все данные — массивы NumPy по всем телам сразу (структура массивов).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

#: Индекс «тела» для статического окружения (рельеф, деревья, стены) в `ContactList`.
STATIC = -1


@dataclass(frozen=True)
class ContactList:
    """Контакты текущего шага: пары тел и нормальные силы.

    `body_a`, `body_b` — индексы бэкенда (`STATIC` для статики), формы `(K,)`;
    `normal_force` — модуль нормальной силы контакта, Н, форма `(K,)`.
    """

    body_a: np.ndarray
    body_b: np.ndarray
    normal_force: np.ndarray

    @classmethod
    def empty(cls) -> ContactList:
        z = np.zeros(0, dtype=np.int64)
        return cls(z, z.copy(), np.zeros(0, dtype=np.float64))

    def __len__(self) -> int:
        return int(self.body_a.shape[0])


@runtime_checkable
class PhysicsBackend(Protocol):
    """Физический движок модуля. Все методы векторные: одна операция на все тела."""

    @property
    def timestep(self) -> float:
        """Шаг интегрирования движка, с. Совпадает с шагом физики ядра."""
        ...

    @property
    def n_bodies(self) -> int:
        """Число управляемых тел (размер пула)."""
        ...

    def step(self, n_substeps: int = 1) -> None:
        """Продвинуть физику на `n_substeps` шагов по `timestep`."""
        ...

    def set_forces(
        self,
        body_ids: np.ndarray,
        forces: np.ndarray,
        torques: np.ndarray | None = None,
    ) -> None:
        """Задать внешние силы `(K,3)` (Н, мировая СК, в центре масс) и моменты `(K,3)`.

        Силы действуют до следующего вызова; тела, не попавшие в `body_ids`,
        сохраняют прежние силы.
        """
        ...

    def poses(self) -> tuple[np.ndarray, np.ndarray]:
        """Позиции `(N,3)` и кватернионы `(N,4)` (w, x, y, z) всех тел."""
        ...

    def velocities(self) -> np.ndarray:
        """Скорости `(N,6)`: линейная (мировая СК) и угловая."""
        ...

    def contacts(self) -> ContactList:
        """Контакты, возникшие на последнем шаге."""
        ...

    def set_active(self, body_ids: np.ndarray, active: np.ndarray) -> None:
        """Включить/выключить тела пула (выключенные «припаркованы»: без столкновений и сил)."""
        ...
