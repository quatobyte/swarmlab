"""Маршруты администратора и резервная копия портала (M9c)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.backup import create, restore


def test_admin_access_and_account_actions(portal) -> None:
    admin = portal.user("admin@example.com")
    user = portal.user("bee@example.com")
    uid = portal.portal.db.one("SELECT id FROM users WHERE email = ?", ("bee@example.com",))["id"]
    assert user.json("GET", "/api/admin/users")[0] == 403
    assert admin.json("GET", "/api/admin/status")[0] == 403
    assert user.raw("GET", "/admin")[0] == 403
    admin_id = portal.portal.db.one("SELECT id FROM users WHERE email = ?",
                                    ("admin@example.com",))["id"]
    portal.portal.accounts.set_role(admin_id, "admin")
    assert admin.login("admin@example.com")[0] == 200
    assert admin.raw("GET", "/admin")[0] == 200
    code, users = admin.json("GET", "/api/admin/users")
    assert code == 200 and {u["email"] for u in users} == {"admin@example.com", "bee@example.com"}
    assert {"created", "last_login", "bytes", "blocked", "role"} <= users[0].keys()
    assert admin.json("POST", f"/api/admin/users/{uid}/password", csrf=False)[0] == 403
    code, result = admin.json("POST", f"/api/admin/users/{uid}/password")
    assert code == 200 and result["password"]
    assert user.login("bee@example.com")[0] == 401
    assert user.login("bee@example.com", result["password"])[0] == 200
    assert admin.json("POST", f"/api/admin/users/{uid}/block", {"blocked": True})[0] == 200
    assert user.json("GET", "/api/me")[0] == 401
    assert user.login("bee@example.com", result["password"])[0] == 403
    assert admin.json("POST", f"/api/admin/users/{uid}/block", {"blocked": False})[0] == 200
    assert user.login("bee@example.com", result["password"])[0] == 200
    assert admin.json("POST", f"/api/admin/users/{uid}/role", {"role": "admin"})[0] == 200
    assert portal.portal.db.one("SELECT role FROM users WHERE id = ?", (uid,))["role"] == "admin"
    assert admin.json("DELETE", f"/api/admin/users/{uid}")[0] == 200
    assert portal.portal.db.one("SELECT 1 FROM users WHERE id = ?", (uid,)) is None


def test_backup_restores_database_and_user_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "swarmlab.db") as db:
        db.execute("CREATE TABLE users (email TEXT)")
        db.execute("INSERT INTO users VALUES ('bee@example.com')")
    folder = data / "users" / "1"
    (folder / "projects").mkdir(parents=True)
    (folder / "replays").mkdir()
    (folder / "projects" / "hive.swarm").write_bytes(b"project")
    (folder / "replays" / "match.swr").write_bytes(b"replay")
    backups = tmp_path / "backups"
    archive = create(data, backups)
    for _ in range(8):
        create(data, backups)
    assert len(list(backups.glob("*.tar.gz"))) <= 7
    clean = tmp_path / "clean"
    restore(archive if archive.exists() else sorted(backups.glob("*.tar.gz"))[-1], clean)
    with sqlite3.connect(clean / "swarmlab.db") as db:
        assert db.execute("SELECT email FROM users").fetchone()[0] == "bee@example.com"
    assert (clean / "users" / "1" / "projects" / "hive.swarm").read_bytes() == b"project"
    assert (clean / "users" / "1" / "replays" / "match.swr").read_bytes() == b"replay"
