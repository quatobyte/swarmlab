"""Подсказки редактора M5: файл api_hints.js совпадает с api.py, вывод типов в подсказках."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _gen():
    spec = importlib.util.spec_from_file_location("gen_api_hints", ROOT / "tools/gen_api_hints.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_api_hints_js_in_sync_with_api_py():
    gen = _gen()
    expected = gen.render_js(gen.build_hints())
    actual = (ROOT / "web/js/modules/bees/api_hints.js").read_text(encoding="utf-8")
    assert actual == expected, "устарел: .venv\\Scripts\\python tools\\gen_api_hints.py"


def test_api_hints_cover_player_api():
    hints = _gen().build_hints()["classes"]
    coll = {m["name"]: m for m in hints["Collector"]["members"]}
    # Команды сборщика — свои и унаследованные от общей части пчёл.
    for name in ("collect", "go_home", "fly_to", "search", "explore", "stop", "say", "mark"):
        assert coll[name]["kind"] == "method" and coll[name]["doc"], name
    assert coll["fly_to"]["sig"].startswith("(target, y=None")
    assert coll["loop"]["kind"] == "override"
    assert coll["energy"]["kind"] == "property" and coll["pos"]["type"] == "Point"
    assert "энерги" in coll["energy"]["doc"]
    assert coll["flowers"]["type"] == "list[Flower]"
    assert coll["nearest_flower"]["type"] == "Flower | None"
    hive = {m["name"]: m for m in hints["Hive"]["members"]}
    assert {"honey", "count", "hatch", "set_home_energy", "say", "heard"} <= set(hive)
    assert "_Agent" not in hints and "_Flyer" not in hints and "_View" not in hints
    assert not {"step", "hover", "signal", "cargo", "in_hive"} & set(coll)
    assert not {"Sensors", "Me", "Forager", "Vec", "Spider", "Counts", "Larva"} & set(hints)


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — JS-проверка пропущена")
def test_editor_hints_infer_types():
    out = subprocess.run(["node", str(ROOT / "tests/web/editor_check.mjs")], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    assert {"collect", "fly_to", "go_home", "say", "mark", "energy", "pos", "heard"} <= set(
        js["self."])
    assert "loop" not in js["self."]
    assert js["self.co"] == ["collect"]
    assert {"nectar", "pos", "distance", "spider"} <= set(js["flower="])
    assert "friend" in js["for"] and "nectar" not in js["for"]  # OtherBee, не Flower
    assert {"word", "where", "from_where"} <= set(js["heard"])
    assert {"x", "y", "distance"} <= set(js["index"])  # Point
    assert "nectar" in js["selfattr"]
    assert {"honey", "hatch", "count", "set_home_energy"} <= set(js["hive"])
    assert "Collector" in js["global"]
    assert "loop" in js["super"]
    md = js["markdown"]
    assert "<table>" in md and "<code>x&lt;y</code>" in md and "<b>ж</b>" in md
    assert "<pre><code>print(1)</code></pre>" in md and "<li>два</li>" in md
