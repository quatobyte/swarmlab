"""Создать или восстановить архив данных портала; база копируется SQLite backup API."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def create(data: Path, backups: Path) -> Path:
    source = data / "swarmlab.db"
    if not source.is_file():
        raise FileNotFoundError(source)
    backups.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("swarmlab-%Y%m%d-%H%M%S-%f.tar.gz")
    result = backups / name
    with tempfile.TemporaryDirectory() as temp:
        db_copy = Path(temp) / "swarmlab.db"
        with closing(sqlite3.connect(source)) as db, closing(sqlite3.connect(db_copy)) as dst:
            db.backup(dst)
        with tarfile.open(result, "w:gz") as archive:
            archive.add(db_copy, arcname="swarmlab.db")
            users = data / "users"
            if users.exists():
                archive.add(users, arcname="users")
    os.chmod(result, 0o600)
    for old in sorted(backups.glob("swarmlab-*.tar.gz"), reverse=True)[7:]:
        old.unlink()
    return result


def restore(archive_path: Path, data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    if any(data.iterdir()):
        raise ValueError("Папка восстановления должна быть пустой")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for item in members:
            parts = Path(item.name).parts
            if (not (item.isdir() or item.isfile()) or not parts
                    or parts[0] not in ("users", "swarmlab.db")
                    or (parts[0] == "swarmlab.db" and len(parts) != 1)
                    or ".." in parts or Path(item.name).is_absolute()):
                raise ValueError(f"Небезопасный путь в архиве: {item.name}")
        if not any(item.name == "swarmlab.db" for item in members):
            raise ValueError("В архиве нет базы")
        for item in members:
            target = data / item.name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(item)
                if source is None:
                    raise ValueError(f"Не прочитать файл: {item.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("create")
    make.add_argument("data", type=Path)
    make.add_argument("backups", type=Path)
    recover = sub.add_parser("restore")
    recover.add_argument("archive", type=Path)
    recover.add_argument("data", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        print(create(args.data, args.backups))
    else:
        restore(args.archive, args.data)
        print(args.data)


if __name__ == "__main__":
    main()
