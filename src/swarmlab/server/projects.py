"""Проекты `.swarm`: загрузка в меню, папка `projects/`, копия в редактор (DECISIONS №63–64).

Проект — JSON `{"format": 1, "name", "created", "mode": "blocks" | "python", "code",
"blocks": {рабочая область Blockly} | null}`: только рой (один скрипт улья), без настроек
матча и соперников. Сервер проверяет форму файла, а не код: код игрока он не исполняет,
синтаксис — `ast.parse` перед матчем, как у скриптов редактора.

Загруженный проект лежит в `projects/` (её не видно в списке скриптов редактора):
`<имя>.py` + `<имя>.blocks.json` (если блоки) + `<имя>.swarm` (оригинал, пишется последним —
по нему проект считается загруженным). Имя проверяется как у скриптов (№47). Тот же
проект с тем же содержимым — тот же проект; другое содержимое под тем же именем —
новый проект с суффиксом даты `<имя>-YYYYMMDD-HHMM`, старый не перезаписывается.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from swarmlab.server.scripts import (
    _SCRIPT_NAME,
    _WIN_RESERVED,
    BLOCKS_SUFFIX,
    MAX_BLOCKS_BYTES,
    MAX_SCRIPT_BYTES,
    ScriptError,
    ScriptStore,
    SyntaxProblem,
    _atomic_write,
    check_syntax,
    is_readonly,
)

#: Версия формата `.swarm`.
PROJECT_FORMAT = 1
PROJECT_SUFFIX = ".swarm"
PROJECT_MODES = ("blocks", "python")
#: Наибольший размер файла проекта, байт (код + блоки + запас на JSON).
MAX_PROJECT_BYTES = MAX_SCRIPT_BYTES + MAX_BLOCKS_BYTES + 64 * 1024
#: Имя загруженного проекта: имя скрипта без `.py` и, возможно, суффикс даты.
_PROJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}(-\d{8}-\d{4}(-\d+)?)?$")


def parse_project(raw: bytes | str) -> dict[str, Any]:
    """Разобрать и проверить `.swarm`; ошибка — `ScriptError(400)` с понятным текстом."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_PROJECT_BYTES:
            raise ScriptError(413, f"Файл проекта больше {MAX_PROJECT_BYTES // 1024} КБ")
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ScriptError(400, f"Файл проекта не в кодировке UTF-8 ({e.reason})") from e
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ScriptError(400, f"Это не файл проекта .swarm: битый JSON ({e})") from e
    if not isinstance(data, dict):
        raise ScriptError(400, "Это не файл проекта .swarm: нужен объект JSON")
    fmt = data.get("format")
    if fmt != PROJECT_FORMAT:
        raise ScriptError(400, f"Неизвестный формат проекта {fmt!r}: эта версия SwarmLab "
                               f"открывает только format {PROJECT_FORMAT}")
    code = data.get("code")
    if not isinstance(code, str):
        raise ScriptError(400, "В проекте нет кода (поле code)")
    if len(code.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise ScriptError(413, f"Код проекта больше {MAX_SCRIPT_BYTES // 1024} КБ")
    name = data.get("name")
    if not isinstance(name, str) or not _SCRIPT_NAME.match(f"{name}.py") \
            or name.lower() in _WIN_RESERVED:
        raise ScriptError(400, f"Недопустимое имя проекта {name!r}: только латинские буквы, "
                               "цифры и _, начинается с буквы (например, my_bees)")
    mode = data.get("mode")
    if mode not in PROJECT_MODES:
        raise ScriptError(400, f"Неизвестный режим проекта {mode!r}: нужен blocks или python")
    blocks = data.get("blocks")
    if mode == "blocks" and not isinstance(blocks, dict):
        raise ScriptError(400, "Проект в режиме блоков, но блоков в нём нет (поле blocks)")
    if mode == "python":
        blocks = None
    created = data.get("created")
    return {"format": PROJECT_FORMAT, "name": name,
            "created": created if isinstance(created, str) else None,
            "mode": mode, "code": code.replace("\r\n", "\n"), "blocks": blocks}


def code_sha256(code: str) -> str:
    """sha256 текста кода (так же считает браузер для предупреждения о чужом коде)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _same_content(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a["mode"], a["code"], a["blocks"]) == (b["mode"], b["code"], b["blocks"])


class ProjectStore:
    """Папка загруженных проектов; `scripts` — куда «Открыть в редакторе» кладёт копию."""

    def __init__(self, folder: Path, scripts: ScriptStore) -> None:
        self.folder = Path(folder).resolve()
        self.scripts = scripts

    # ------------------------------------------------------------ пути

    def path(self, name: str, suffix: str = ".py") -> Path:
        stem = name[: -len(suffix)] if name.endswith(suffix) else name
        if not _PROJECT_NAME.match(stem) or stem.split("-")[0].lower() in _WIN_RESERVED:
            raise ScriptError(400, f"Недопустимое имя проекта {name!r}")
        path = (self.folder / f"{stem}{suffix}").resolve()
        if path.parent != self.folder:
            raise ScriptError(400, f"Недопустимое имя проекта {name!r}")
        return path

    def _load(self, stem: str) -> dict[str, Any] | None:
        swarm = self.path(stem, PROJECT_SUFFIX)
        if not swarm.is_file():
            return None
        try:
            return parse_project(swarm.read_bytes())
        except ScriptError:
            return None

    # ------------------------------------------------------------ операции

    def add(self, raw: bytes) -> dict[str, Any]:
        """Загрузить проект. `status`: "new" — записан, "same" — такой уже есть."""
        project = parse_project(raw)
        base = project["name"]
        candidates = [base]
        stamp = f"{base}-{datetime.now():%Y%m%d-%H%M}"
        candidates += [stamp, *(f"{stamp}-{k}" for k in range(2, 100))]
        for stem in candidates:
            old = self._load(stem)
            if old is not None and _same_content(old, project):
                return {**self.info(stem), "status": "same"}
            if old is None and not self.path(stem, PROJECT_SUFFIX).exists():
                break
        else:
            raise ScriptError(409, f"Слишком много версий проекта {base}")
        code = project["code"].encode("utf-8")
        blocks_data = None
        if project["blocks"] is not None:
            blocks_file = {"format": 1, "mode": "blocks", "workspace": project["blocks"]}
            blocks_data = json.dumps(blocks_file, ensure_ascii=False, indent=1).encode("utf-8")
            if len(blocks_data) > MAX_BLOCKS_BYTES:
                raise ScriptError(413, f"Блоки проекта больше {MAX_BLOCKS_BYTES // 1024} КБ")
        self.folder.mkdir(parents=True, exist_ok=True)
        py = self.path(stem)
        if blocks_data is not None:
            _atomic_write(py.with_name(stem + BLOCKS_SUFFIX), blocks_data)
        _atomic_write(py, code)
        _atomic_write(self.path(stem, PROJECT_SUFFIX), raw)  # последним: проект загружен
        return {**self.info(stem), "status": "new"}

    def info(self, stem: str) -> dict[str, Any]:
        project = self._load(stem)
        if project is None:
            raise ScriptError(404, f"Нет проекта {stem}")
        swarm = self.path(stem, PROJECT_SUFFIX)
        return {"name": stem, "title": project["name"], "mode": project["mode"],
                "created": project["created"],
                "uploaded": datetime.fromtimestamp(swarm.stat().st_mtime).isoformat(
                    timespec="seconds"),
                "path": self.scripts.rel(self.path(stem)),
                "sha256": code_sha256(project["code"])}

    def list(self) -> list[dict[str, Any]]:
        if not self.folder.is_dir():
            return []
        out = []
        for swarm in self.folder.glob(f"*{PROJECT_SUFFIX}"):
            stem = swarm.name[: -len(PROJECT_SUFFIX)]
            if not _PROJECT_NAME.match(stem):
                continue
            try:
                out.append(self.info(stem))
            except ScriptError:
                continue
        out.sort(key=lambda p: p["uploaded"], reverse=True)
        return out

    def read(self, name: str) -> dict[str, Any]:
        stem = name[: -len(PROJECT_SUFFIX)] if name.endswith(PROJECT_SUFFIX) else name
        project = self._load(stem)
        if project is None:
            raise ScriptError(404, f"Нет проекта {name}")
        return {**self.info(stem), "code": project["code"], "blocks": project["blocks"]}

    def to_editor(self, name: str, target: str | None = None) -> dict[str, Any]:
        """Копия проекта — свой скрипт редактора (с блоками); имя не занимает чужое."""
        project = self.read(name)
        stem = (target[:-3] if target and target.endswith(".py") else target) \
            or project["name"].replace("-", "_")
        stem = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:60] or "project"
        if not re.match(r"[A-Za-z_]", stem):
            stem = f"p_{stem}"
        if is_readonly(f"{stem}.py"):
            stem = f"my_{stem}"
        existing = {s["name"] for s in self.scripts.list()}
        candidate, k = f"{stem}.py", 1
        while candidate in existing:
            k += 1
            candidate = f"{stem}_{k}.py"
        blocks = ({"format": 1, "mode": "blocks", "workspace": project["blocks"]}
                  if project["blocks"] is not None else None)
        saved = self.scripts.write(candidate, project["code"], blocks)
        return {"name": candidate, "project": project["name"], "script": saved}

    def check_file(self, name: str) -> tuple[Path, list[SyntaxProblem]]:
        """Синтаксис проекта перед матчем (код не исполняется)."""
        path = self.path(name)
        if not path.is_file():
            raise ScriptError(404, f"Нет проекта {name}")
        return path, check_syntax(path.read_text(encoding="utf-8"), path.name)
