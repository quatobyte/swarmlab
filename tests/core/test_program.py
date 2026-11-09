"""`core.program`: `loop()` в потоке `greenlet` между тиками (DECISIONS №84) — без модулей."""

import pytest

from swarmlab.core.program import (
    DONE,
    FAILED,
    RUNNING,
    Order,
    Outcome,
    Program,
    ProgramError,
    Wait,
    request,
)


def test_order_waits_for_module_status_and_sends_result():
    got = []

    def loop():
        got.append(request(Order(["fly_to", 1.0, 2.0, None])))
        request(Wait(100.0))

    p = Program(loop)
    p.run(now=0.0, next_seq=7)
    assert p.seq == 7 and isinstance(p.waiting, Order)
    assert p.poll(0.1, None) is None and not p.acknowledged(None)  # команда не дошла
    assert p.poll(0.1, [7, RUNNING, -1]) is None and p.acknowledged([7, RUNNING, -1])
    assert p.poll(0.2, [6, DONE, -1]) is None  # статус чужого ожидания не считается
    out = p.poll(0.3, [7, FAILED, -1])
    assert out == Outcome(False, -1)
    p.run(0.3, 8, out)
    assert got == [Outcome(False, -1)] and isinstance(p.waiting, Wait)


def test_result_of_command_reaches_loop():
    got = []

    def loop():
        got.append(request(Order(["search", 1.0, 2.0, None])).result)

    p = Program(loop)
    p.run(0.0, 1)
    p.run(0.1, 2, p.poll(0.1, [1, DONE, 42]))
    assert got == [42]


def test_wait_seconds_and_next_tick():
    marks = []

    def loop():
        marks.append("a")
        request(Wait())
        marks.append("b")
        request(Wait(2.0))
        marks.append("c")

    p = Program(loop)
    p.run(0.0, 1)
    assert p.poll(0.0, None) is None  # тот же тик
    p.run(0.1, 2, p.poll(0.1, None))
    assert marks == ["a", "b"]
    assert p.poll(1.0, None) is None
    p.run(2.1, 3, p.poll(2.1, None))
    assert marks == ["a", "b", "c"] and p.at_pass_end()


def test_pass_without_commands_once_per_tick():
    passes = []

    def loop():
        passes.append(1)

    p = Program(loop, on_pass=lambda: passes.append("pass"))
    p.run(0.0, 1)
    assert p.at_pass_end() and passes == ["pass", 1]
    assert p.poll(0.0, None) is None  # второй проход в том же тике — нет
    for t in (0.1, 0.2, 0.3):
        p.run(t, 1, p.poll(t, None))
    assert p.passes == 4 and passes.count(1) == 4


def test_error_in_loop_leaves_program_dead():
    def loop():
        raise ValueError("ой")

    p = Program(loop)
    with pytest.raises(ValueError):
        p.run(0.0, 1)
    assert p.dead


def test_close_runs_finally_and_commands_inside_do_not_wait():
    events = []

    def loop():
        try:
            request(Order(["fly_to", 0.0, 0.0, None]))
        finally:
            events.append("finally")
            with pytest.raises(BaseException):  # noqa: B017 — GreenletExit: ждать некому
                request(Wait(1.0))
            events.append("after")

    p = Program(loop)
    p.run(0.0, 1)
    p.close()
    assert events == ["finally", "after"] and p.dead


def test_request_outside_loop_is_an_error():
    with pytest.raises(ProgramError, match="loop"):
        request(Wait())
