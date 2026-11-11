"""Публичный режим сервера — портал (`swarmlab serve --public`, M9a, DECISIONS №90–92, 95, 97).

Без флага `--public` ничего из этого модуля не подключается: сервер работает как раньше.

Вход:
    POST   /api/auth/register      {email, password} → профиль; cookie сессии
    POST   /api/auth/login         {email, password} → профиль; cookie сессии
    POST   /api/auth/logout        выйти (сессия закрыта, cookie стёрт)
Профиль:
    GET    /api/me                 {email, role, csrf, usage}; без входа — 401
    POST   /api/me/password        {current, new} — смена пароля (неверный текущий — 403)
    DELETE /api/me                 {password} — удалить аккаунт: матчи, база, папка
    GET    /api/me/export          zip всего своего кода (`.swarm`)
Свои данные:
    POST   /api/replays/{id}/pin   {pinned} — «Сохранить» (сверх квоты — 409)
    DELETE /api/replays/{id}       удалить реплей
    DELETE /api/scripts/{name}     удалить свой скрипт
    DELETE /api/projects/{name}    удалить загруженный проект

Охрана (`PortalGuard`, ASGI — и HTTP, и WebSocket): без входа открыты только статика
и `/api/auth/register|login`; остальное `/api/*` — 401, WS — отказ рукопожатия 401.
Изменяющие запросы (не GET/HEAD/OPTIONS) — только с заголовком `X-CSRF-Token` сессии,
иначе 403; вход и регистрация — только с телом JSON (форма с чужого сайта так не пошлёт).
IP клиента и HTTPS за прокси — из `X-Forwarded-For` / `X-Forwarded-Proto`, только если
запрос пришёл от доверенного адреса (`proxy.trusted` в настройках).
"""

from __future__ import annotations

import asyncio
import hmac
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket

from swarmlab.server.accounts import AccountError, Accounts, Database, PublicSettings, User
from swarmlab.server.scripts import ScriptError, ScriptStore
from swarmlab.server.storage import ReplayStore, UserSpace, remove_tree, user_dir

if TYPE_CHECKING:
    from swarmlab.server.app import MatchManager, MatchProcess

#: Без входа открыты только эти маршруты API.
OPEN_PATHS = frozenset({"/api/auth/register", "/api/auth/login"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-csrf-token"
NEED_LOGIN = "Нужно войти"
SERIES_OFF = ("Серии матчей на портале пока выключены — запускайте матчи по одному "
              "(лимиты серий появятся позже)")


class Credentials(BaseModel):
    email: Any = ""
    password: Any = ""


class PasswordChange(BaseModel):
    current: Any = ""
    new: Any = ""


class PasswordConfirm(BaseModel):
    password: Any = ""


class PinRequest(BaseModel):
    pinned: bool = True


class Portal:
    """Аккаунты, папки пользователей и реплеи публичного режима."""

    def __init__(self, settings: PublicSettings, data: Path, root: Path,
                 shared: ScriptStore) -> None:
        self.settings = settings
        self.data = Path(data).resolve()
        self.root = Path(root).resolve()
        self.shared = shared
        #: Часы портала (сессии, лимиты, возраст реплеев); тесты подменяют.
        self.now = time.time
        self.db = Database(self.data / "swarmlab.db")
        self.accounts = Accounts(self.db, settings, clock=lambda: self.now())
        self.replays = ReplayStore(self.db, settings.replays, self.data,
                                   clock=lambda: self.now())
        self.manager: MatchManager | None = None

    # ------------------------------------------------------------ пользователь

    def space(self, user: User) -> UserSpace:
        return UserSpace(self.data, user.id, self.shared, self.root)

    def user_for(self, conn: HTTPConnection) -> User | None:
        return self.accounts.session(conn.cookies.get(self.settings.cookie.name))

    def _trusted(self, scope: Scope) -> bool:
        client = scope.get("client")
        return bool(client) and client[0] in self.settings.proxy.trusted

    def client_ip(self, scope: Scope) -> str:
        """IP клиента; за доверенным прокси — первый недоверенный справа в X-Forwarded-For."""
        client = scope.get("client")
        host = client[0] if client else "unknown"
        if not self._trusted(scope):
            return host
        xff = HTTPConnection(scope).headers.get("x-forwarded-for", "")
        for part in reversed([p.strip() for p in xff.split(",") if p.strip()]):
            if part not in self.settings.proxy.trusted:
                return part
        return host

    def is_https(self, scope: Scope) -> bool:
        if scope.get("scheme") in ("https", "wss"):
            return True
        if self._trusted(scope):
            proto = HTTPConnection(scope).headers.get("x-forwarded-proto", "")
            return proto.split(",")[0].strip().lower() == "https"
        return False

    def set_cookie(self, response: Response, token: str, scope: Scope) -> None:
        c = self.settings.cookie
        secure = c.secure == "always" or (c.secure == "auto" and self.is_https(scope))
        response.set_cookie(c.name, token, max_age=int(self.settings.accounts.session_days * 86400),
                            path="/", httponly=True, samesite="lax", secure=secure)

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(self.settings.cookie.name, path="/", httponly=True,
                               samesite="lax")

    def me(self, user: User) -> dict[str, Any]:
        return {"email": user.email, "role": user.role, "csrf": user.csrf,
                "usage": self.replays.usage(user.id)}

    # ------------------------------------------------------------ матчи

    def on_match_start(self, m: MatchProcess) -> None:
        if m.owner is not None:
            self.replays.start(m.owner, m.replay.stem)

    def on_match_end(self, m: MatchProcess) -> None:
        if m.owner is None or self.manager is None:
            return
        busy = [x.replay.stem for x in self.manager.running() if x.owner == m.owner]
        self.replays.finish(m.owner, m.replay.stem, busy)

    def startup(self) -> None:
        """Старт сервера: сверить реплеи с диском и удалить старые."""
        self.replays.startup(self.accounts.user_ids())

    def close(self) -> None:
        self.db.close()


def current_user(request: Request | WebSocket) -> User:
    """Вошедший пользователь (охрана уже проверила сессию)."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, NEED_LOGIN)
    return user


# ====================================================================== охрана


class PortalGuard:
    """ASGI-прослойка: сессия, 401, CSRF, Origin у WebSocket."""

    def __init__(self, app: ASGIApp, portal: Portal) -> None:
        self.app = app
        self.portal = portal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        path = scope.get("path", "")
        if kind == "http" and (path == "/api" or path.startswith("/api/")):
            denied = self._check_http(scope)
            if denied is not None:
                # Дочитать тело: иначе сервер закроет сокет с непрочитанными данными, и на
                # Windows клиент вместо 401 получит обрыв соединения (RST).
                await _drain(receive)
                await denied(scope, receive, send)
                return
        elif kind == "websocket":
            status, text = self._check_ws(scope)
            if status:
                await _deny_ws(scope, receive, send, status, text)
                return
        await self.app(scope, receive, send)

    def _check_http(self, scope: Scope) -> Response | None:
        conn = HTTPConnection(scope)
        method = scope.get("method", "GET")
        if scope["path"] in OPEN_PATHS:
            ctype = conn.headers.get("content-type", "")
            if method not in SAFE_METHODS and not ctype.startswith("application/json"):
                return JSONResponse({"detail": "Нужно тело JSON"}, 415)
            return None
        user = self.portal.user_for(conn)
        if user is None:
            return JSONResponse({"detail": NEED_LOGIN}, 401)
        if method not in SAFE_METHODS:
            token = conn.headers.get(CSRF_HEADER, "")
            if not token or not hmac.compare_digest(token, user.csrf):
                return JSONResponse({"detail": "Запрос отклонён: нет токена защиты (CSRF). "
                                               "Обновите страницу"}, 403)
        scope.setdefault("state", {})["user"] = user
        return None

    def _check_ws(self, scope: Scope) -> tuple[int, str]:
        conn = HTTPConnection(scope)
        origin = conn.headers.get("origin")
        host = conn.headers.get("host", "")
        if origin and origin.split("://", 1)[-1].rstrip("/") != host:
            return 403, "Чужой сайт"
        user = self.portal.user_for(conn)
        if user is None:
            return 401, NEED_LOGIN
        scope.setdefault("state", {})["user"] = user
        return 0, ""


#: Сколько тела отклонённого запроса дочитывать (больше — пусть соединение рвётся).
_DRAIN_MAX = 4 * 1024 * 1024


async def _drain(receive: Receive) -> None:
    got = 0
    while got <= _DRAIN_MAX:
        msg = await receive()
        if msg["type"] != "http.request":
            return
        got += len(msg.get("body", b""))
        if not msg.get("more_body", False):
            return


async def _deny_ws(scope: Scope, receive: Receive, send: Send, status: int, text: str) -> None:
    ws = WebSocket(scope, receive, send)
    if "websocket.http.response" in scope.get("extensions", {}):
        await ws.send_denial_response(JSONResponse({"detail": text}, status))
    else:  # сервер не умеет HTTP-ответ на рукопожатие — закрыть до accept (HTTP 403)
        await ws.close(code=4000 + status)


# ====================================================================== маршруты


def add_routes(app: FastAPI, portal: Portal, manager: MatchManager) -> None:
    """Маршруты, которых нет в локальном режиме."""

    @app.exception_handler(AccountError)
    async def account_error(_: Request, e: AccountError) -> JSONResponse:
        return JSONResponse({"detail": e.message}, e.status)

    # ------------------------------------------------------------ вход

    @app.post("/api/auth/register")
    def register(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        user, token = portal.accounts.register(body.email, body.password,
                                               portal.client_ip(request.scope))
        portal.set_cookie(response, token, request.scope)
        return portal.me(user)

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        user, token = portal.accounts.login(body.email, body.password)
        portal.set_cookie(response, token, request.scope)
        return portal.me(user)

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, Any]:
        portal.accounts.close_session(current_user(request).token)
        portal.clear_cookie(response)
        return {"ok": True}

    # ------------------------------------------------------------ профиль

    @app.get("/api/me")
    def me(request: Request) -> dict[str, Any]:
        return portal.me(current_user(request))

    @app.post("/api/me/password")
    def change_password(body: PasswordChange, request: Request) -> dict[str, Any]:
        portal.accounts.change_password(current_user(request), body.current, body.new)
        return {"ok": True}

    @app.delete("/api/me")
    async def delete_account(body: PasswordConfirm, request: Request,
                             response: Response) -> dict[str, Any]:
        user = current_user(request)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, portal.accounts.verify_user_password, user.id,
                                   body.password)
        mine = [m for m in manager.matches.values() if m.owner == user.id]
        for m in mine:  # остановить и дождаться выхода процессов: файлы отпущены
            m.stop()
        await loop.run_in_executor(None, manager.wait_exit, mine)
        for m in mine:
            manager.matches.pop(m.id, None)
        portal.accounts.delete_user(user.id)
        await loop.run_in_executor(None, remove_tree, user_dir(portal.data, user.id))
        portal.clear_cookie(response)
        return {"ok": True}

    @app.get("/api/me/export")
    def export(request: Request) -> Response:
        data = portal.space(current_user(request)).export_zip()
        name = f"swarmlab-{datetime.now():%Y%m%d-%H%M}.zip"
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------ свои данные

    @app.post("/api/replays/{rid}/pin")
    def pin_replay(rid: str, body: PinRequest, request: Request) -> dict[str, Any]:
        return portal.replays.pin(current_user(request).id, _stem(rid), body.pinned)

    @app.delete("/api/replays/{rid}")
    def delete_replay(rid: str, request: Request) -> dict[str, Any]:
        portal.replays.delete(current_user(request).id, _stem(rid))
        return {"ok": True}

    @app.delete("/api/scripts/{name}")
    def delete_script(name: str, request: Request) -> dict[str, Any]:
        _call(portal.space(current_user(request)).scripts.delete, name)
        return {"ok": True}

    @app.delete("/api/projects/{name}")
    def delete_project(name: str, request: Request) -> dict[str, Any]:
        _call(portal.space(current_user(request)).projects.delete, name)
        return {"ok": True}


def _stem(rid: str) -> str:
    return rid[:-4] if rid.endswith(".swr") else rid


def _call(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except ScriptError as e:
        raise HTTPException(e.status, e.message) from e
