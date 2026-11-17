"""Администрирование публичного портала (M9c)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from swarmlab.server.accounts import AccountError
from swarmlab.server.storage import remove_tree, user_dir

if TYPE_CHECKING:
    from swarmlab.server.app import MatchManager
    from swarmlab.server.public import Portal


class BlockRequest(BaseModel):
    blocked: bool


class RoleRequest(BaseModel):
    role: str


def _admin(request: Request, portal: Portal) -> int:
    user = getattr(request.state, "user", None) or portal.user_for(request)
    if user is None or user.role != "admin":
        raise HTTPException(403, "Доступно только администратору")
    return user.id


def _target(portal: Portal, uid: int) -> None:
    if not portal.accounts.exists(uid):
        raise AccountError(404, "Пользователь не найден")


def _usage(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.exists() else 0


def _cpu_percent() -> float | None:
    """Загрузка CPU Linux по /proc/stat; при недоступности показать пустое значение."""
    try:
        values = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    except (OSError, ValueError, IndexError):
        return None
    total = sum(values)
    idle = values[3] + values[4]
    previous = getattr(_cpu_percent, "previous", None)
    _cpu_percent.previous = (total, idle)
    if previous is None or total == previous[0]:
        return None
    return round(100 * (1 - (idle - previous[1]) / (total - previous[0])), 1)


def add_admin_routes(app: FastAPI, portal: Portal, manager: MatchManager) -> None:
    """Маршруты админки; PortalGuard уже проверяет сессию и CSRF для API."""

    @app.get("/admin")
    def page(request: Request) -> FileResponse:
        _admin(request, portal)
        return FileResponse(Path(__file__).with_name("admin.html"))

    @app.get("/api/admin/users")
    def users(request: Request) -> list[dict[str, Any]]:
        _admin(request, portal)
        rows = portal.db.query("SELECT id, email, role, created, last_login, blocked "
                               "FROM users ORDER BY id")
        return [{**dict(row), "bytes": _usage(user_dir(portal.data, row["id"]))}
                for row in rows]

    @app.post("/api/admin/users/{uid}/password")
    def password(uid: int, request: Request) -> dict[str, str]:
        _admin(request, portal)
        return {"password": portal.accounts.reset_password(uid)}

    @app.post("/api/admin/users/{uid}/block")
    async def block(uid: int, body: BlockRequest, request: Request) -> dict[str, bool]:
        admin_id = _admin(request, portal)
        _target(portal, uid)
        if uid == admin_id and body.blocked:
            raise HTTPException(400, "Нельзя заблокировать себя")
        if body.blocked:
            mine = [m for m in manager.running() if m.owner == uid]
            for m in mine:
                m.stop()
            await asyncio.get_running_loop().run_in_executor(None, manager.wait_exit, mine)
            await asyncio.get_running_loop().run_in_executor(None, app.state.series.stop_under,
                                                              user_dir(portal.data, uid))
        portal.accounts.set_blocked(uid, body.blocked)
        return {"blocked": body.blocked}

    @app.post("/api/admin/users/{uid}/role")
    def role(uid: int, body: RoleRequest, request: Request) -> dict[str, str]:
        admin_id = _admin(request, portal)
        if uid == admin_id and body.role != "admin":
            raise HTTPException(400, "Нельзя снять роль администратора с себя")
        portal.accounts.set_role(uid, body.role)
        return {"role": body.role}

    @app.delete("/api/admin/users/{uid}")
    async def delete(uid: int, request: Request) -> dict[str, bool]:
        admin_id = _admin(request, portal)
        _target(portal, uid)
        if uid == admin_id:
            raise HTTPException(400, "Нельзя удалить себя здесь")
        mine = [m for m in manager.matches.values() if m.owner == uid]
        for m in mine:
            m.stop()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, manager.wait_exit, mine)
        for m in mine:
            manager.matches.pop(m.id, None)
        await loop.run_in_executor(None, app.state.series.stop_under, user_dir(portal.data, uid))
        portal.accounts.delete_user(uid)
        await loop.run_in_executor(None, remove_tree, user_dir(portal.data, uid))
        return {"ok": True}

    @app.get("/api/admin/status")
    def status(request: Request) -> dict[str, Any]:
        _admin(request, portal)
        disk = shutil.disk_usage(portal.data)
        return {"cpu_percent": _cpu_percent(), "disk_free": disk.free,
                "matches": [{**m.info(), "owner": m.owner} for m in manager.running()]}

    @app.post("/api/admin/matches/{mid}/stop")
    def stop(mid: str, request: Request) -> dict[str, bool]:
        _admin(request, portal)
        m = manager.matches.get(mid)
        if m is None:
            raise HTTPException(404, "Матч не найден")
        m.stop()
        return {"ok": True}
