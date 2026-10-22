"""`core.program`: генератор `step()` между тиками (DECISIONS №57) — без модулей."""

import pytest

from swarmlab.core.program import DONE, FAILED, RUNNING, Order, Program, ProgramError, Wait


def test_order_waits_for_module_status_and_sends_result():
    got = []

    def step():
        got.append((yield Order(["fly_to", 1.0, 2.0, None, None, True])))

    p = Program(step())
    assert p.start(now=0.0, next_seq=7)
    assert p.seq == 7 and isinstance(p.waiting, Order)
    assert p.poll(0.1, None) is None and not p.acknowledged(None)  # команда не дошла
    assert p.poll(0.1, [7, RUNNING]) is None and p.acknowledged([7, RUNNING])
    assert p.poll(0.2, [6, DONE]) is None  # статус чужого ожидания не считается
    assert p.poll(0.3, [7, FAILED]) is False
    assert not p.resume(False, 0.3, 8)  # генератор закончился
    assert got == [False]


def test_wait_one_tick_and_seconds_and_bare_yield():
    def step():
        yield
        yield Wait()
        yield Wait(2.0)

    p = Program(step())
    assert p.start(0.0, 1) and p.seq == 0
    assert p.poll(0.0, None) is None and p.poll(0.1, None) is True
    assert p.resume(True, 0.1, 2)
    assert p.poll(0.2, None) is True
    assert p.resume(True, 0.2, 3)
    assert p.poll(2.1, None) is None
    assert p.poll(0.2 + 2.0 - 1e-9, None) is True  # накопленная ошибка часов не мешает


def test_instant_order_lasts_one_tick():
    def step():
        yield Order(["fly_dir", 1.0, 0.0, 0.0, None], instant=True)

    p = Program(step())
    assert p.start(1.0, 5) and p.seq == 0 and p.acknowledged(None)
    assert p.poll(1.0, None) is None and p.poll(1.1, None) is True


def test_yield_of_wrong_value_is_an_error_and_closes():
    closed = []

    def step():
        try:
            yield 42
        finally:
            closed.append(True)

    with pytest.raises(ProgramError, match="yield ждёт команду"):
        Program(step()).start(0.0, 1)
    assert closed == [True]


def test_close_runs_finally():
    log = []

    def step():
        try:
            yield Wait()
        finally:
            log.append("finally")

    p = Program(step())
    p.start(0.0, 1)
    p.close()
    assert log == ["finally"]
