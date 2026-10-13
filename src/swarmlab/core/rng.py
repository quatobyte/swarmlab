"""Реестр генераторов случайных чисел.

Вся случайность симуляции берётся отсюда. Из одного seed матча реестр выдаёт
независимые потоки `numpy.random.Generator` по именам подсистем (`world`,
`weather`, `enemies`, `sensor_noise`…). Поток зависит только от seed и имени,
поэтому добавление новой подсистемы не сдвигает уже существующие.
"""

from __future__ import annotations

import hashlib

import numpy as np


def _name_key(name: str) -> int:
    """Стабильный (не зависящий от PYTHONHASHSEED) 64-битный ключ имени потока."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


class RngRegistry:
    """Seed матча → именованные независимые потоки случайных чисел."""

    def __init__(self, seed: int) -> None:
        if seed < 0:
            raise ValueError(f"seed должен быть неотрицательным, получено {seed}")
        self._seed = int(seed)
        self._streams: dict[str, np.random.Generator] = {}

    @property
    def seed(self) -> int:
        return self._seed

    def get(self, name: str) -> np.random.Generator:
        """Поток подсистемы `name`. Повторный вызов возвращает тот же объект (с его состоянием)."""
        gen = self._streams.get(name)
        if gen is None:
            gen = self.fresh(name)
            self._streams[name] = gen
        return gen

    def __call__(self, name: str) -> np.random.Generator:
        return self.get(name)

    def fresh(self, name: str) -> np.random.Generator:
        """Новый генератор потока `name` с начального состояния (не кэшируется)."""
        seq = np.random.SeedSequence(entropy=self._seed, spawn_key=(_name_key(name),))
        return np.random.Generator(np.random.PCG64(seq))
