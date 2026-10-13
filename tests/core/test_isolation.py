"""Инварианты зависимостей: ядро не знает о модулях; MuJoCo — только в bees/physics."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "swarmlab"
FORBIDDEN_IN_CORE = ("swarmlab.bees", "swarmlab.server", "swarmlab.runner", "mujoco")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _hits(names: set[str], prefixes: tuple[str, ...]) -> set[str]:
    return {n for n in names if any(n == p or n.startswith(p + ".") for p in prefixes)}


def test_core_has_no_forbidden_imports_static():
    bad = {
        str(f.relative_to(SRC)): _hits(_imports(f), FORBIDDEN_IN_CORE)
        for f in (SRC / "core").rglob("*.py")
    }
    assert not {k: v for k, v in bad.items() if v}


def test_mujoco_only_inside_bees_physics():
    physics = SRC / "bees" / "physics"
    offenders = [
        str(f.relative_to(SRC))
        for f in SRC.rglob("*.py")
        if physics not in f.parents and _hits(_imports(f), ("mujoco",))
    ]
    assert offenders == []


def test_core_import_does_not_load_modules_at_runtime():
    code = (
        "import importlib, pkgutil, sys, swarmlab.core as c\n"
        "for m in pkgutil.iter_modules(c.__path__):\n"
        "    importlib.import_module('swarmlab.core.' + m.name)\n"
        f"bad = [m for m in sys.modules if m.startswith({FORBIDDEN_IN_CORE!r})]\n"
        "print(bad); sys.exit(1 if bad else 0)\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
