"""Данные пользователя портала (`serve --public`, M9a, DECISIONS №92).

Папка данных (`--data`, по умолчанию `<root>/data`):

    swarmlab.db                     база (`server/accounts.py`)
    users/<id>/scripts/             свои скрипты редактора (+ `.blocks.json`)
    users/<id>/projects/            загруженные проекты `.swarm`
    users/<id>/replays/             реплеи матчей пользователя
    users/<id>/logs/<матч>/         логи кода игрока его матчей

Пути строятся только из числового id пользователя, не из почты. Общие примеры модуля
(`template.py`, `example_*.py` из папки редактора `examples/<модуль>/`) видны всем и только
для чтения; остальные файлы той папки (`my_*.py` локального режима) на портале не видны.

Реплеи: последние `keep_last` незакреплённых хранятся сами; «Сохранить» закрепляет (флаг
`pinned` в базе), закреплённые — в квоте `pinned_max_count` штук и `pinned_max_mb`;
незакреплённые старше `unpinned_max_age_days` удаляются. Очистка — при окончании матча
и при старте сервера.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import stat
import sys
import time
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from swarmlab.server.accounts import AccountError, Database, ReplaySettings
from swarmlab.server.projects import PROJECT_FORMAT, PROJECT_SUFFIX, ProjectStore
from swarmlab.server.scripts import (
    _SCRIPT_NAME,
    ScriptError,
    ScriptStore,
    SyntaxProblem,
    is_readonly,
)

#: Имя реплея: как id матча (`<матч>-s<seed>-<дата-время>[-n]`).
_REPLAY_NAME = re.compile(r"^[A-Za-z0-9_][\w.\-]{0,200}$")
_MB = 1024 * 1024


def user_dir(data: Path, user_id: int) -> Path:
    """Папка пользователя — только из числового id."""
    return Path(data) / "users" / str(int(user_id))


def remove_tree(path: Path) -> None:
    """Удалить папку целиком (на Windows — снимая «только чтение»; несколько попыток)."""
    def retry(func: Callable[..., Any], p: str, _exc: Any) -> None:
        Path(p).chmod(stat.S_IWRITE)
        func(p)

    for attempt in range(10):
        if not path.exists():
            return
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=retry)
            else:
                shutil.rmtree(path, onerror=retry)
            return
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.2)  # файл ещё держит процесс, который только что вышел


# ====================================================================== скрипты


class UserScripts(ScriptStore):
    """Свои скрипты пользователя + общие примеры только для чтения."""

    def __init__(self, folder: Path, root: Path, shared: ScriptStore) -> None:
        super().__init__(folder, root)
        self.shared = shared

    def _shared_names(self) -> set[str]:
        return {s["name"] for s in self.shared.list() if is_readonly(s["name"])}

    def list(self) -> list[dict[str, Any]]:
        own = []
        if self.folder.is_dir():
            files = [p for p in self.folder.glob("*.py")
                     if _SCRIPT_NAME.match(p.name) and not is_readonly(p.name)]
            files.sort(key=lambda p: p.name.lower())
            own = [self.info(p) for p in files]
        shared = [s for s in self.shared.list() if is_readonly(s["name"])]
        return own + shared

    def read(self, name: str) -> dict[str, Any]:
        if is_readonly(name):
            if name not in self._shared_names():
                raise ScriptError(404, f"Нет скрипта {name}")
            return self.shared.read(name)
        return super().read(name)

    def check_file(self, name: str) -> tuple[Path, list[SyntaxProblem]]:
        if is_readonly(name):
            if name not in self._shared_names():
                raise ScriptError(404, f"Нет скрипта {name}")
            return self.shared.check_file(name)
        return super().check_file(name)


# ====================================================================== папка пользователя


class UserSpace:
    """Хранилища одного пользователя."""

    def __init__(self, data: Path, user_id: int, shared: ScriptStore, root: Path) -> None:
        self.user_id = int(user_id)
        self.dir = user_dir(data, user_id)
        self.scripts = UserScripts(self.dir / "scripts", root, shared)
        self.projects = ProjectStore(self.dir / "projects", self.scripts)
        self.replays = self.dir / "replays"
        self.logs = self.dir / "logs"
        self.series = self.dir / "series"
        #: Откуда матчу пользователя можно брать код ульев: свои папки и общие примеры.
        self.script_dirs = [self.scripts.folder, self.projects.folder, shared.folder]

    def export_zip(self) -> bytes:
        """Архив всего своего кода: скрипты — как `.swarm`, загруженные проекты — оригиналы."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for s in self.scripts.list():
                if s["readonly"]:
                    continue
                data = self.scripts.read(s["name"])
                blocks = data.get("blocks")
                mode = blocks["mode"] if blocks else "python"
                project = {
                    "format": PROJECT_FORMAT,
                    "name": s["name"][:-3],
                    "created": data["modified"],
                    "mode": mode,
                    "code": data["text"],
                    "blocks": blocks["workspace"] if blocks and mode == "blocks" else None,
                }
                z.writestr(f"scripts/{s['name'][:-3]}{PROJECT_SUFFIX}",
                           json.dumps(project, ensure_ascii=False, indent=1) + "\n")
            for p in self.projects.list():
                swarm = self.projects.path(p["name"], PROJECT_SUFFIX)
                z.write(swarm, f"projects/{swarm.name}")
        return buf.getvalue()


# ====================================================================== реплеи


class ReplayStore:
    """Реплеи пользователей: строки в базе + файлы `users/<id>/replays/<имя>.swr`."""

    def __init__(self, db: Database, settings: ReplaySettings, data: Path,
                 clock: Callable[[], float] = time.time) -> None:
        self.db = db
        self.settings = settings
        self.data = Path(data)
        self.clock = clock

    def folder(self, user_id: int) -> Path:
        return user_dir(self.data, user_id) / "replays"

    def file(self, user_id: int, name: str) -> Path:
        if not _REPLAY_NAME.match(name):
            raise AccountError(400, "Недопустимое имя реплея")
        return self.folder(user_id) / f"{name}.swr"

    # ------------------------------------------------------------ жизненный цикл

    def start(self, user_id: int, name: str) -> None:
        """Матч начался: реплей пишется (в списке его ещё нет)."""
        self.file(user_id, name)
        self.db.run("INSERT OR REPLACE INTO replays (user_id, name, created, size, pinned, "
                    "finished) VALUES (?, ?, ?, 0, 0, 0)", (user_id, name, self.clock()))

    def finish(self, user_id: int, name: str, busy: Iterable[str] = ()) -> None:
        """Матч закончился: реплей дописан — в список, затем очистка старых."""
        path = self.file(user_id, name)
        row = self.db.one("SELECT 1 FROM replays WHERE user_id = ? AND name = ?",
                          (user_id, name))
        if row is None:  # аккаунт удалён, пока матч доигрывал
            return
        if not path.is_file():
            self.db.run("DELETE FROM replays WHERE user_id = ? AND name = ?", (user_id, name))
        else:
            self.db.run("UPDATE replays SET finished = 1, size = ? WHERE user_id = ? "
                        "AND name = ?", (path.stat().st_size, user_id, name))
        self.cleanup(user_id, busy)

    # ------------------------------------------------------------ список и действия

    def _row(self, user_id: int, name: str) -> Any:
        row = self.db.one("SELECT * FROM replays WHERE user_id = ? AND name = ? AND finished = 1",
                          (user_id, name))
        if row is None or not self.file(user_id, name).is_file():
            raise AccountError(404, f"Нет реплея {name}")
        return row

    def list(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM replays WHERE user_id = ? AND finished = 1 "
                             "ORDER BY created DESC, name DESC", (user_id,))
        return [self._info(r) for r in rows if self.file(user_id, r["name"]).is_file()]

    def _info(self, row: Any) -> dict[str, Any]:
        created = datetime.fromtimestamp(row["created"]).isoformat(timespec="seconds")
        return {"id": row["name"], "name": f"{row['name']}.swr", "size": row["size"],
                "created": created, "modified": created, "pinned": bool(row["pinned"])}

    def path(self, user_id: int, name: str) -> Path:
        """Файл реплея для скачивания; чужой или пишущийся — 404."""
        self._row(user_id, name)
        return self.file(user_id, name)

    def pin(self, user_id: int, name: str, pinned: bool) -> dict[str, Any]:
        row = self._row(user_id, name)
        if pinned and not row["pinned"]:
            use = self.usage(user_id)
            s = self.settings
            if use["pinned_count"] + 1 > s.pinned_max_count:
                raise AccountError(409, f"Сохранено уже {use['pinned_count']} реплеев — это "
                                        f"предел ({s.pinned_max_count}). Уберите из сохранённых "
                                        "или удалите старые")
            if use["pinned_bytes"] + row["size"] > s.pinned_max_mb * _MB:
                raise AccountError(409, f"Сохранённые реплеи займут больше {s.pinned_max_mb:g} МБ"
                                        " — уберите из сохранённых или удалите старые")
        self.db.run("UPDATE replays SET pinned = ? WHERE user_id = ? AND name = ?",
                    (int(pinned), user_id, name))
        return self._info(self._row(user_id, name))

    def delete(self, user_id: int, name: str) -> None:
        self._row(user_id, name)
        self.file(user_id, name).unlink(missing_ok=True)
        self.db.run("DELETE FROM replays WHERE user_id = ? AND name = ?", (user_id, name))

    def usage(self, user_id: int) -> dict[str, Any]:
        row = self.db.one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS b, "
            "COALESCE(SUM(CASE WHEN pinned = 1 THEN 1 ELSE 0 END), 0) AS pn, "
            "COALESCE(SUM(CASE WHEN pinned = 1 THEN size ELSE 0 END), 0) AS pb "
            "FROM replays WHERE user_id = ? AND finished = 1", (user_id,))
        s = self.settings
        return {"count": row["n"], "bytes": row["b"], "pinned_count": row["pn"],
                "pinned_bytes": row["pb"], "pinned_max_count": s.pinned_max_count,
                "pinned_max_mb": s.pinned_max_mb, "keep_last": s.keep_last,
                "unpinned_max_age_days": s.unpinned_max_age_days}

    # ------------------------------------------------------------ очистка

    def cleanup(self, user_id: int, busy: Iterable[str] = ()) -> list[str]:
        """Незакреплённые: оставить `keep_last` последних и не старше срока; вернуть удалённые."""
        busy = set(busy)
        rows = self.db.query("SELECT name, created FROM replays WHERE user_id = ? AND pinned = 0 "
                             "AND finished = 1 ORDER BY created DESC, name DESC", (user_id,))
        edge = self.clock() - self.settings.unpinned_max_age_days * 86400
        removed = []
        for i, r in enumerate(rows):
            if r["name"] in busy:
                continue
            if i >= self.settings.keep_last or r["created"] < edge:
                self.file(user_id, r["name"]).unlink(missing_ok=True)
                self.db.run("DELETE FROM replays WHERE user_id = ? AND name = ?",
                            (user_id, r["name"]))
                removed.append(r["name"])
        return removed

    def startup(self, user_ids: Iterable[int]) -> None:
        """Старт сервера: матчей нет — недописанные строки сверить с диском, файлы без строк
        внести в список, потом очистка у всех."""
        for uid in user_ids:
            for r in self.db.query("SELECT name FROM replays WHERE user_id = ? AND finished = 0",
                                   (uid,)):
                path = self.file(uid, r["name"])
                if path.is_file():
                    self.db.run("UPDATE replays SET finished = 1, size = ? WHERE user_id = ? "
                                "AND name = ?", (path.stat().st_size, uid, r["name"]))
                else:
                    self.db.run("DELETE FROM replays WHERE user_id = ? AND name = ?",
                                (uid, r["name"]))
            folder = self.folder(uid)
            if folder.is_dir():
                known = {r["name"] for r in self.db.query(
                    "SELECT name FROM replays WHERE user_id = ?", (uid,))}
                for p in folder.glob("*.swr"):
                    if p.stem not in known and _REPLAY_NAME.match(p.stem):
                        st = p.stat()
                        self.db.run("INSERT INTO replays (user_id, name, created, size, pinned, "
                                    "finished) VALUES (?, ?, ?, ?, 0, 1)",
                                    (uid, p.stem, st.st_mtime, st.st_size))
            self.cleanup(uid)
