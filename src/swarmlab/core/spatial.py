"""Равномерная 2D-сетка для поиска соседей за O(N·k) (ARCHITECTURE §6).

Общий инструмент ядра, не знает о предметной области модуля. Точки раскладываются
по клеткам квадратной области `[-half_size, half_size]²` (точки снаружи попадают в
крайние клетки — это не теряет пар, только добавляет кандидатов). Клетки
нумеруются построчно, точки сортируются по клетке устойчивой сортировкой, поэтому
порядок результатов детерминирован.

Запрос «кто в радиусе» перебирает только клетки в квадрате радиуса вокруг
каждой точки-запроса. Всё векторно: никаких циклов Python по точкам.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Pairs:
    """Пары «запрос → точка», отсортированы по запросу, затем по порядку точек в сетке.

    `query`, `point` — индексы `(K,)`; `delta` — `point_pos − query_pos` `(K,D)`;
    `dist` — длины `delta` `(K,)`.
    """

    query: np.ndarray
    point: np.ndarray
    delta: np.ndarray
    dist: np.ndarray

    def __len__(self) -> int:
        return int(self.query.shape[0])

    def select(self, mask: np.ndarray) -> Pairs:
        return Pairs(self.query[mask], self.point[mask], self.delta[mask], self.dist[mask])

    def counts(self, n_queries: int) -> np.ndarray:
        """Число пар у каждого запроса `(n_queries,)`."""
        return np.bincount(self.query, minlength=n_queries)


def expand(counts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Развернуть счётчики в пары (владелец, номер внутри владельца).

    `counts = [2, 0, 3]` → владельцы `[0, 0, 2, 2, 2]`, номера `[0, 1, 0, 1, 2]`.
    """
    counts = np.asarray(counts, dtype=np.int64)
    owner = np.repeat(np.arange(counts.shape[0]), counts)
    first = np.cumsum(counts) - counts
    local = np.arange(owner.shape[0]) - first[owner]
    return owner, local


class UniformGrid:
    """Индекс точек в равномерной сетке на плоскости xy."""

    def __init__(self, half_size: float, cell: float) -> None:
        if cell <= 0:
            raise ValueError(f"Размер клетки должен быть > 0, получено {cell}")
        self.half_size = float(half_size)
        self.cell = float(cell)
        self.n = max(1, int(np.ceil(2 * self.half_size / self.cell)))
        self._order = np.zeros(0, dtype=np.int64)
        self._sorted_cell = np.zeros(0, dtype=np.int64)
        self._pos = np.zeros((0, 2))

    @property
    def size(self) -> int:
        """Число точек в индексе."""
        return int(self._order.shape[0])

    def cell_of(self, xy: np.ndarray) -> np.ndarray:
        """Координаты клеток `(N,2)` (ix, iy) для точек `xy (N,2)`, обрезанные по сетке."""
        c = np.floor((np.asarray(xy)[:, :2] + self.half_size) / self.cell).astype(np.int64)
        return np.clip(c, 0, self.n - 1)

    def build(self, pos: np.ndarray) -> None:
        """Проиндексировать точки `pos (N,2)` или `(N,3)` (расстояния — по всем осям)."""
        pos = np.asarray(pos, dtype=np.float64)
        c = self.cell_of(pos)
        cell_id = c[:, 1] * self.n + c[:, 0]
        self._order = np.argsort(cell_id, kind="stable")
        self._sorted_cell = cell_id[self._order]
        self._pos = pos

    def candidates(self, query_xy: np.ndarray, radius: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Пары-кандидаты (индекс запроса, индекс точки) из клеток в квадрате радиуса."""
        query_xy = np.asarray(query_xy, dtype=np.float64)
        q = query_xy.shape[0]
        radius = np.broadcast_to(np.asarray(radius, dtype=np.float64), (q,))
        if q == 0 or self.size == 0:
            z = np.zeros(0, dtype=np.int64)
            return z, z.copy()
        c = self.cell_of(query_xy)
        s = np.ceil(radius / self.cell).astype(np.int64)
        x0 = np.clip(c[:, 0] - s, 0, self.n - 1)
        x1 = np.clip(c[:, 0] + s, 0, self.n - 1)
        y0 = np.clip(c[:, 1] - s, 0, self.n - 1)
        y1 = np.clip(c[:, 1] + s, 0, self.n - 1)

        # Строки сетки, которые смотрит каждый запрос: в каждой строке клетки
        # [x0, x1] лежат подряд, значит и их точки — один отрезок в `_order`.
        # Границы отрезка — двоичным поиском: память и время не зависят от числа клеток.
        row_q, row_k = expand(y1 - y0 + 1)
        row_y = y0[row_q] + row_k
        lo = np.searchsorted(self._sorted_cell, row_y * self.n + x0[row_q], side="left")
        hi = np.searchsorted(self._sorted_cell, row_y * self.n + x1[row_q], side="right")

        pair_row, pair_k = expand(hi - lo)
        query = row_q[pair_row]
        point = self._order[lo[pair_row] + pair_k]
        return query, point

    def within(
        self,
        query_pos: np.ndarray,
        radius: np.ndarray | float,
        *,
        exclude_self: bool = False,
    ) -> Pairs:
        """Точки на расстоянии ≤ `radius` от каждого запроса (расстояние — по всем осям `pos`).

        `exclude_self=True` — запросы и точки одни и те же (индексы совпадают),
        пары «сам с собой» отбрасываются.
        """
        query_pos = np.asarray(query_pos, dtype=np.float64)
        radius = np.broadcast_to(np.asarray(radius, dtype=np.float64), (query_pos.shape[0],))
        query, point = self.candidates(query_pos[:, :2], radius)
        delta = self._pos[point] - query_pos[query]
        dist = np.sqrt(np.einsum("ij,ij->i", delta, delta))
        keep = dist <= radius[query]
        if exclude_self:
            keep &= query != point
        return Pairs(query[keep], point[keep], delta[keep], dist[keep])
