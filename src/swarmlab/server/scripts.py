"""Скрипты игроков для редактора в браузере (M5, DECISIONS №47).

Сервер читает и пишет `.py` только в одной папке (`examples/bees/`). Имя файла
проверяется: буквы, цифры и `_`, расширение `.py`, без зарезервированных имён Windows;
после `resolve()` путь обязан лежать в этой папке. Справочные скрипты (`template.py`,
`example_*.py`) только для чтения — их правят через «Сохранить как».

Синтаксис проверяется `ast.parse` — код игрока сервер не исполняет и не импортирует.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

#: Имя скрипта: как имя модуля Python, до 64 символов, `.py`.
_SCRIPT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}\.py$")
#: Имена устройств Windows: с ними файл не создать (или создастся не файл).
_WIN_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
#: Наибольший размер скрипта, байт.
MAX_SCRIPT_BYTES = 256 * 1024


class ScriptError(Exception):
    """Ошибка запроса к скриптам; `status` — HTTP-код ответа."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class SyntaxProblem:
    """Синтаксическая ошибка: строка и колонка с 1, как в редакторе."""

    line: int
    col: int
    end_line: int
    end_col: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "col": self.col, "end_line": self.end_line,
                "end_col": self.end_col, "message": self.message}


def check_syntax(text: str, filename: str = "<скрипт>") -> list[SyntaxProblem]:
    """Синтаксические ошибки текста (пусто — всё в порядке). Код не исполняется."""
    try:
        ast.parse(text, filename=filename)
    except SyntaxError as e:
        line = e.lineno or 1
        col = e.offset or 1
        end_line = getattr(e, "end_lineno", None) or line
        end_col = getattr(e, "end_offset", None) or col + 1
        if (end_line, end_col) <= (line, col):
            end_line, end_col = line, col + 1
        kind = "Ошибка отступа" if isinstance(e, IndentationError) else "Синтаксическая ошибка"
        return [SyntaxProblem(line, col, end_line, end_col, f"{kind}: {e.msg}")]
    except ValueError as e:  # например, нулевой байт в тексте
        return [SyntaxProblem(1, 1, 1, 2, f"Ошибка в тексте: {e}")]
    return []


def is_readonly(name: str) -> bool:
    """Справочные скрипты, которые редактор не перезаписывает."""
    return name == "template.py" or name.startswith("example_")


class ScriptStore:
    """Папка скриптов редактора; `root` — корень проекта (для относительных путей)."""

    def __init__(self, folder: Path, root: Path) -> None:
        self.folder = Path(folder).resolve()
        self.root = Path(root).resolve()

    # ------------------------------------------------------------ пути

    def path(self, name: str) -> Path:
        """Путь к скрипту по имени; недопустимое имя — `ScriptError(400)`."""
        if not _SCRIPT_NAME.match(name) or name[:-3].lower() in _WIN_RESERVED:
            raise ScriptError(
                400,
                f"Недопустимое имя файла {name!r}: только латинские буквы, цифры и _, "
                "в конце .py (например, my_bees.py)",
            )
        path = (self.folder / name).resolve()
        if path.parent != self.folder:  # на случай ссылок и прочих сюрпризов ФС
            raise ScriptError(400, f"Недопустимое имя файла {name!r}")
        return path

    def rel(self, path: Path) -> str:
        """Путь для конфига матча: от корня проекта, если внутри него, иначе абсолютный."""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    # ------------------------------------------------------------ операции

    def info(self, path: Path) -> dict[str, Any]:
        st = path.stat()
        return {"name": path.name, "path": self.rel(path), "readonly": is_readonly(path.name),
                "size": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}

    def list(self) -> list[dict[str, Any]]:
        if not self.folder.is_dir():
            return []
        files = [p for p in self.folder.glob("*.py") if _SCRIPT_NAME.match(p.name)]
        # Свои скрипты — первыми, справочные — после.
        files.sort(key=lambda p: (is_readonly(p.name), p.name.lower()))
        return [self.info(p) for p in files]

    def read(self, name: str) -> dict[str, Any]:
        path = self.path(name)
        if not path.is_file():
            raise ScriptError(404, f"Нет скрипта {name}")
        return {**self.info(path), "text": _read_text(path)}

    def write(self, name: str, text: str) -> dict[str, Any]:
        """Сохранить текст (даже с синтаксической ошибкой — правки не теряются)."""
        path = self.path(name)
        if is_readonly(name):
            raise ScriptError(
                403, f"{name} — справочный скрипт, его не перезаписать. Сохраните под своим "
                "именем («Сохранить как»)")
        data = text.replace("\r\n", "\n").encode("utf-8")
        if len(data) > MAX_SCRIPT_BYTES:
            raise ScriptError(413, f"Скрипт больше {MAX_SCRIPT_BYTES // 1024} КБ")
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # атомарно: вьюер или матч не прочитают полфайла
        problems = check_syntax(text, name)
        return {**self.info(path), "ok": not problems,
                "errors": [p.as_dict() for p in problems]}

    def check_file(self, name: str) -> tuple[Path, list[SyntaxProblem]]:
        """Существующий скрипт и его синтаксические ошибки (перед запуском матча)."""
        path = self.path(name)
        if not path.is_file():
            raise ScriptError(404, f"Нет скрипта {name}")
        return path, check_syntax(_read_text(path), name)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ScriptError(400, f"{path.name}: файл не в кодировке UTF-8 ({e.reason})") from e
