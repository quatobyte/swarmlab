"""Лог программы понятными словами (DECISIONS №106): разбор и слова — под Node, на живых логах."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from swarmlab.core.config import load_match
from swarmlab.core.sim import Simulation

ROOT = Path(__file__).resolve().parents[2]
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — проверка пропущена")


@NODE
def test_log_grouping_and_texts():
    out = subprocess.run(["node", str(ROOT / "tests/web/log_unit.mjs")], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip() == "ok"


def _match_log(tmp_path: Path, code: str, seconds: float = 2.0) -> Path:
    """Короткий headless-матч с одним ульем на этом коде → файл с его логом."""
    script = tmp_path / "player.py"
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    cfg = load_match(ROOT / "configs/matches/m2_economy.yaml", cli_overrides=(
        f"hives=[{{script: '{script.as_posix()}'}}]", f"duration_s={seconds}",
        "weather.mean_duration_s=1e9"))
    with Simulation(cfg) as sim:
        sim.run()
        text = sim.runners.logs[0].text()
    path = tmp_path / "log.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _shown(path: Path) -> list[dict]:
    check = ROOT / "tests/web/log_check.mjs"
    out = subprocess.run(["node", str(check), str(path)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


@NODE
def test_runtime_error_is_one_entry_without_traceback(tmp_path):
    """Ошибка в loop(): одна запись «кто, строка, что», без трассировки и служебных строк ядра."""
    log = _match_log(tmp_path, """
        from swarmlab.bees.api import Collector, Hive, Scout


        class S(Scout):
            def loop(self):
                self.wait(1)


        class C(Collector):
            def loop(self):
                self.collect(None)


        class H(Hive):
            def loop(self):
                self.wait(1)
    """)
    raw = log.read_text(encoding="utf-8")
    assert "Traceback" in raw and "[ядро] запуск раннера" in raw  # в файле лога — всё
    shown = _shown(log)
    errors = [e for e in shown if e["kind"] == "error"]
    assert errors, shown
    first = errors[0]
    assert first["who"].startswith("Сборщик #")
    assert first["file"] == "player.py" and first["line"] == 12
    assert first["message"].startswith("TypeError: collect")
    assert "None" in first["detail"] and "ничто" in first["blockText"]
    text = json.dumps(shown, ensure_ascii=False)
    for junk in ("Traceback", "File \\\"", "~~~", "^^^", "[ядро]", "раннер"):
        assert junk not in text, junk
    # Остальные сборщики — повторами той же ошибки или своими записями, но не трассировкой.
    assert all(e["kind"] in ("error", "repeat", "line", "core") for e in shown)


@NODE
def test_load_error_is_one_entry(tmp_path):
    """Синтаксическая ошибка: «Программа не загрузилась, строка N» и совет; строка ядра скрыта."""
    log = _match_log(tmp_path, """
        from swarmlab.bees.api import Collector

        class C(Collector):
            def loop(self)
                pass
    """, seconds=0.5)
    shown = _shown(log)
    errors = [e for e in shown if e["kind"] == "error"]
    assert len(errors) == 1, shown
    assert errors[0]["who"] == "Программа не загрузилась"
    assert errors[0]["line"] == 5  # первая строка файла — пустая
    assert errors[0]["message"].startswith("SyntaxError")
    assert errors[0]["detail"]
    assert "скрипт не загрузился" not in json.dumps(shown, ensure_ascii=False)
