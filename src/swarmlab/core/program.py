"""Программы агентов: `loop()` по кругу в лёгком потоке `greenlet` (DECISIONS №84).

У каждого агента в раннере свой поток. Тело потока — `loop()` по кругу; конец
прохода — скрытое ожидание следующего тика (проход не чаще раза за тик). Команда,
которая ждёт выполнения, вызывает `request(Order(...))`: поток переключается
обратно в хост, хост отправляет команду модулю с номером ожидания `wait`, а когда
модуль ответил в сенсорах агента `me["wait"] = [seq, состояние, результат]`,
продолжает поток с результатом. `Wait(секунды)` хост отсчитывает сам по времени
сенсоров. Переключения делает только хост и строго по порядку агентов —
детерминизм не зависит от планировщика ОС: потоки `greenlet` не вытесняют друг
друга.

Ошибка в `loop()` выходит из `run()`/`resume()` в хост, поток после неё мёртв —
хост создаёт новый на следующем тике (проход с начала). `close()` бросает в поток
`GreenletExit`: `finally` игрока выполняется, команды внутри него не ждут.

Модуль не зависит ни от NumPy, ни от модулей-сценариев: его импортирует раннер.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from greenlet import GreenletExit, getcurrent, greenlet

#: Статус ожидания в сенсорах агента: `[seq, состояние, результат]`.
RUNNING, DONE, FAILED = 0, 1, 2
#: Запас при сравнении игрового времени (накопленная ошибка шага часов).
_TIME_EPS = 1e-6


@dataclass(frozen=True, slots=True)
class Wait:
    """Ждать: `seconds = 0` — до следующего тика, иначе — столько секунд игрового времени."""

    seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class Order:
    """Команда, выполнения которой ждут: что отправить модулю."""

    #: Команда движения в формате модуля, например `["fly_to", x, y, speed]`.
    move: list[Any]


@dataclass(frozen=True, slots=True)
class Outcome:
    """Чем закончилось ожидание: удалось ли и результат модуля (−1 — нет)."""

    ok: bool
    result: int = -1


#: Конец прохода `loop()` — ждать следующего тика.
_TICK = Wait(0.0)


class ProgramError(RuntimeError):
    """Команду, которая ждёт, вызвали не из `loop()`."""


class Program:
    """Поток `loop()` одного агента между тиками."""

    def __init__(self, loop: Callable[[], Any], on_pass: Callable[[], None] | None = None) -> None:
        self._loop = loop
        self._on_pass = on_pass
        self._g = greenlet(self._body)
        self._g.swarmlab_program = self  # type: ignore[attr-defined]
        #: Чего ждём сейчас: `Order` или `Wait` (`None` — поток ещё не запущен).
        self.waiting: Order | Wait | None = None
        #: Номер ожидания команды (0 — ждём не команду).
        self.seq = 0
        #: Игровое время, когда началось ожидание.
        self.since = 0.0
        #: Сколько проходов `loop()` начато.
        self.passes = 0
        #: Поток закрывается: команды в `finally` не ждут.
        self.closing = False

    def _body(self) -> None:
        while True:
            self.passes += 1
            if self._on_pass is not None:
                self._on_pass()
            self._loop()
            getcurrent().parent.switch(_TICK)

    @property
    def started(self) -> bool:
        return self.waiting is not None

    @property
    def dead(self) -> bool:
        return self._g.dead

    def run(self, now: float, next_seq: int, value: Any = None) -> None:
        """Запустить или продолжить поток до следующего ожидания.

        Исключение из `loop()` выходит отсюда; поток после него мёртв.
        """
        got = self._g.switch() if self.waiting is None else self._g.switch(value)
        if self._g.dead:
            return
        if isinstance(got, Order):
            self.seq = next_seq
        elif isinstance(got, Wait):
            self.seq = 0
        else:  # pragma: no cover — переключать в хост умеет только request()
            raise ProgramError(f"Поток отдал хосту {got!r}")
        self.waiting = got
        self.since = now

    def poll(self, now: float, status: list[int] | None) -> Outcome | None:
        """Результат ожидания на этом тике или `None` — ждать дальше.

        `status` — `[seq, состояние, результат]` из сенсоров агента (или `None`).
        """
        w = self.waiting
        if w is None:
            return Outcome(True)
        if isinstance(w, Wait):
            if w.seconds <= 0:
                return Outcome(True) if now > self.since + _TIME_EPS else None
            return Outcome(True) if now + _TIME_EPS >= self.since + w.seconds else None
        if status is not None and int(status[0]) == self.seq and int(status[1]) != RUNNING:
            result = int(status[2]) if len(status) > 2 else -1
            return Outcome(int(status[1]) == DONE, result)
        return None

    def acknowledged(self, status: list[int] | None) -> bool:
        """Модуль получил ожидаемую команду (иначе её надо отправить ещё раз)."""
        return self.seq == 0 or (status is not None and int(status[0]) == self.seq)

    def at_pass_end(self) -> bool:
        """Поток дошёл до конца прохода `loop()` и ждёт следующего тика."""
        return self.waiting is _TICK

    def close(self) -> None:
        """Закрыть поток: внутри выполнится `finally` (исключение из него выходит наружу)."""
        if self._g.dead or not self.started:
            return
        self.closing = True
        self._g.throw(GreenletExit)


def current_program() -> Program | None:
    """Программа, в потоке которой выполняется код (`None` — не в `loop()`)."""
    return getattr(getcurrent(), "swarmlab_program", None)


def request(token: Order | Wait) -> Outcome:
    """Ждать команду или время: переключиться в хост и вернуть итог.

    Вне `loop()` — `ProgramError`; в закрывающемся потоке — `GreenletExit`
    (после смерти агента ждать нечего).
    """
    program = current_program()
    if program is None:
        raise ProgramError("Ждать можно только внутри loop()")
    if program.closing:
        raise GreenletExit
    got = getcurrent().parent.switch(token)
    return got if isinstance(got, Outcome) else Outcome(True)
