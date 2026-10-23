"""Структура блоков пчёл для редактора в браузере (M7b, DECISIONS №52).

Читает `src/swarmlab/bees/api.py` через `ast` (без импорта) — тем же способом, что
`tools/gen_api_hints.py`, — и пишет `web/js/modules/bees/blocks_api.js`: по блоку на
каждую команду пчелы и улья, на каждое поле, свойство и метод сенсоров и объектов,
на `wait()` и `HIVE_ID`. Русские подписи сюда не попадают — они вручную в
`web/js/modules/bees/blocks_ru.js`.

    .venv\\Scripts\\python tools\\gen_blocks_api.py           # перезаписать файл
    .venv\\Scripts\\python tools\\gen_blocks_api.py --check   # только сверить (код 1 — устарел)

Тест `tests/web/test_blocks.py` проверяет, что файл совпадает с `api.py`.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_PY = ROOT / "src" / "swarmlab" / "bees" / "api.py"
OUT_JS = ROOT / "web" / "js" / "modules" / "bees" / "blocks_api.js"


def _hints_module() -> Any:
    """`tools/gen_api_hints.py` — общие помощники разбора (комментарии `#:`, docstring)."""
    spec = importlib.util.spec_from_file_location(
        "gen_api_hints", Path(__file__).with_name("gen_api_hints.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_H = _hints_module()

FLYERS = ["scout", "forager", "guard"]
EVERYONE = ["scout", "forager", "guard", "house", "hive"]

#: Классы, у которых есть блоки: класс → (к чему обращается блок, какие программы его видят,
#: внутренние базы, чьи члены считаются своими). Шершень и паук — боты, не игрок.
CLASSES: dict[str, tuple[str, list[str], tuple[str, ...]]] = {
    "Bee": ("self", FLYERS, ("_Flyer", "_Agent")),
    "Forager": ("self", ["forager"], ()),
    "Guard": ("self", ["guard"], ()),
    "HouseBee": ("self", ["house"], ("_Agent",)),
    "Hive": ("hive", ["hive"], ()),
    "Sensors": ("s", FLYERS, ()),
    "Me": ("s.me", FLYERS, ()),
    "Home": ("s.home", FLYERS, ()),
    "HouseSensors": ("s", ["house"], ()),
    "HouseMe": ("s.me", ["house"], ()),
    "Flower": ("obj", EVERYONE, ()),
    "Enemy": ("obj", EVERYONE, ()),
    "BeeInfo": ("obj", EVERYONE, ()),
    "Obstacle": ("obj", EVERYONE, ()),
    "Message": ("obj", EVERYONE, ()),
    "Pheromones": ("obj", EVERYONE, ()),
    "Vec": ("obj", EVERYONE, ()),
    "Counts": ("obj", EVERYONE, ()),
    "Larva": ("obj", EVERYONE, ()),
}
#: Методы, которые игрок переопределяет, а не вызывает.
_OVERRIDE_ONLY = {"step"}
#: Глобальные функции и константы с блоками.
GLOBALS = ("wait", "HIVE_ID")


def _literals(tree: ast.Module) -> dict[str, list[str]]:
    """`Kind = Literal["scout", …]` → {"Kind": ["scout", …]}."""
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Subscript)
                and ast.unparse(node.value.value) == "Literal"):
            sl = node.value.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            out[node.targets[0].id] = [e.value for e in elts if isinstance(e, ast.Constant)]
    return out


def _check(ann: str | None, classes: set[str]) -> list[str] | None:
    """Тип для проверки соединений Blockly: `None` — подходит что угодно."""
    if not ann:
        return None
    out: list[str] = []
    for part in (p.strip() for p in ann.split("|")):
        if part == "None":
            continue
        head = part.split("[", 1)[0]
        if head in ("float", "int"):
            t = "Number"
        elif head == "bool":
            t = "Boolean"
        elif head in ("str", "Kind", "Weather", "Task"):
            t = "String"
        elif head in ("list", "tuple"):
            t = "Array"
        elif head in classes:
            t = head
        else:
            return None  # dict, Any и прочее — без проверки
        if t not in out:
            out.append(t)
    return out or None


def _params(fn: ast.FunctionDef, literals: dict[str, list[str]],
            classes: set[str]) -> list[dict[str, Any]]:
    args = fn.args
    plain = args.posonlyargs + args.args
    defaults: list[ast.expr | None] = (
        [None] * (len(plain) - len(args.defaults)) + list(args.defaults))
    out: list[dict[str, Any]] = []

    def one(a: ast.arg, d: ast.expr | None, vararg: bool = False) -> dict[str, Any]:
        ann = ast.unparse(a.annotation) if a.annotation is not None else ""
        return {"name": a.arg, "type": ann, "required": d is None and not vararg,
                "default": None if d is None else ast.unparse(d), "vararg": vararg,
                "options": literals.get(ann),
                "check": ["Array"] if vararg else _check(ann, classes)}

    for a, d in zip(plain, defaults, strict=True):
        if a.arg != "self":
            out.append(one(a, d))
    if args.vararg:
        out.append(one(args.vararg, None, vararg=True))
    for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        out.append(one(a, d))
    return out


def build_blocks(api_path: Path = API_PY) -> dict[str, Any]:
    """Описание блоков: `{"literals": {...}, "classes": {...}, "blocks": [...]}`."""
    source = api_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    literals = _literals(tree)
    nodes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    api_classes = {name for name in nodes if not name.startswith("_")}

    def members(cls: ast.ClassDef) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        for item in cls.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                name = item.target.id
                if name.startswith("_") or (name == "kind" and item.value is not None):
                    continue
                out.append((name, {"member": "field", "returns": ast.unparse(item.annotation),
                                   "doc": _H._comment_after(lines, item), "params": []}))
            elif isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    for st in ast.walk(item):
                        if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Attribute)
                                and isinstance(st.target.value, ast.Name)
                                and st.target.value.id == "self"
                                and not st.target.attr.startswith("_")):
                            out.append((st.target.attr, {
                                "member": "field", "returns": ast.unparse(st.annotation),
                                "doc": _H._comment_after(lines, st), "params": []}))
                    continue
                if item.name.startswith("_") or item.name in _OVERRIDE_ONLY:
                    continue
                decos = {ast.unparse(d) for d in item.decorator_list}
                kind = "property" if "property" in decos else "method"
                out.append((item.name, {
                    "member": kind,
                    "returns": ast.unparse(item.returns) if item.returns is not None else "None",
                    "doc": _H._clean(_H._first_line(ast.get_docstring(item))),
                    "params": [] if kind == "property" else _params(item, literals, api_classes),
                }))
        return out

    blocks: list[dict[str, Any]] = []
    classes: dict[str, Any] = {}
    for cls_name, (target, subjects, hidden) in CLASSES.items():
        classes[cls_name] = {"target": target, "subjects": subjects}
        own: dict[str, dict[str, Any]] = {}
        for base in reversed(hidden):  # члены внутренних баз — как свои (fly_to у Bee)
            own.update(dict(members(nodes[base])))
        own.update(dict(members(nodes[cls_name])))
        if target == "self":  # у пчёл нет полей для игрока (`kind` — служебное; есть `s.me.kind`)
            own = {k: v for k, v in own.items() if v["member"] != "field"}
        for name in sorted(own):
            m = own[name]
            returns = m["returns"]
            blocks.append({
                "type": f"bees_{cls_name}_{name}",
                "api": f"{cls_name}.{name}",
                "cls": cls_name,
                "name": name,
                "member": m["member"],
                "target": target,
                "subjects": subjects,
                "params": m["params"],
                "returns": returns,
                "output": (None if returns in ("None", "Order")
                           else _check(returns, api_classes) or []),
                "waitable": returns == "Order",
                "doc": m["doc"],
            })

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in GLOBALS:
            returns = ast.unparse(node.returns) if node.returns is not None else "None"
            blocks.append({
                "type": f"bees_{node.name}", "api": node.name, "cls": "", "name": node.name,
                "member": "function", "target": "", "subjects": EVERYONE,
                "params": _params(node, literals, api_classes), "returns": returns,
                "output": None, "waitable": False, "yields": returns == "Wait",
                "doc": _H._clean(_H._first_line(ast.get_docstring(node))),
            })
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id in GLOBALS):
            name = node.targets[0].id
            blocks.append({
                "type": f"bees_{name}", "api": name, "cls": "", "name": name, "member": "const",
                "target": "", "subjects": EVERYONE, "params": [], "returns": "int",
                "output": ["Number"], "waitable": False,
                "doc": _H._comment_after(lines, node),
            })
    return {"literals": literals, "classes": classes, "blocks": blocks}


def render_js(data: dict[str, Any]) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=1)
    return (
        "// Сгенерировано tools/gen_blocks_api.py из src/swarmlab/bees/api.py"
        " — не править руками.\n"
        "// Обновить: .venv\\Scripts\\python tools\\gen_blocks_api.py\n"
        f"export const BLOCKS_API = {body};\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="только сверить файл с api.py")
    args = parser.parse_args(argv)
    text = render_js(build_blocks())
    current = OUT_JS.read_text(encoding="utf-8") if OUT_JS.exists() else ""
    if args.check:
        if current != text:
            print(f"{OUT_JS} устарел: запустите tools/gen_blocks_api.py", file=sys.stderr)
            return 1
        print("blocks_api.js совпадает с api.py")
        return 0
    OUT_JS.write_text(text, encoding="utf-8", newline="\n")
    print(f"записан {OUT_JS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
