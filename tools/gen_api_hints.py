"""Подсказки по API пчёл для редактора в браузере (M5).

Читает `src/swarmlab/bees/api.py` через `ast` (без импорта) и пишет
`web/js/modules/bees/api_hints.js`: классы, их поля (комментарии `#:`), свойства
и методы (сигнатура и первая строка docstring), с учётом наследования.

    .venv\\Scripts\\python tools\\gen_api_hints.py           # перезаписать файл
    .venv\\Scripts\\python tools\\gen_api_hints.py --check   # только сверить (код 1 — устарел)

Тест `tests/web/test_api_hints.py` проверяет, что файл совпадает с `api.py`.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_PY = ROOT / "src" / "swarmlab" / "bees" / "api.py"
OUT_JS = ROOT / "web" / "js" / "modules" / "bees" / "api_hints.js"

#: Внутренние классы, которые в подсказках не показываются, но чьи члены наследуются.
_HIDDEN_BASES = ("_Agent", "_Flyer")
#: Методы, которые игрок переопределяет, а не вызывает.
_OVERRIDE_ONLY = {"step"}


def _comment_after(lines: list[str], node: ast.AST) -> str:
    """Комментарий `#: …` в конце строки узла или на строке над ним."""
    end = getattr(node, "end_lineno", node.lineno)
    m = re.search(r"#:\s*(.+)$", lines[end - 1])
    if m:
        return m.group(1).strip()
    prev = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
    if prev.startswith("#:"):
        return prev[2:].strip()
    return ""


def _first_line(doc: str | None) -> str:
    return (doc or "").strip().split("\n\n")[0].replace("\n", " ").strip()


def _clean(doc: str) -> str:
    return re.sub(r"\s+", " ", doc).strip()


def _signature(fn: ast.FunctionDef) -> str:
    args = fn.args
    parts: list[str] = []
    plain = args.posonlyargs + args.args
    defaults = [None] * (len(plain) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(plain, defaults, strict=True):
        if a.arg == "self":
            continue
        parts.append(a.arg if d is None else f"{a.arg}={ast.unparse(d)}")
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parts.append(a.arg if d is None else f"{a.arg}={ast.unparse(d)}")
    return f"({', '.join(parts)})"


def _returns(fn: ast.FunctionDef) -> str:
    return ast.unparse(fn.returns) if fn.returns is not None else ""


def build_hints(api_path: Path = API_PY) -> dict[str, Any]:
    """Словарь подсказок: `{"classes": {имя: {...}}, "globals": [...]}`."""
    source = api_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    own: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    globals_: list[dict[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            members: list[dict[str, Any]] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    if name.startswith("_") or (name == "kind" and item.value is not None):
                        continue
                    members.append({"name": name, "kind": "field",
                                    "type": ast.unparse(item.annotation),
                                    "doc": _comment_after(lines, item)})
                elif isinstance(item, ast.FunctionDef):
                    decos = {ast.unparse(d) for d in item.decorator_list}
                    if item.name == "__init__":
                        for st in ast.walk(item):
                            if (isinstance(st, ast.AnnAssign)
                                    and isinstance(st.target, ast.Attribute)
                                    and isinstance(st.target.value, ast.Name)
                                    and st.target.value.id == "self"
                                    and not st.target.attr.startswith("_")):
                                members.append({"name": st.target.attr, "kind": "field",
                                                "type": ast.unparse(st.annotation),
                                                "doc": _comment_after(lines, st)})
                        continue
                    if item.name.startswith("_"):
                        continue
                    doc = _clean(_first_line(ast.get_docstring(item)))
                    if "property" in decos:
                        members.append({"name": item.name, "kind": "property",
                                        "type": _returns(item), "doc": doc})
                    else:
                        members.append({"name": item.name,
                                        "kind": "override" if item.name in _OVERRIDE_ONLY
                                        else "method",
                                        "sig": _signature(item), "type": _returns(item),
                                        "doc": doc})
            own[node.name] = {
                "doc": _clean(_first_line(ast.get_docstring(node))),
                "bases": [ast.unparse(b) for b in node.bases],
                "members": members,
            }
            order.append(node.name)
            if not node.name.startswith("_"):
                globals_.append({"name": node.name, "kind": "class",
                                 "doc": own[node.name]["doc"]})
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_"):
                globals_.append({"name": node.target.id, "kind": "const",
                                 "doc": _comment_after(lines, node)})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    globals_.append({"name": target.id, "kind": "const",
                                     "doc": _comment_after(lines, node)})
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            globals_.append({"name": node.name, "kind": "function",
                             "doc": _clean(_first_line(ast.get_docstring(node)))})

    def resolved(name: str, seen: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        cls = own.get(name)
        if cls is None or name in seen:
            return []
        out: dict[str, dict[str, Any]] = {}
        for base in cls["bases"]:
            for m in resolved(base, (*seen, name)):
                out[m["name"]] = m
        for m in cls["members"]:
            prev = out.get(m["name"])
            if prev is not None and not m.get("doc"):
                m = {**m, "doc": prev.get("doc", "")}  # переопределение без docstring
            out[m["name"]] = m
        return sorted(out.values(), key=lambda m: (m["kind"] == "override", m["name"]))

    classes = {
        name: {"doc": own[name]["doc"],
               "bases": [b for b in own[name]["bases"] if b not in _HIDDEN_BASES],
               "members": resolved(name)}
        for name in order if not name.startswith("_")
    }
    return {"classes": classes, "globals": globals_}


def render_js(hints: dict[str, Any]) -> str:
    body = json.dumps(hints, ensure_ascii=False, indent=1)
    return (
        "// Сгенерировано tools/gen_api_hints.py из src/swarmlab/bees/api.py — не править руками.\n"
        "// Обновить: .venv\\Scripts\\python tools\\gen_api_hints.py\n"
        f"export const API_HINTS = {body};\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="только сверить файл с api.py")
    args = parser.parse_args(argv)
    text = render_js(build_hints())
    current = OUT_JS.read_text(encoding="utf-8") if OUT_JS.exists() else ""
    if args.check:
        if current != text:
            print(f"{OUT_JS} устарел: запустите tools/gen_api_hints.py", file=sys.stderr)
            return 1
        print("api_hints.js совпадает с api.py")
        return 0
    OUT_JS.write_text(text, encoding="utf-8", newline="\n")
    print(f"записан {OUT_JS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
