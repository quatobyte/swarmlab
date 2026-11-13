"""Проект `.swarm` и предупреждение о чужом коде (M7c, DECISIONS №63, №65).

Экспорт и открытие проекта — `web/js/core/project.js`, доверие — `web/js/core/trust.js`;
проверяются под Node (без Node.js тесты пропускаются). Тот же файл разбирает и сервер
(`server/projects.py`) — проверяем, что они согласны.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from swarmlab.server.projects import code_sha256, parse_project

ROOT = Path(__file__).resolve().parents[2]
CHECK = Path(__file__).with_name("project_check.mjs")
EXAMPLES = ROOT / "examples" / "bees"

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="нет Node.js — JS-проверка проекта пропущена")


def _node(*args: str) -> str:
    res = subprocess.run(["node", str(CHECK), *args], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return res.stdout


@needs_node
@pytest.mark.parametrize("mode", ["python", "blocks"])
def test_export_then_open_gives_same_code_and_blocks(tmp_path, mode):
    """Критерий M7c: экспорт → открытие проекта даёт тот же код и те же блоки (оба режима)."""
    if mode == "blocks":
        py, blocks_file = EXAMPLES / "example_blocks.py", EXAMPLES / "example_blocks.blocks.json"
        args = ["export", "example_blocks", "blocks", str(py), str(blocks_file)]
    else:
        py, blocks_file = EXAMPLES / "example_smart.py", None
        args = ["export", "example_smart.py", "python", str(py)]
    text = _node(*args)
    swarm = tmp_path / "p.swarm"
    swarm.write_text(text, encoding="utf-8")
    opened = json.loads(_node("open", str(swarm)))
    code = py.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert opened["code"] == code
    assert opened["mode"] == mode and opened["format"] == 1 and opened["created"]
    assert opened["name"] == py.stem
    if blocks_file:
        assert opened["blocks"] == json.loads(blocks_file.read_text("utf-8"))["workspace"]
    else:
        assert opened["blocks"] is None
    # Сервер разбирает тот же файл так же.
    server = parse_project(swarm.read_bytes())
    assert (server["code"], server["blocks"], server["mode"]) == (
        opened["code"], opened["blocks"], opened["mode"])


@needs_node
def test_broken_project_file_gives_clear_error_in_browser():
    """Критерий M7c: битый файл — понятная ошибка (в браузере; сервер — tests/server)."""
    res = json.loads(_node("broken"))
    words = {"json": "битый JSON", "array": "объект", "format": "формат", "nocode": "кода",
             "name": "имя", "mode": "режим", "noblocks": "блоков"}
    for case, word in words.items():
        assert res[case] and res[case].startswith("ProjectError") and word in res[case], (case, res)


@needs_node
def test_foreign_code_warning_once_per_content_and_again_when_changed():
    """Критерий M7c: предупреждение один раз на содержимое; изменённый файл спрашивает снова."""
    res = json.loads(_node("trust"))
    steps = {label: (ok, asked) for label, ok, asked in res["steps"]}
    assert steps["first-no"] == (False, 1)  # отказ — код не запомнен
    assert steps["first-yes"] == (True, 2)
    assert steps["same-again"] == (True, 2)  # не спросили
    assert steps["changed"] == (True, 3)  # изменённый — спросили
    assert steps["both-known"] == (True, 3)
    assert steps["one-new"] == (True, 4)
    assert res["stored"] == 3


def test_server_sha256_matches_browser_algorithm():
    # Браузер хеширует UTF-8 текста кода (crypto.subtle) — так же, как сервер.
    assert code_sha256("print('пчёлы')\n") == (
        hashlib.sha256("print('пчёлы')\n".encode()).hexdigest())
