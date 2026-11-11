"""Портал M9a: регистрация, вход, сессии, CSRF, закрытый API, ограничения частоты."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.routing import APIRoute
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from swarmlab.core.config import ConfigError
from swarmlab.server.accounts import load_settings
from swarmlab.server.public import OPEN_PATHS

from .conftest import PASSWORD


def _db(portal) -> sqlite3.Connection:
    conn = sqlite3.connect(portal.cfg.data / "swarmlab.db")
    conn.row_factory = sqlite3.Row
    return conn


def test_register_login_logout_password_is_argon2(portal):
    c = portal.client()
    code, me = c.register("  Leo@Example.RU ")
    assert code == 200, me
    assert me["email"] == "leo@example.ru" and me["role"] == "user" and me["csrf"]
    assert c.json("GET", "/api/me")[0] == 200

    row = _db(portal).execute("SELECT email, password_hash FROM users").fetchone()
    assert row["email"] == "leo@example.ru"
    assert row["password_hash"].startswith("$argon2id$") and PASSWORD not in row["password_hash"]

    code, _ = c.json("POST", "/api/auth/logout")
    assert code == 200
    assert c.json("GET", "/api/me")[0] == 401

    code, me = c.login("LEO@example.ru")  # почта без учёта регистра
    assert code == 200 and me["email"] == "leo@example.ru"
    assert c.json("GET", "/api/me")[0] == 200


def test_wrong_password_taken_email_short_password_are_clear_errors(portal):
    c = portal.client()
    code, data = c.register("a@b.ru", "1234567")
    assert code == 400 and "не меньше 8" in data["detail"]
    code, data = c.register("не почта", PASSWORD)
    assert code == 400 and "Почта" in data["detail"]
    assert c.register("a@b.ru")[0] == 200
    code, data = portal.client().register("A@B.RU")
    assert code == 409 and "уже зарегистрирована" in data["detail"]
    code, data = portal.client().login("a@b.ru", "wrong password")
    assert code == 401 and data["detail"] == "Неверная почта или пароль"
    code, data = portal.client().login("nobody@b.ru")
    assert code == 401 and data["detail"] == "Неверная почта или пароль"


def test_session_cookie_http_only_lax_secure_only_over_https(make_portal):
    p = make_portal(proxy={"trusted": ["127.0.0.1"]})
    c = p.client()
    _, headers, _ = c.raw("POST", "/api/auth/register",
                          b'{"email": "a@b.ru", "password": "correct horse 1"}',
                          {"Content-Type": "application/json"})
    cookie = headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    _, headers, _ = c.raw("POST", "/api/auth/login",
                          b'{"email": "a@b.ru", "password": "correct horse 1"}',
                          {"Content-Type": "application/json", "X-Forwarded-Proto": "https"})
    assert "secure" in headers["set-cookie"].lower()  # за доверенным прокси по HTTPS


def test_without_login_only_auth_pages_and_static_every_api_and_ws_401(portal):
    anon = portal.client()
    checked = 0
    for route in portal.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        if route.path in OPEN_PATHS:
            continue
        path = route.path.replace("{seed}", "1")
        for name in ("mid", "rid", "name", "sid"):
            path = path.replace(f"{{{name}}}", "x")
        for method in route.methods:
            code, _, _ = anon.raw(method, path, b"{}", {"Content-Type": "application/json"})
            assert code == 401, (method, path, code)
            checked += 1
    assert checked >= 30
    assert anon.raw("GET", "/api/nope")[0] == 401  # и несуществующие тоже

    assert anon.raw("GET", "/")[0] == 200
    assert anon.raw("GET", "/js/core/app.js")[0] == 200
    assert anon.raw("GET", "/style.css")[0] == 200
    # Страницы входа и регистрации — те же маршруты, открыты без сессии.
    assert anon.json("POST", "/api/auth/login", {"email": "x@y.ru", "password": "x"})[0] == 401
    assert anon.register("new@y.ru")[0] == 200

    with pytest.raises(InvalidStatus) as e:
        connect(f"{portal.ws}/ws/matches/x", open_timeout=10).close()
    assert e.value.response.status_code == 401


def test_mutating_request_without_csrf_token_is_403(portal):
    c = portal.user("a@b.ru")
    body = {"text": "def loop(self):\n    pass\n"}
    code, data = c.json("PUT", "/api/scripts/mine.py", body, csrf=False)
    assert code == 403 and "CSRF" in data["detail"]
    c.headers["X-CSRF-Token"] = "not-the-token"
    assert c.json("PUT", "/api/scripts/mine.py", body, csrf=False)[0] == 403
    assert c.json("POST", "/api/auth/logout", csrf=False)[0] == 403
    del c.headers["X-CSRF-Token"]
    assert c.json("PUT", "/api/scripts/mine.py", body)[0] == 200
    assert c.json("GET", "/api/scripts/mine.py")[0] == 200  # чтение без токена

    # Вход с чужой формы: не JSON — 415.
    code, _, _ = portal.client().raw("POST", "/api/auth/login", b"email=a@b.ru",
                                     {"Content-Type": "application/x-www-form-urlencoded"})
    assert code == 415


def test_fourth_registration_from_one_ip_is_429(portal):
    for i in range(3):
        assert portal.client().register(f"u{i}@b.ru")[0] == 200
    code, data = portal.client().register("u3@b.ru")
    assert code == 429 and "регистраций" in data["detail"]
    # Через час — снова можно.
    t = portal.portal.now() + 3601
    portal.portal.now = lambda: t
    assert portal.client().register("u3@b.ru")[0] == 200


def test_forwarded_for_trusted_only_from_proxy(make_portal):
    direct = make_portal()  # прокси нет: X-Forwarded-For — просто заголовок
    for i in range(3):
        assert direct.client(**{"X-Forwarded-For": f"10.0.0.{i}"}).register(f"d{i}@b.ru")[0] == 200
    assert direct.client(**{"X-Forwarded-For": "10.0.0.9"}).register("d9@b.ru")[0] == 429

    proxied = make_portal(proxy={"trusted": ["127.0.0.1"]})  # за Caddy: IP — из заголовка
    for i in range(3):
        assert proxied.client(**{"X-Forwarded-For": "10.0.0.1"}).register(f"p{i}@b.ru")[0] == 200
    assert proxied.client(**{"X-Forwarded-For": "10.0.0.1"}).register("p3@b.ru")[0] == 429
    assert proxied.client(**{"X-Forwarded-For": "10.0.0.2"}).register("p4@b.ru")[0] == 200


def test_login_locked_after_n_wrong_passwords_then_opens(portal):
    portal.user("a@b.ru")
    n = portal.cfg.public.limits.login_failures
    for _ in range(n):
        assert portal.client().login("a@b.ru", "wrong password")[0] == 401
    code, data = portal.client().login("a@b.ru")  # даже верный пароль
    assert code == 429 and "попробуйте через 15 мин" in data["detail"]
    t = portal.portal.now() + portal.cfg.public.limits.login_lockout_s + 1
    portal.portal.now = lambda: t
    assert portal.client().login("a@b.ru")[0] == 200


def test_session_expires(portal):
    c = portal.user("a@b.ru")
    t = portal.portal.now() + portal.cfg.public.accounts.session_days * 86400 + 1
    portal.portal.now = lambda: t
    assert c.json("GET", "/api/me")[0] == 401


def test_public_config_overrides_defaults(tmp_path):
    own = tmp_path / "portal.yaml"
    own.write_text("replays:\n  keep_last: 3\nproxy:\n  trusted: [172.18.0.2]\n",
                   encoding="utf-8")
    s = load_settings(own)
    assert s.replays.keep_last == 3 and s.replays.pinned_max_count == 50
    assert s.proxy.trusted == ["172.18.0.2"] and s.accounts.password_min == 8
    own.write_text("replays:\n  keep_lats: 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="keep_lats"):
        load_settings(own)
