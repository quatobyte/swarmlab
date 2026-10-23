"""Блоки в редакторе (M7b, DECISIONS №50–56, №62).

Генератор Python из блоков — `web/js/modules/bees/blocks_gen.js` — проверяется под Node
(`tests/web/blocks_check.mjs`, без браузера и Blockly); синтаксис — тем же `check_syntax`,
что и у сервера. Без Node.js эти тесты пропускаются.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation
from swarmlab.server.scripts import ScriptError, ScriptStore, check_syntax

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("blocks")
EXAMPLES = ROOT / "examples" / "bees"
CHECK = Path(__file__).with_name("blocks_check.mjs")

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="нет Node.js — JS-проверка блоков пропущена")


def _gen_module():
    spec = importlib.util.spec_from_file_location("gen_blocks_api",
                                                  ROOT / "tools/gen_blocks_api.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _node(*args: str) -> dict:
    out = subprocess.run(["node", str(CHECK), *args], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _gen(path: Path) -> dict:
    return _node("gen", str(path), path.name)


def _run_script(tmp_path: Path, code: str, seconds: float, *overrides: str):
    """Короткий headless-матч m2_economy с одним ульем на этом коде → (stats, лог, экономика)."""
    script = tmp_path / "player.py"
    script.write_text(code, encoding="utf-8")
    cfg = load_match(ROOT / "configs/matches/m2_economy.yaml", cli_overrides=(
        f"hives=[{{script: '{script.as_posix()}'}}]", f"duration_s={seconds}",
        "weather.mean_duration_s=1e9", *overrides))
    with Simulation(cfg) as sim:
        sim.run()
        return sim.runners.stats[0], sim.runners.logs[0].text(), sim.module.economy


# ===================================================================== набор блоков = api.py


def test_blocks_api_js_in_sync_with_api_py():
    gen = _gen_module()
    expected = gen.render_js(gen.build_blocks())
    actual = (ROOT / "web/js/modules/bees/blocks_api.js").read_text(encoding="utf-8")
    assert actual == expected, "устарел: .venv\\Scripts\\python tools\\gen_blocks_api.py"


def _public_api() -> set[str]:
    """Публичные методы, свойства и поля api.py для игрока — независимо от генератора блоков."""
    tree = ast.parse((ROOT / "src/swarmlab/bees/api.py").read_text(encoding="utf-8"))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def own(cls: str, fields: bool) -> set[str]:
        out = set()
        for item in classes[cls].body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__init__" and fields:
                    out |= {st.target.attr for st in ast.walk(item)
                            if isinstance(st, ast.AnnAssign)
                            and isinstance(st.target, ast.Attribute)
                            and not st.target.attr.startswith("_")}
                elif not item.name.startswith("_") and item.name != "step":
                    out.add(item.name)
            elif (fields and isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
                  and not item.target.id.startswith("_")):
                out.add(item.target.id)
        return out

    names = {f"Bee.{m}" for m in own("Bee", False) | own("_Flyer", False)}
    for cls in ("Forager", "Guard", "HouseBee"):
        names |= {f"{cls}.{m}" for m in own(cls, False)}
    for cls in ("Hive", "Sensors", "Me", "Home", "HouseSensors", "HouseMe", "Flower", "Enemy",
                "BeeInfo", "Obstacle", "Message", "Pheromones", "Vec", "Counts", "Larva"):
        names |= {f"{cls}.{m}" for m in own(cls, True)}
    return names | {"wait", "HIVE_ID"}


def test_block_set_matches_public_api():
    """Критерий M7b: набор блоков совпадает с публичными методами (и полями) api.py."""
    blocks = {b["api"] for b in _gen_module().build_blocks()["blocks"]}
    api = _public_api()
    assert blocks == api, f"нет блоков: {sorted(api - blocks)}; лишние: {sorted(blocks - api)}"
    # Команды пчёл и улья — на месте; боты (шершень, паук) — не игрок.
    assert {"Bee.fly_to", "Forager.collect", "Guard.intercept", "HouseBee.nurse", "Hive.breed",
            "Sensors.nearest_flower", "Me.energy_percent", "wait"} <= blocks
    assert not any(b.startswith(("Hornet.", "Spider.")) for b in blocks)


@needs_node
def test_russian_labels_from_dictionary_api_ids_english():
    """Критерий M7b: подписи — из словаря blocks_ru.js (по-русски), имена API — английские."""
    ru = _node("ru")
    assert ru["problems"] == []
    assert set(ru["labels"]) == set(ru["api"])  # у каждого блока API — подпись из словаря
    assert all(re.search("[а-яё]", label, re.I) for label in ru["labels"].values())
    assert 20 <= len(ru["beginner"]) < len(ru["api"])  # стартовый набор и «Продвинутые»
    assert ru["categories"][-1] == "Продвинутые"
    toolbox = set(ru["toolbox"])
    api_types = {f"bees_{a.replace('.', '_')}" for a in ru["api"]}
    assert api_types <= toolbox and set(ru["builtin"]) <= toolbox

    cat = _node("catalog")
    code = cat["code"]
    assert cat["errors"] == [] and check_syntax(code) == []
    # В коде — английские имена API: ни одной русской подписи блока; все атрибуты известны.
    for label in ru["labels"].values():
        assert label.split("{")[0].strip() not in code
    known = {a.split(".")[-1] for a in ru["api"]} | {
        "pop", "append", "insert", "get", "randint", "random", "choice", "randrange", "sqrt", "log",
        "log10", "exp", "sin", "cos", "tan", "asin", "acos", "atan", "radians", "degrees", "pi",
        "e",
        "ceil", "floor", "me", "home", "time"}
    attrs = {n.attr for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Attribute)}
    assert attrs <= known, attrs - known
    assert not re.search(r"\.[а-яё]", code, re.I)


# ===================================================================== генерация и проверки


def _block_files() -> list[Path]:
    good = sorted(EXAMPLES.glob("*.blocks.json"))
    good += [FIXTURES / "basic_wait.blocks.json", FIXTURES / "recursion.blocks.json",
             FIXTURES / "duplicate.blocks.json"]
    return good


@needs_node
@pytest.mark.parametrize("path", _block_files(), ids=lambda p: p.name)
def test_example_block_programs_pass_ast(path):
    """Критерий M7b: сгенерированный Python программ-примеров проходит ast-проверку."""
    res = _gen(path)
    assert res["errors"] == []
    assert check_syntax(res["code"], path.name) == []
    # Каждая строка от блока несёт # block:<id>, и это id существующего блока.
    ids = {m for m in re.findall(r'"id": "([^"]+)"', path.read_text(encoding="utf-8"))}
    marked = re.findall(r"# block:(\S+)$", res["code"], re.M)
    assert marked and set(marked) <= ids
    body = res["code"].split("from swarmlab.bees.api import", 1)[1].splitlines()[1:]
    assert all("# block:" in ln for ln in body if ln.strip())


@needs_node
def test_example_blocks_py_matches_blocks():
    """`example_blocks.py` в репозитории — ровно то, что генерируют его блоки."""
    res = _gen(EXAMPLES / "example_blocks.blocks.json")
    assert (EXAMPLES / "example_blocks.py").read_text(encoding="utf-8") == res["code"], (
        "устарел: node tools/blocks_to_py.mjs examples/bees/example_blocks.blocks.json")


@needs_node
@pytest.mark.parametrize(("fixture", "block"), [
    ("syntax_error.blocks.json", "bad_line"),        # строка Python с незакрытой скобкой
    ("syntax_error_expr.blocks.json", "bad_expr"),   # выражение Python внутри «если»
])
def test_ast_error_points_to_block(fixture, block):
    """Критерий M7b: ошибка ast в сгенерированном коде указывает на блок по `# block:<id>`."""
    res = _gen(FIXTURES / fixture)
    assert res["errors"] == []  # блоки собраны правильно — ошибку ловит только ast
    problems = check_syntax(res["code"])
    assert len(problems) == 1
    assert problems[0].block == block
    assert problems[0].as_dict()["block"] == block


@needs_node
def test_duplicate_program_type_not_generated():
    """Критерий M7b: дубликат типа не попадает в .py, подсвечивается предупреждением."""
    res = _gen(FIXTURES / "duplicate.blocks.json")
    code = res["code"]
    assert code.count("class MyForager(Forager):") == 1
    assert "self.go_home()  # block:first_home" in code  # верхняя программа
    assert "second_hover" not in code and "forager_second" not in code
    assert res["duplicates"] == ["forager_second"]
    assert [w["block"] for w in res["warnings"]] == ["forager_second"]
    assert "class MyScout(Scout):" in code  # другой тип — не дубликат


@needs_node
def test_unconnected_block_ignored_not_error():
    """Критерий M7b: неподключённый блок не попадает в код и не ошибка."""
    res = _gen(FIXTURES / "basic_wait.blocks.json")
    assert res["orphans"] == ["orphan_hover"]
    assert res["errors"] == [] and res["warnings"] == []
    assert "orphan_hover" not in res["code"] and "hover()" not in res["code"]


@needs_node
def test_block_level_errors_before_ast():
    """DECISIONS №56: блок не для этой программы и пустой вход — ошибка на блоке."""
    res = _gen(FIXTURES / "wrong_subject.blocks.json")
    errors = {(e["block"], e["message"].split(":")[0].split("«")[0].strip()) for e in res["errors"]}
    blocks = {b for b, _ in errors}
    assert {"scout_collect", "scout_calls_unload", "hive_go_home", "empty_fly"} <= blocks
    assert any(b == "empty_fly" and m.startswith("Не заполнено") for b, m in errors)


@needs_node
def test_recursion_warns_in_blocks_but_runs_in_python(tmp_path):
    """Критерий M7b: рекурсия в блоках — предупреждение; тот же код на Python работает."""
    res = _gen(FIXTURES / "recursion.blocks.json")
    assert res["errors"] == []
    warned = {w["block"] for w in res["warnings"]}
    assert warned == {"self_call", "ping_calls_pong", "pong_calls_ping"}
    assert "сумма_до(n - 1)" in res["code"]
    stats, log, _ = _run_script(tmp_path, res["code"], 1.0)
    assert stats.load_error is None and stats.agent_errors == 0, log
    assert "сумма=55" in log


def test_recursion_in_plain_python_runs(tmp_path):
    """DECISIONS №55: в Python рекурсию ничто не запрещает."""
    code = textwrap.dedent("""
        def fib(n):
            return n if n < 2 else fib(n - 1) + fib(n - 2)

        def hive_step(hive):
            print(f"fib={fib(15)}")
    """)
    stats, log, _ = _run_script(tmp_path, code, 0.3)
    assert stats.agent_errors == 0 and "fib=610" in log


def test_example_blocks_runs_and_delivers(tmp_path):
    """Программа из блоков: сборщики летят к цветку, ждут, возвращаются — нектар доставлен."""
    code = (EXAMPLES / "example_blocks.py").read_text(encoding="utf-8")
    stats, log, economy = _run_script(tmp_path, code, 60.0)
    assert stats.load_error is None, stats.load_error
    assert stats.agent_errors == 0 and stats.missed == 0, log
    assert economy.delivered[0] > 0
    assert "набрала нектара" in log


# ===================================================================== хранение и переход в Python


def _blocks(mode: str = "blocks") -> dict:
    workspace = {"blocks": {"languageVersion": 0, "blocks": []}}
    return {"format": 1, "mode": mode, "workspace": workspace}


def test_blocks_file_saved_next_to_script(tmp_path):
    """DECISIONS №54: my_bees.blocks.json рядом с my_bees.py."""
    store = ScriptStore(tmp_path, tmp_path)
    res = store.write("my_bees.py", "x = 1  # block:abc\n", _blocks())
    assert res["ok"] and res["mode"] == "blocks"
    saved = json.loads((tmp_path / "my_bees.blocks.json").read_text(encoding="utf-8"))
    assert saved == _blocks()
    data = store.read("my_bees.py")
    assert data["blocks"] == _blocks() and data["text"] == "x = 1  # block:abc\n"
    # В списке — только .py (с режимом), файлы блоков отдельно не показываются.
    assert [(s["name"], s["mode"]) for s in store.list()] == [("my_bees.py", "blocks")]
    # Обычный Python-скрипт без файла блоков.
    store.write("plain.py", "y = 2\n")
    assert store.read("plain.py")["blocks"] is None and store.read("plain.py")["mode"] == "python"
    with pytest.raises(ScriptError) as e:
        store.write("bad.py", "z = 3\n", {"format": 2, "mode": "blocks", "workspace": {}})
    assert e.value.status == 400


def test_switch_to_python_is_one_way(tmp_path):
    """Критерий M7b: после перехода в Python блоки больше не обновляют .py; блоки сохранены."""
    store = ScriptStore(tmp_path, tmp_path)
    store.write("my_bees.py", "x = 1  # block:a\n", _blocks())
    store.write("my_bees.py", "x = 1  # block:a\n", _blocks("python"))  # «Перейти на Python»
    store.write("my_bees.py", "x = 2  # правлю руками\n")  # дальше — обычный Python
    with pytest.raises(ScriptError) as e:
        store.write("my_bees.py", "x = 1  # block:a\n", _blocks())  # блоки пытаются записать
    assert e.value.status == 409
    assert (tmp_path / "my_bees.py").read_text(encoding="utf-8") == "x = 2  # правлю руками\n"
    saved = json.loads((tmp_path / "my_bees.blocks.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "python"
    assert store.read("my_bees.py")["mode"] == "python"


def test_example_blocks_readonly(tmp_path):
    store = ScriptStore(EXAMPLES, ROOT)
    info = store.read("example_blocks.py")
    assert info["readonly"] and info["mode"] == "blocks" and info["blocks"]["workspace"]
    with pytest.raises(ScriptError) as e:
        store.write("example_blocks.py", "x = 1\n", _blocks())
    assert e.value.status == 403
