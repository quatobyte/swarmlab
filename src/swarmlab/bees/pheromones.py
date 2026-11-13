"""Феромоны (BEES_SPEC §5.2): у каждого улья своя 2D-сетка, 4 канала.

`mark` добавляет значение в клетку под пчелой, испарение — экспонента с
полураспадом `half_life_s`. Пчела видит окно 3×3 клетки вокруг себя и градиент
по каждому каналу (центральные разности, единицы — значение на метр). Клетки за
краем карты читаются как 0. Всё векторно по пчёлам.

Испарение — за O(1): сетка хранит значения, делённые на общий множитель, и
испарение меняет только множитель.
"""

from __future__ import annotations

import numpy as np

from swarmlab.bees.params import PheromoneParams


class PheromoneField:
    """Сетки феромонов всех ульев: массив `(H, n, n, C)`, индекс `[h, iy, ix, c]`."""

    def __init__(self, n_hives: int, map_size: float, params: PheromoneParams) -> None:
        self.params = params
        self.cell = params.cell
        self.half_size = map_size / 2
        self.n = int(np.ceil(map_size / params.cell))
        self._raw = np.zeros((n_hives, self.n, self.n, params.channels))
        self._scale = 1.0

    @property
    def values(self) -> np.ndarray:
        """Текущие значения `(H, n, n, C)` (копия)."""
        return self._raw * self._scale

    def cell_of(self, xy: np.ndarray) -> np.ndarray:
        """Клетки `(N,2)` (ix, iy) точек; за картой — ближайшая крайняя клетка."""
        c = np.floor((xy[:, :2] + self.half_size) / self.cell).astype(np.int64)
        return np.clip(c, 0, self.n - 1)

    def mark(
        self, hive: np.ndarray, xy: np.ndarray, channel: np.ndarray, amount: np.ndarray
    ) -> None:
        """Добавить `amount` в канал `channel` клетки под каждой точкой `xy`."""
        hive = np.atleast_1d(hive)
        channel = np.atleast_1d(channel)
        if np.any((channel < 0) | (channel >= self.params.channels)):
            raise ValueError(f"Канал феромона — от 0 до {self.params.channels - 1}")
        c = self.cell_of(np.atleast_2d(xy))
        np.add.at(self._raw, (hive, c[:, 1], c[:, 0], channel),
                  np.asarray(amount, dtype=np.float64) / self._scale)

    def decay(self, dt: float) -> None:
        """Испарение за `dt` секунд."""
        self._scale *= 0.5 ** (dt / self.params.half_life_s)
        if self._scale < 1e-150:  # раз в несколько часов матча — без потери точности
            self._raw *= self._scale
            self._scale = 1.0

    def sample(self, hive: np.ndarray, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Окна 3×3 `(N,3,3,C)` (`[dy+1][dx+1]`, dy — по +y) и градиенты `(N,C,2)` (∂/∂x, ∂/∂y)."""
        hive = np.atleast_1d(hive)
        n_pts = hive.shape[0]
        c = np.floor((np.atleast_2d(xy)[:, :2] + self.half_size) / self.cell).astype(np.int64)
        off = np.arange(-1, 2)
        iy = c[:, 1, None, None] + off[None, :, None]  # (N,3,1)
        ix = c[:, 0, None, None] + off[None, None, :]  # (N,1,3)
        iy, ix = np.broadcast_arrays(iy, ix)
        inside = (iy >= 0) & (iy < self.n) & (ix >= 0) & (ix < self.n)
        h = np.broadcast_to(hive[:, None, None], iy.shape)
        win = self._raw[h, np.clip(iy, 0, self.n - 1), np.clip(ix, 0, self.n - 1)]
        win = np.where(inside[..., None], win * self._scale, 0.0)
        grad = np.empty((n_pts, self.params.channels, 2))
        grad[:, :, 0] = (win[:, 1, 2] - win[:, 1, 0]) / (2 * self.cell)
        grad[:, :, 1] = (win[:, 2, 1] - win[:, 0, 1]) / (2 * self.cell)
        return win, grad
