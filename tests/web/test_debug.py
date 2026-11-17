"""Инспектор пчелы (M12): слова карточки и переход от строки к блоку — под Node."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — JS-проверка пропущена")
def test_inspector_texts_and_line_to_block():
    out = subprocess.run(["node", str(ROOT / "tests/web/debug_unit.mjs")], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip() == "ok"


def test_core_passes_debug_without_reading_it():
    """Ядро не разбирает сведения отладчика и не называет модуль (DECISIONS №105)."""
    for name in ("protocol.py", "runner_host.py", "sim.py", "program.py"):
        text = (ROOT / "src/swarmlab/core" / name).read_text(encoding="utf-8")
        assert "swarmlab.bees" not in text, name
    for name in ("app.js", "live.js", "ui/editor.js"):
        text = (ROOT / "web/js/core" / name).read_text(encoding="utf-8")
        assert "debug_ru" not in text and "modules/bees" not in text, name
