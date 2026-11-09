"""Сообщения пчёл своему улью (BEES_SPEC §5.2, DECISIONS №87).

`say(слово, место)` — слово и (необязательно) точка на карте. Сообщение,
отправленное на тике `t`, доставляется на тике `t + 1` всем живым пчёлам того же
улья в радиусе связи от точки отправки и улью — если в радиусе его леток. Пчёлы
внутри улья находятся у летка: слышат то, что сказано в радиусе от летка, а их
сообщения звучат у летка. Чужие ульи сообщений не получают. Хранение — массивы
(SoA), доставка — пространственная сетка.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from swarmlab.core.spatial import UniformGrid


@dataclass(frozen=True)
class Delivery:
    """Доставленные на тике сообщения.

    Пары «получатель–сообщение» отсортированы по получателю, затем по порядку
    отправки: `receiver (K,)` — слот получателя, `message (K,)` — номер сообщения.
    Сами сообщения: `sender_uid (M,)`, `sender_pos (M,3)`, `words` — слова,
    `where (M,2)` — названное место (NaN — места нет). `hive_inbox[h]` — номера
    сообщений для улья `h`.
    """

    receiver: np.ndarray
    message: np.ndarray
    sender_uid: np.ndarray
    sender_pos: np.ndarray
    words: list[str]
    where: np.ndarray
    hive_inbox: list[np.ndarray]

    @classmethod
    def empty(cls, n_hives: int) -> Delivery:
        z = np.zeros(0, dtype=np.int64)
        return cls(z, z.copy(), z.copy(), np.zeros((0, 3)), [], np.zeros((0, 2)),
                   [z.copy() for _ in range(n_hives)])

    def row(self, i: int) -> dict:
        """Сообщение `i` в формате протокола: `{from_id, word, where, from}`."""
        wx, wy = self.where[i].tolist()
        return {
            "from_id": int(self.sender_uid[i]),
            "word": self.words[i],
            "where": None if math.isnan(wx) else [wx, wy],
            "from": self.sender_pos[i].tolist(),
        }


class MessageBoard:
    """Очередь сообщений текущего тика и доставка на следующем."""

    def __init__(self, n_hives: int, radius: float) -> None:
        self.n_hives = n_hives
        self.radius = radius
        self._slot: list[int] = []
        self._uid: list[int] = []
        self._hive: list[int] = []
        self._pos: list[np.ndarray] = []
        self._words: list[str] = []
        self._where: list[tuple[float, float]] = []

    def __len__(self) -> int:
        return len(self._slot)

    def post(
        self, slot: int, uid: int, hive: int, pos: np.ndarray, word: str,
        where: tuple[float, float] = (math.nan, math.nan),
    ) -> None:
        """Поставить сообщение в очередь (доставка на следующем тике); `slot = −1` — улей."""
        self._slot.append(int(slot))
        self._uid.append(int(uid))
        self._hive.append(int(hive))
        self._pos.append(np.asarray(pos, dtype=np.float64).copy())
        self._words.append(str(word))
        self._where.append((float(where[0]), float(where[1])))

    def deliver(
        self,
        grid: UniformGrid,
        receiver_slots: np.ndarray,
        receiver_hive: np.ndarray,
        entrance: np.ndarray,
        inside_slots: np.ndarray,
        inside_hive: np.ndarray,
    ) -> Delivery:
        """Доставить накопленное и очистить очередь.

        `grid` проиндексирован по позициям пчёл в воздухе; `receiver_slots`,
        `receiver_hive` — их слоты и ульи в том же порядке. `inside_slots`,
        `inside_hive` — пчёлы в ульях (слышат у летка).
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
        msg, recv = pairs.query[keep], recv[keep]
        to_entrance = np.linalg.norm(entrance[hive] - pos, axis=1)
        heard_at_door = to_entrance <= self.radius
        # Пчёлы в улье: сообщения, сказанные в радиусе от летка своего улья.
        if inside_slots.size and np.any(heard_at_door):
            m_idx, i_idx = np.nonzero(
                heard_at_door[:, None] & (hive[:, None] == inside_hive[None, :])
            )
            r = inside_slots[i_idx]
            own = r != sender_slot[m_idx]
            msg = np.concatenate([msg, m_idx[own]])
            recv = np.concatenate([recv, r[own]])
        order = np.lexsort((msg, recv))  # по получателю, затем по порядку отправки
        inbox = [np.flatnonzero((hive == h) & heard_at_door) for h in range(self.n_hives)]
        out = Delivery(
            receiver=recv[order],
            message=msg[order],
            sender_uid=np.array(self._uid, dtype=np.int64),
            sender_pos=pos,
            words=list(self._words),
            where=np.array(self._where, dtype=np.float64).reshape(-1, 2),
            hive_inbox=inbox,
        )
        self.clear()
        return out

    def clear(self) -> None:
        self._slot.clear()
        self._uid.clear()
        self._hive.clear()
        self._pos.clear()
        self._words.clear()
        self._where.clear()
