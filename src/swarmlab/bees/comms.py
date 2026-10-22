"""Сообщения пчёл своему улью (BEES_SPEC §5.2).

`signal(*values)` — до `max_values` чисел. Сообщение, отправленное на тике `t`,
доставляется на тике `t + 1` всем живым пчёлам того же улья, которые находятся в
радиусе связи от точки отправки, и улью — если в радиусе его леток. Чужие ульи
сообщений не получают. Хранение — массивы (SoA), доставка — пространственная сетка.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from swarmlab.core.spatial import UniformGrid


@dataclass(frozen=True)
class Delivery:
    """Доставленные на тике сообщения.

    Пары «получатель–сообщение» отсортированы по получателю, затем по порядку
    отправки: `receiver (K,)` — слот получателя, `message (K,)` — номер сообщения,
    `rel_pos (K,3)` — точка отправки относительно получателя. Сами сообщения:
    `sender_uid (M,)`, `values` — список кортежей. `hive_inbox[h]` — номера
    сообщений для улья `h`.
    """

    receiver: np.ndarray
    message: np.ndarray
    rel_pos: np.ndarray
    sender_uid: np.ndarray
    sender_pos: np.ndarray
    values: list[tuple[float, ...]]
    hive_inbox: list[np.ndarray]

    @classmethod
    def empty(cls, n_hives: int) -> Delivery:
        z = np.zeros(0, dtype=np.int64)
        return cls(z, z.copy(), np.zeros((0, 3)), z.copy(), np.zeros((0, 3)), [],
                   [z.copy() for _ in range(n_hives)])


class MessageBoard:
    """Очередь сообщений текущего тика и доставка на следующем."""

    def __init__(self, n_hives: int, radius: float, max_values: int) -> None:
        self.n_hives = n_hives
        self.radius = radius
        self.max_values = max_values
        self._slot: list[int] = []
        self._uid: list[int] = []
        self._hive: list[int] = []
        self._pos: list[np.ndarray] = []
        self._values: list[tuple[float, ...]] = []

    def __len__(self) -> int:
        return len(self._slot)

    def post(
        self, slot: int, uid: int, hive: int, pos: np.ndarray, values: Sequence[float]
    ) -> None:
        """Поставить сообщение пчелы в очередь (доставка на следующем тике)."""
        vals = tuple(float(v) for v in values)
        if len(vals) > self.max_values:
            raise ValueError(f"signal(): не больше {self.max_values} чисел, получено {len(vals)}")
        self._slot.append(int(slot))
        self._uid.append(int(uid))
        self._hive.append(int(hive))
        self._pos.append(np.asarray(pos, dtype=np.float64).copy())
        self._values.append(vals)

    def deliver(
        self,
        grid: UniformGrid,
        receiver_slots: np.ndarray,
        receiver_hive: np.ndarray,
        entrance: np.ndarray,
    ) -> Delivery:
        """Доставить накопленное и очистить очередь.

        `grid` проиндексирован по позициям получателей-кандидатов (живых пчёл в
        воздухе); `receiver_slots`, `receiver_hive` — их слоты и ульи в том же порядке.
        """
        if not self._slot:
            return Delivery.empty(self.n_hives)
        sender_slot = np.array(self._slot, dtype=np.int64)
        hive = np.array(self._hive, dtype=np.int64)
        pos = np.array(self._pos)
        pairs = grid.within(pos, self.radius)
        recv = receiver_slots[pairs.point]
        keep = (receiver_hive[pairs.point] == hive[pairs.query]) & (
            recv != sender_slot[pairs.query]
        )
        msg, recv, rel = pairs.query[keep], recv[keep], -pairs.delta[keep]
        order = np.lexsort((msg, recv))  # по получателю, затем по порядку отправки
        to_entrance = np.linalg.norm(entrance[hive] - pos, axis=1)
        inbox = [np.flatnonzero((hive == h) & (to_entrance <= self.radius))
                 for h in range(self.n_hives)]
        out = Delivery(
            receiver=recv[order],
            message=msg[order],
            rel_pos=rel[order],
            sender_uid=np.array(self._uid, dtype=np.int64),
            sender_pos=pos,
            values=list(self._values),
            hive_inbox=inbox,
        )
        self.clear()
        return out

    def clear(self) -> None:
        self._slot.clear()
        self._uid.clear()
        self._hive.clear()
        self._pos.clear()
        self._values.clear()
