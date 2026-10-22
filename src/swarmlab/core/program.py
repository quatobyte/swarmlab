"""Программы агентов: `step()` с `yield` (DECISIONS №57–59).

Если `step()` агента — функция-генератор, хост в раннере держит генератор между
тиками и возобновляет его, когда ожидание закончилось. Ядро и модуль генератора
не видят: от раннера приходит обычная команда с номером ожидания `wait`, а модуль
отвечает статусом в сенсорах агента (ARCHITECTURE §3.3).

Что можно отдать в `yield`:

* `Order` — жетон команды (его возвращают методы-команды API модуля). Ждём, пока
  модуль сообщит «выполнено» (`True`) или «не вышло» (`False`). Если у команды нет
  естественного конца (`Order.instant`), ожидание длится один тик и даёт `True`.
* `Wait(seconds)` — пропустить тик (`seconds = 0`) или ждать столько секунд
  игрового времени; результат `True`.
* `None` (голый `yield`) — то же, что `Wait()`.

Модуль не зависит ни от NumPy, ни от модулей-сценариев: его импортирует раннер.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

#: Статус ожидания в сенсорах агента: `[seq, состояние]`.
RUNNING, DONE, FAILED = 0, 1, 2
#: Запас при сравнении игрового времени (накопленная ошибка шага часов).
_TIME_EPS = 1e-6


@dataclass(frozen=True, slots=True)
class Wait:
    """Ждать: `seconds = 0` — один тик, иначе — столько секунд игрового времени."""

    seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class Order:
    """Жетон команды: что отправить модулю и нужно ли ждать её выполнения."""

    #: Команда движения в формате модуля, например `["fly_to", x, y, z, speed, avoid]`.
    move: list[Any]
    #: У команды нет естественного конца — ожидание длится один тик.
    instant: bool = False


class ProgramError(TypeError):
    """В `yield` отдано то, чего ждать нельзя."""


class Program:
    """Генератор `step()` одного агента между тиками."""

    def __init__(self, gen: Generator[Any, Any, Any]) -> None:
        self.gen = gen
        #: Чего ждём сейчас: `Order` или `Wait`.
        self.waiting: Order | Wait = Wait()
        #: Номер ожидания команды (0 — ждём не команду).
        self.seq = 0
        #: Игровое время, когда началось ожидание.
        self.since = 0.0

    def start(self, now: float, next_seq: int) -> bool:
        """Запустить до первого `yield`. `False` — генератор закончился сразу."""
        return self._run(None, now, next_seq, first=True)

    def resume(self, value: bool, now: float, next_seq: int) -> bool:
        """Продолжить с результатом ожидания. `False` — генератор закончился."""
        return self._run(value, now, next_seq, first=False)

    def _run(self, value: bool | None, now: float, next_seq: int, *, first: bool) -> bool:
        try:
            got = next(self.gen) if first else self.gen.send(value)
        except StopIteration:
            return False
        if got is None:
            got = Wait()
        if isinstance(got, Wait):
            self.seq = 0
        elif isinstance(got, Order):
            self.seq = 0 if got.instant else next_seq
        else:
            self.gen.close()
            raise ProgramError(
                f"yield ждёт команду (yield self.fly_to(...)) или wait(), а получено {got!r}"
            )
        self.waiting = got
        self.since = now
        return True

    def poll(self, now: float, status: list[int] | None) -> bool | None:
        """Результат ожидания на этом тике или `None` — ждать дальше.

        `status` — `[seq, состояние]` из сенсоров агента (или `None`).
        """
        w = self.waiting
        if isinstance(w, Wait):
            if w.seconds <= 0:
                return True if now > self.since else None
            return True if now + _TIME_EPS >= self.since + w.seconds else None
        if self.seq == 0:  # команда без конца — один тик
            return True if now > self.since else None
        if status is not None and int(status[0]) == self.seq and int(status[1]) != RUNNING:
            return int(status[1]) == DONE
        return None

    def acknowledged(self, status: list[int] | None) -> bool:
        """Модуль получил ожидаемую команду (иначе её надо отправить ещё раз)."""
        return self.seq == 0 or (status is not None and int(status[0]) == self.seq)

    def close(self) -> None:
        """Закрыть генератор: внутри выполнится `finally`."""
        self.gen.close()
