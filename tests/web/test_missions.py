"""Обучение (M11): подсказки, судья и тексты миссий — под Node (`tests/web/missions_unit.mjs`)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — JS-проверка пропущена")
def test_missions_hints_judge_and_texts():
    out = subprocess.run(["node", str(ROOT / "tests/web/missions_unit.mjs")], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip() == "ok"


def test_core_web_reaches_missions_only_through_registry():
    """Ядро вьюера не импортирует модуль; экран обучения не знает, чему учит (№100)."""
    for path in sorted((ROOT / "web/js/core").rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert "modules/bees" not in text, path.name
    tutorial = (ROOT / "web/js/core/ui/tutorial.js").read_text(encoding="utf-8").lower()
    for word in ("bees", "пчел", "пчёл", "нектар", "улей", "улья", "цвет"):
        assert word not in tutorial, word
    registry = (ROOT / "web/js/modules/registry.js").read_text(encoding="utf-8")
    assert 'missions: () => import("./bees/missions.js")' in registry
