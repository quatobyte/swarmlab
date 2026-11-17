"""M12: сведения для отладчика от раннера (DECISIONS №105).

Хост без процесса: что попадает в снимок программы и когда он отправляется. Настоящий
матч с раннером — в конце: сведения доходят до ядра, а хеш реплея от них не зависит.
"""

import textwrap
from pathlib import Path

from swarmlab.bees import debug
from swarmlab.bees.api import Collector, Flower, Hive, Message, OtherBee, Point
from swarmlab.core.config import load_match
from swarmlab.core.program import DONE, RUNNING
from swarmlab.core.protocol import CommandBatch
from swarmlab.core.replay import ReplayWriter, make_header
from swarmlab.core.sim import Simulation

from .helpers import CONFIGS, FLAT
from .test_program import batch, hive_view, host_with, msg, raw_bee


def debug_host(**classes: type):
    host, log = host_with(**classes)
    host.debug = True
    host._script_file = __file__  # «файл игрока» — этот тест: в нём классы программ
    return host, log


def line_of(marker: str) -> int:
    """Номер строки этого файла с пометкой `# <marker>`."""
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    return next(i for i, text in enumerate(lines, 1) if text.rstrip().endswith(f"# {marker}"))


class Gatherer(Collector):
    def loop(self):
        self.my_trips = getattr(self, "my_trips", 0) + 1
        цветок = self.explore()  # wait-explore
        if цветок is not None:
            self.collect(цветок)  # wait-collect
        self.go_home()


def test_snapshot_has_line_command_variables_and_own_fields():
    host, _ = debug_host(forager=Gatherer)
    out = host.step(batch(0, raw_bee(5, 0)))
    snap = out.debug["5"]
    assert snap["line"] == line_of("wait-explore") and snap["fn"] is None
    assert snap["wait"] == ["explore", None]
    assert snap["pass"] == 1 and snap["vars"] == [] and snap["error"] is None
    assert snap["self"] == [["my_trips", 1]]
    # Цветок найден: программа ждёт следующую команду, в переменной — цветок.
    seq = out.commands[5]["wait"]
    out = host.step(batch(1, raw_bee(5, 1, wait=[seq, DONE, 7], found=[7, 3.0, 4.0, 0.3, 2.5])))
    snap = out.debug["5"]
    assert snap["line"] == line_of("wait-collect")
    assert snap["wait"][0] == "collect"
    assert snap["vars"] == [["цветок", {"k": "flower", "x": 3.0, "y": 4.0, "nectar": 2.5,
                                       "spider": None}]]


def test_snapshot_is_sent_only_when_it_changes_and_never_without_debug():
    host, _ = debug_host(forager=Gatherer)
    seq = host.step(batch(0, raw_bee(5, 0))).commands[5]["wait"]
    # Пчела всё ещё ищет: снимок тот же — отладчику нечего слать.
    assert host.step(batch(1, raw_bee(5, 1, wait=[seq, RUNNING, -1]))).debug is None
    # Пчела погибла: отладчик узнаёт, что её больше нет.
    assert host.step(batch(2)).debug == {"5": None}

    plain, _ = host_with(forager=Gatherer)
    out = plain.step(batch(0, raw_bee(5, 0)))
    assert out.debug is None and "debug" not in out.to_message()


def helper(bee, where):
    рядом = len(bee.flowers)
    bee.fly_to(where)  # wait-helper
    return рядом


class Listener(Collector):
    def loop(self):
        for сообщение in self.heard:
            helper(self, сообщение.where)
        self.wait(2.5)  # wait-seconds


def test_procedure_frame_heard_and_plain_wait():
    host, _ = debug_host(forager=Listener)
    out = host.step(batch(0, raw_bee(5, 0, messages=[msg(1, "flowers", [10.0, 20.0])])))
    snap = out.debug["5"]
    assert snap["line"] == line_of("wait-helper") and snap["fn"] == "helper"
    assert snap["heard"] == [{"k": "message", "word": "flowers", "where": [10.0, 20.0]}]
    # Переменные и программы (loop), и процедуры, в которой она сейчас; сама пчела (`self`,
    # `bee`) — не данные.
    assert [name for name, _ in snap["vars"]] == ["сообщение", "where", "рядом"]
    assert snap["vars"][1][1] == {"k": "point", "x": 10.0, "y": 20.0} and snap["vars"][2][1] == 0

    host, _ = debug_host(forager=Listener)
    snap = host.step(batch(0, raw_bee(5, 0))).debug["5"]
    assert snap["line"] == line_of("wait-seconds") and snap["wait"] == ["wait", 2.5]


class Broken(Collector):
    def loop(self):
        цель = None
        self.collect(цель)  # error-line


class Keeper(Hive):
    def loop(self):
        мёд = self.honey
        self.wait(мёд)  # wait-hive


def test_error_is_kept_with_line_and_hive_has_snapshot_too():
    host, _ = debug_host(forager=Broken, hive=Keeper)
    out = host.step(batch(0, raw_bee(5, 0), view=hive_view(0)))
    bee = out.debug["5"]
    assert bee["line"] is None and bee["wait"] is None
    assert bee["error"]["line"] == line_of("error-line")
    assert bee["error"]["text"].startswith("TypeError: collect: куда?")
    hive = out.debug["hive"]
    assert hive["line"] == line_of("wait-hive") and hive["vars"] == [["мёд", 10.0]]


class Loud:
    def __repr__(self):  # pragma: no cover — отладчик не должен это вызывать
        raise AssertionError("отладчик вызвал код игрока")


def test_encode_is_bounded_and_never_calls_player_code():
    assert debug.encode(None) is None and debug.encode(True) is True
    assert debug.encode(1.23456) == 1.235 and debug.encode(float("nan")) == "nan"
    assert debug.encode("я" * 500) == "я" * debug.MAX_TEXT
    assert debug.encode(Point(1.0, 2.0)) == {"k": "point", "x": 1.0, "y": 2.0}
    assert debug.encode(OtherBee(Point(1, 2), True, 3.0)) == {"k": "bee", "x": 1, "y": 2,
                                                              "friend": True}
    assert debug.encode(Message("go", None, Point(0, 0), 1))["where"] is None
    big = debug.encode(list(range(100)))
    assert big["n"] == 100 and big["items"] == list(range(debug.MAX_ITEMS))
    assert debug.encode({"a": [Flower(Point(0, 0), 1.0, True, 2.0)]}) == {
        "k": "dict", "n": 1, "items": [["a", {"k": "list", "n": 1, "items": [
            {"k": "flower", "x": 0, "y": 0, "nectar": 1.0, "spider": True}]}]]}
    deep = debug.encode([[[[1]]]])
    assert deep["items"][0]["items"][0] == {"k": "list", "n": 1, "items": []}
    assert debug.encode(Loud()) == {"k": "obj", "text": "Loud"}


def test_debug_field_survives_the_protocol_roundtrip():
    out = CommandBatch(tick=3, debug={"5": {"line": 7}})
    assert CommandBatch.from_message(out.to_message()).debug == {"5": {"line": 7}}
    assert CommandBatch.from_message(CommandBatch(tick=3).to_message()).debug is None


# ===================================================================== настоящий матч

PLAYER = """
    from swarmlab.bees.api import Collector, Hive, Scout

    class MyScout(Scout):
        def loop(self):
            self.wait(1000)

    class MyCollector(Collector):
        def loop(self):
            flower = self.explore()
            if flower is not None:
                self.collect(flower)
            self.go_home()

    class MyHive(Hive):
        def loop(self):
            self.wait(5)
"""


def _match(tmp_path: Path, name: str, on_debug=None) -> str:
    script = tmp_path / "player.py"
    script.write_text(textwrap.dedent(PLAYER), encoding="utf-8")
    cfg = load_match(
        CONFIGS / "matches" / "m2_economy.yaml",
        cli_overrides=(f"hives=[{{script: '{script.as_posix()}'}}]", "duration_s=20", "seed=5",
                       "weather.enabled=false", *FLAT),
    )
    with Simulation(cfg, on_debug=on_debug) as sim:
        writer = ReplayWriter(tmp_path / name, make_header(cfg, sim.teams, sim.module.scene()))
        sim.on_frame = writer.write
        sim.run()
        return writer.close(sim.module.score())


def test_real_match_sends_snapshots_and_replay_hash_does_not_depend_on_debug(tmp_path):
    got: list[tuple] = []
    with_debug = _match(tmp_path, "a.swr", lambda *row: got.append(row))
    without = _match(tmp_path, "b.swr")
    assert with_debug == without
    assert (tmp_path / "a.swr").read_bytes() == (tmp_path / "b.swr").read_bytes()
    assert got and got[0][0] == 0
    merged: dict[str, dict] = {}
    for _, _, data in got:
        merged.update(data)
    # Номера строк — по файлу игрока (первая строка PLAYER пустая).
    assert merged["hive"]["line"] == 17 and merged["hive"]["wait"] == ["wait", 5]
    collectors = [s for s in merged.values() if s and s["wait"] and s["wait"][0] in
                  ("explore", "collect", "go_home")]
    assert collectors and all(s["line"] in (10, 12, 13) for s in collectors)
    # Сведения приходят не каждый тик: только когда снимок изменился.
    assert len(got) < 200
