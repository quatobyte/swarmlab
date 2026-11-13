"""M8: `loop()` без `yield` — хост раннера без процесса (DECISIONS №84–87).

Точный контроль тиков и статусов: сенсоры в формате протокола подаются руками,
команды читаются из `CommandBatch`. Настоящий матч с раннером — `test_m8_match.py`.
"""

import pytest

from swarmlab.bees.api import Collector, Hive, Scout, Worker
from swarmlab.bees.player_host import HiveHost
from swarmlab.core.program import DONE, FAILED, RUNNING
from swarmlab.core.protocol import SensorBatch


def raw_bee(uid: int, tick: int, *, kind: str = "forager", wait=None, x: float = 0.0,
            messages=(), epoch: int = 0, auto_home: bool = False, in_hive: bool = False,
            energy: float = 100.0, found=None, flowers=()) -> dict:
    """Сенсоры летающей пчелы в формате протокола (sensors.py)."""
    me = {
        "id": uid, "kind": kind, "pos": [x, 0.0, 5.0], "energy": energy, "energy_max": 100.0,
        "cargo": 0.0, "cargo_max": 1.5 if kind == "forager" else 0.0, "in_hive": in_hive,
        "auto_home": auto_home, "epoch": epoch,
    }
    if wait is not None:
        me["wait"] = wait
    if found is not None:
        me["found"] = found
    return {
        "time": round(tick * 0.1, 6), "me": me, "home": [0.0, 0.0, 1.0],
        "flowers": list(flowers), "bees": [], "messages": list(messages),
        "smell": [0.0] * 4, "smell_way": [[0.0, 0.0]] * 4,
    }


def msg(sender: int, word: str, where=None) -> dict:
    return {"from_id": sender, "word": word, "where": where, "from": [1.0, 2.0, 3.0]}


def batch(tick: int, *agents: dict, view: dict | None = None) -> SensorBatch:
    return SensorBatch(tick=tick, team=0, budget_ms=20.0, team_view=view or {},
                       agents=list(agents))


def hive_view(tick: int, **kw) -> dict:
    view = {
        "time": round(tick * 0.1, 6), "honey": 10.0, "nectar": 0.0,
        "counts": {"scout": {"in_hive": 1, "flying": 2}, "forager": {"in_hive": 3, "flying": 4},
                   "house": 5},
        "busy": 15, "max_bees": 20, "costs": {"scout": 3.0, "forager": 4.0, "house": 2.0},
        "messages": [], "notes": [],
    }
    view.update(kw)
    return view


def host_with(**classes: type) -> tuple[HiveHost, list[str]]:
    log: list[str] = []
    host = HiveHost(log.append)
    host.classes.update(classes)
    return host, log


EVENTS: list[tuple] = []


class Courier(Collector):
    """Летит, ждёт результата; в `finally` отмечает закрытие."""

    def loop(self):
        EVENTS.append(("start",))
        try:
            ok = self.fly_to(10.0, 0.0)
            EVENTS.append(("arrived", ok, self.pos.x))
            self.wait(1.0)
        finally:
            EVENTS.append(("finally",))


@pytest.fixture(autouse=True)
def _clear_events():
    EVENTS.clear()


# ===================================================================== команды ждут без yield


def test_commands_wait_without_yield_and_resume_with_result():
    host, log = host_with(forager=Courier)
    out = host.step(batch(0, raw_bee(5, 0)))
    cmd = out.commands[5]
    assert cmd["move"] == ["fly_to", 10.0, 0.0, None] and cmd["wait"] > 0
    seq = cmd["wait"]
    # Пока модуль говорит «идёт» — пчела продолжает команду, новых команд нет.
    assert host.step(batch(1, raw_bee(5, 1, wait=[seq, RUNNING, -1]))).commands == {}
    assert EVENTS == [("start",)]
    # Выполнено → loop() продолжается со свежими сенсорами.
    host.step(batch(2, raw_bee(5, 2, wait=[seq, DONE, -1], x=9.8)))
    assert EVENTS == [("start",), ("arrived", True, 9.8)]
    assert not log


def test_fly_to_false_when_module_says_failed():
    host, _ = host_with(forager=Courier)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    host.step(batch(1, raw_bee(5, 1, wait=[seq, FAILED, -1])))
    assert EVENTS[-1] == ("arrived", False, 0.0)


class Searcher(Collector):
    def loop(self):
        EVENTS.append(("found", self.search(20.0, 0.0)))
        self.wait(100.0)


def test_search_returns_flower_or_none():
    host, _ = host_with(forager=Searcher)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    found = [7, 3.0, 4.0, 0.3, 2.5]
    host.step(batch(1, raw_bee(5, 1, wait=[seq, DONE, 7], found=found)))
    flower = EVENTS[-1][1]
    assert flower.pos == (3.0, 4.0, 0.3) and flower.nectar == 2.5 and flower._id == 7

    host, _ = host_with(forager=Searcher)
    seq = host.step(batch(0, raw_bee(6, 0))).commands[6]["wait"]
    host.step(batch(1, raw_bee(6, 1, wait=[seq, DONE, -1])))
    assert EVENTS[-1] == ("found", None)


class Counter(Scout):
    passes = 0

    def loop(self):
        Counter.passes += 1
        self.stop()


def test_loop_without_waiting_commands_runs_once_per_tick():
    host, _ = host_with(scout=Counter)
    Counter.passes = 0
    for tick in range(10):
        out = host.step(batch(tick, raw_bee(1, tick, kind="scout")))
        assert out.commands[1] == {"move": ["stop"]}
    assert Counter.passes == 10


def test_lost_command_is_sent_again_with_same_seq():
    host, _ = host_with(forager=Courier)
    first = host.step(batch(0, raw_bee(5, 0))).commands[5]
    again = host.step(batch(1, raw_bee(5, 1))).commands[5]  # модуль не прислал статус
    assert again == first


# ===================================================================== heard


class Listener(Collector):
    def loop(self):
        EVENTS.append(("pass", [(m.word, m._from, m.where) for m in self.heard]))
        self.fly_to(1.0, 0.0)


def test_heard_keeps_messages_while_waiting_last_per_word_and_clears_next_pass():
    host, _ = host_with(forager=Listener)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    # Пока пчела ждёт fly_to: два сообщения от пчелы 9 со словом «a» и одно «b».
    host.step(batch(1, raw_bee(5, 1, wait=[seq, RUNNING, -1],
                               messages=[msg(9, "a", [1.0, 1.0]), msg(8, "c")])))
    host.step(batch(2, raw_bee(5, 2, wait=[seq, RUNNING, -1],
                               messages=[msg(9, "a", [2.0, 2.0]), msg(9, "b")])))
    host.step(batch(3, raw_bee(5, 3, wait=[seq, DONE, -1])))  # конец 1-го прохода
    seq = host.step(batch(4, raw_bee(5, 4))).commands[5]["wait"]  # 2-й проход
    assert EVENTS[1] == ("pass", [("c", 8, None), ("a", 9, (2.0, 2.0, 0.0)), ("b", 9, None)])
    host.step(batch(5, raw_bee(5, 5, wait=[seq, DONE, -1])))
    host.step(batch(6, raw_bee(5, 6)))  # 3-й проход: услышанное до 2-го прохода забыто
    assert EVENTS[2] == ("pass", [])


class Waiter(Collector):
    def loop(self):
        while not self.heard:
            self.wait(1.0)
        EVENTS.append(("heard", self.heard[0].word, self.time))
        self.wait(100.0)


def test_heard_updates_during_the_pass():
    host, _ = host_with(forager=Waiter)
    for tick in range(25):
        messages = [msg(9, "go")] if tick == 15 else []
        host.step(batch(tick, raw_bee(5, tick, messages=messages)))
    assert EVENTS == [("heard", "go", 2.0)]  # ждал по секунде: услышал на ближайшей проверке


# ===================================================================== данные только для чтения


class Writer(Collector):
    def loop(self):
        self.target = 5  # своё поле — можно
        EVENTS.append(("target", self.target))
        self.pos = (1, 2)  # данные пчелы — нельзя


def test_writing_bee_property_is_clear_error_own_field_works():
    host, log = host_with(forager=Writer)
    out = host.step(batch(0, raw_bee(5, 0)))
    assert EVENTS == [("target", 5)]
    assert out.errors == [5] and out.commands[5] == {"move": ["stop"]}
    text = "\n".join(log)
    assert "self.pos — это данные пчелы, их можно только читать" in text
    assert "self.my_pos" in text


# ===================================================================== ошибки и смерть


class Fragile(Collector):
    def loop(self):
        EVENTS.append(("start", self.time))
        self.wait()
        if self.time < 0.15:
            raise ZeroDivisionError("бум")
        self.wait(100.0)


class Calm(Scout):
    def loop(self):
        EVENTS.append(("calm", self.time))
        self.stop()


def test_error_in_loop_logs_restarts_and_others_keep_working():
    host, log = host_with(forager=Fragile, scout=Calm)
    for tick in range(4):
        out = host.step(batch(tick, raw_bee(1, tick, kind="scout"), raw_bee(5, tick)))
        if tick == 1:
            assert out.errors == [5] and out.commands[5] == {"move": ["stop"]}
            assert out.commands[1] == {"move": ["stop"]}
    assert ("start", 0.0) in EVENTS and ("start", 0.2) in EVENTS  # с начала на следующем тике
    assert [e for e in EVENTS if e[0] == "calm"] == [("calm", t / 10) for t in range(4)]
    assert len(log) == 1 and "ZeroDivisionError: бум" in log[0] and "loop()" in log[0]


def test_death_while_waiting_runs_finally_and_new_bee_starts_over():
    host, _ = host_with(forager=Courier)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    host.step(batch(1, raw_bee(5, 1, wait=[seq, RUNNING, -1])))
    host.step(batch(2, raw_bee(7, 2)))  # пчела 5 погибла, родилась 7
    assert EVENTS == [("start",), ("finally",), ("start",)]


def test_auto_return_epoch_restarts_loop_and_commands_return_false():
    host, _ = host_with(forager=Courier)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    # Модуль начал автовозврат: ждущая команда «не вышло» → False.
    host.step(batch(1, raw_bee(5, 1, wait=[seq, FAILED, -1], auto_home=True)))
    assert EVENTS[-1] == ("arrived", False, 0.0)
    # Заправилась (epoch +1): поток закрыт (finally), loop() с начала.
    host.step(batch(20, raw_bee(5, 20, epoch=1, in_hive=True)))
    assert EVENTS[-2:] == [("finally",), ("start",)]


class Busy(Collector):
    def loop(self):
        EVENTS.append(("go", self.go_home(), self.fly_to(1, 1)))
        self.wait(100)


def test_movement_during_auto_return_returns_false_at_once():
    host, _ = host_with(forager=Busy)
    out = host.step(batch(0, raw_bee(5, 0, auto_home=True)))
    assert EVENTS == [("go", False, False)] and "move" not in out.commands.get(5, {})


def test_end_of_match_closes_threads():
    host, _ = host_with(forager=Courier)
    host.step(batch(0, raw_bee(5, 0)))
    host.close()
    assert EVENTS == [("start",), ("finally",)]


# ===================================================================== улей


class Hatcher(Hive):
    def loop(self):
        EVENTS.append((self.hatch(Collector), self.hatch(Worker), self.hatch(Scout),
                       self.hatch(Collector), round(self.honey, 3)))
        EVENTS.append((self.count(Scout), self.count(Collector), self.count(Worker)))
        self.set_home_energy(40)
        self.say("hello", (1, 2))
        self.wait(100)


def test_hive_hatch_answers_at_once_and_counts():
    host, _ = host_with(hive=Hatcher)
    out = host.step(batch(0, view=hive_view(0, honey=10.0, busy=17, max_bees=20)))
    # 10 мёда: Collector (4) да, Worker (2) да, Scout (3) — места нет (17+2 = 19, +1 = 20).
    assert EVENTS[0] == (True, True, True, False, 1.0)
    assert EVENTS[1] == (3, 7, 5)
    assert out.team_command == {"hatch": ["forager", "house", "scout"], "home_energy": 40.0,
                                "say": [["hello", 1.0, 2.0]]}


def test_wrong_kind_and_percent_are_clear_errors():
    class Bad(Hive):
        def loop(self):
            self.hatch("forager")

    host, log = host_with(hive=Bad)
    host.step(batch(0, view=hive_view(0)))
    assert "тип пчелы — Scout, Collector или Worker" in log[0]
