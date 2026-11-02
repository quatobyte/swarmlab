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
    forager = {m["name"]: m for m in hints["Forager"]["members"]}
    # Команды сборщика — свои и унаследованные от Bee.
    for name in ("collect", "go_home", "fly_to", "hover", "signal", "mark"):
        assert forager[name]["kind"] == "method" and forager[name]["doc"], name
    assert forager["fly_to"]["sig"].startswith("(x, y")
    assert forager["step"]["kind"] == "override"
    me = {m["name"]: m for m in hints["Me"]["members"]}
    assert me["energy_percent"]["kind"] == "property" and me["pos"]["type"] == "Vec"
    assert "энерги" in me["energy"]["doc"]
    sensors = {m["name"]: m for m in hints["Sensors"]["members"]}
    assert sensors["flowers"]["type"] == "list[Flower]"
    assert sensors["nearest_flower"]["type"] == "Flower | None"
    hive = {m["name"]: m for m in hints["Hive"]["members"]}
    assert {"honey", "counts", "memory", "breed"} <= set(hive)
    assert "_Agent" not in hints
    # Удалённые команды и классы (DECISIONS №82) в подсказки не попадают.
    assert not {"unload", "leave_hive", "fly_dir", "thrust"} & set(forager)
    assert not {"Guard", "HouseBee", "Enemy", "Hornet"} & set(hints)


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — JS-проверка пропущена")
def test_editor_hints_infer_types():
    out = subprocess.run(["node", str(ROOT / "tests/web/editor_check.mjs")], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    assert {"energy_percent", "pos", "cargo", "in_hive"} <= set(js["s.me."])
    assert {"collect", "fly_to", "go_home", "signal", "mark"} <= set(js["self."])
    assert "step" not in js["self."]
    assert js["self.co"] == ["collect"]
    assert {"nectar", "pos", "dist", "id"} <= set(js["flower="])
    assert "friend" in js["for"] and "nectar" not in js["for"]  # BeeInfo, не Flower
    assert {"x", "y", "z", "length", "dist"} <= set(js["index"])  # Vec
    assert "nectar" in js["selfattr"]
    assert {"honey", "breed", "counts", "memory"} <= set(js["hive"])
    assert {"forager", "total"} <= set(js["counts"])
    assert "Forager" in js["global"]
    assert "step" in js["super"]
    md = js["markdown"]
    assert "<table>" in md and "<code>x&lt;y</code>" in md and "<b>ж</b>" in md
    assert "<pre><code>print(1)</code></pre>" in md and "<li>два</li>" in md
