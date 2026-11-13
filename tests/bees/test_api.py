"""Имена API игрока (DECISIONS №85): ровно согласованный список, удалённых имён нигде нет."""

import json
import re
from pathlib import Path

from swarmlab.bees import api

ROOT = Path(__file__).resolve().parents[2]

#: Публичные имена модуля `api.py` (№85; `Flower`, `OtherBee`, `Message` — уточнение M8).
MODULE = {"Scout", "Collector", "Worker", "Hive", "Point", "Flower", "OtherBee", "Message"}
#: Пчела: данные (только чтение) и команды; `collect` — только у сборщика.
BEE_DATA = {"pos", "energy", "max_energy", "nectar", "is_full", "at_home", "home", "flowers",
            "nearest_flower", "bees", "time", "heard", "smell", "smell_way"}
BEE_COMMANDS = {"fly_to", "search", "explore", "go_home", "refuel", "wait", "stop", "say",
                "mark"}
HIVE = {"honey", "count", "hatch", "say", "heard", "wait", "set_home_energy",
        "set_refuel_energy", "time"}
CLASSES = {
    "Scout": BEE_DATA | BEE_COMMANDS | {"loop"},
    "Collector": BEE_DATA | BEE_COMMANDS | {"loop", "collect"},
    "Hive": HIVE | {"loop"},
    "Worker": set(),
    "Point": {"x", "y", "z", "distance"},
    "Flower": {"pos", "nectar", "spider", "distance"},
    "OtherBee": {"pos", "friend", "distance"},
    "Message": {"word", "where", "from_where"},
}
#: Убрано из API игрока (№82, №85): ни в API, ни в подсказках, ни в блоках.
REMOVED = {
    "Sensors", "Me", "Obstacle", "Larva", "Counts", "Spider", "SpiderSensors", "HIVE_ID",
    "hive_step", "hover", "signal", "breed", "pheromones", "energy_percent", "cargo", "in_hive",
    "ground_z", "airspeed", "weather", "tick", "queue", "costs", "max_bees", "memory", "Forager",
    "Vec", "step", "BeeInfo", "messages", "counts", "z_agl", "avoid",
}


def public(cls: type) -> set[str]:
    return {n for c in cls.__mro__ if c.__module__ == api.__name__
            for n in vars(c) if not n.startswith("_")}


def test_public_names_match_decision_85():
    defined = {n for n, v in vars(api).items() if not n.startswith("_")
               and getattr(v, "__module__", None) == api.__name__}
    assert set(api.__all__) == MODULE == defined
    for name, members in CLASSES.items():
        assert public(getattr(api, name)) == members, name
    assert api._COLORS == ("red", "blue", "green", "yellow")


def _js_object(path: Path, name: str) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(re.search(rf"export const {name} = (\{{.*\}});", text, re.S).group(1))


def test_removed_names_absent_in_api_hints_and_blocks():
    assert not REMOVED & set(dir(api))
    for cls in CLASSES:
        assert not REMOVED & public(getattr(api, cls)), cls
    hints = _js_object(ROOT / "web/js/modules/bees/api_hints.js", "API_HINTS")
    names = set(hints["classes"]) | {g["name"] for g in hints["globals"]}
    names |= {m["name"] for c in hints["classes"].values() for m in c["members"]}
    assert not REMOVED & names
    blocks = _js_object(ROOT / "web/js/modules/bees/blocks_api.js", "BLOCKS_API")
    used = {part for b in blocks["blocks"] for part in b["api"].split(".")}
    assert not REMOVED & used
