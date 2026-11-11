"""Аккаунты портала (`serve --public`, M9a, DECISIONS №91, №97): база, пароли, сессии, лимиты.

База — один файл SQLite (`<data>/swarmlab.db`, стандартный `sqlite3`):

    users    (id, email, password_hash, role, created, last_login)
    sessions (token_hash, user_id, csrf, created, expires)
    replays  (user_id, name, created, size, pinned, finished)

Почта — логин, хранится в нижнем регистре; писем нет. Пароль — хеш argon2 (`argon2-cffi`).
Сессия — случайный токен в HTTP-only cookie; в базе лежит только его sha256. CSRF-токен
сессии клиент получает в `GET /api/me` и шлёт в заголовке `X-CSRF-Token`.

Ограничения частоты (регистрации с IP, неверные пароли к почте) — в памяти процесса:
после перезапуска сервера счётчики начинаются заново. Время — из `clock` (подменяется в тестах).
"""

from __future__ import annotations

import collections
import hashlib
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from swarmlab.core.config import ConfigError, deep_merge

#: Умолчания настроек портала (рядом с модулем).
DEFAULT_SETTINGS = Path(__file__).with_name("public.yaml")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_MAX = 254
SCHEMA_VERSION = 1

# ====================================================================== настройки


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountSettings(_Strict):
    password_min: int = Field(8, ge=1)
    password_max: int = Field(256, ge=8)
    session_days: float = Field(30, gt=0)


class CookieSettings(_Strict):
    name: str = Field("swarmlab_session", pattern=r"^[A-Za-z0-9_\-]+$")
    secure: Literal["auto", "always", "never"] = "auto"


class LimitSettings(_Strict):
    register_per_ip: int = Field(3, ge=1)
    register_window_s: float = Field(3600, gt=0)
    login_failures: int = Field(5, ge=1)
    login_window_s: float = Field(900, gt=0)
    login_lockout_s: float = Field(900, gt=0)


class ReplaySettings(_Strict):
    keep_last: int = Field(10, ge=0)
    pinned_max_count: int = Field(50, ge=0)
    pinned_max_mb: float = Field(500, ge=0)
    unpinned_max_age_days: float = Field(7, gt=0)


class ProxySettings(_Strict):
    trusted: list[str] = Field(default_factory=list)


class PublicSettings(_Strict):
    """Настройки публичного режима (`public.yaml` + свой `--public-config`)."""

    accounts: AccountSettings = AccountSettings()
    cookie: CookieSettings = CookieSettings()
    limits: LimitSettings = LimitSettings()
    replays: ReplaySettings = ReplaySettings()
    proxy: ProxySettings = ProxySettings()


def load_settings(path: str | Path | None = None) -> PublicSettings:
    """Умолчания пакета, поверх — свой файл (если задан). Ошибка — `ConfigError`."""
    data = _read_yaml(DEFAULT_SETTINGS)
    if path is not None:
        data = deep_merge(data, _read_yaml(Path(path)))
    try:
        return PublicSettings(**data)
    except ValidationError as e:
        raise ConfigError(f"Неверные настройки портала:\n{e}") from e


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"Не прочитать настройки портала {path}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: нужен словарь YAML")
    return data


# ====================================================================== ошибки и пользователь


class AccountError(Exception):
    """Ошибка запроса к аккаунтам; `status` — HTTP-код, `message` — текст для человека."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class User:
    """Вошедший пользователь (по cookie сессии)."""

    id: int
    email: str
    role: str
    csrf: str
    token: str


def normalize_email(email: Any) -> str:
    """Почта для входа: без пробелов по краям, в нижнем регистре; неверная — 400."""
    if not isinstance(email, str):
        raise AccountError(400, "Укажите почту")
    email = email.strip().lower()
    if not email:
        raise AccountError(400, "Укажите почту")
    if len(email) > _EMAIL_MAX or not _EMAIL.match(email):
        raise AccountError(400, "Почта выглядит неправильно — нужен адрес вида имя@пример.ru")
    return email


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ====================================================================== база


class Database:
    """Файл SQLite; один connection на процесс, доступ — под блокировкой."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"База {self.path} новее этой версии SwarmLab "
                               f"(схема {version}, знаю до {SCHEMA_VERSION})")
        if version < 1:
            with self._lock:  # executescript сам закрывает транзакции — BEGIN/COMMIT в скрипте
                self.conn.executescript(f"""
                    BEGIN;
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user',
                        created REAL NOT NULL,
                        last_login REAL
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        token_hash TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        csrf TEXT NOT NULL,
                        created REAL NOT NULL,
                        expires REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                    CREATE TABLE IF NOT EXISTS replays (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        created REAL NOT NULL,
                        size INTEGER NOT NULL DEFAULT 0,
                        pinned INTEGER NOT NULL DEFAULT 0,
                        finished INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, name)
                    );
                    PRAGMA user_version = {SCHEMA_VERSION};
                    COMMIT;
                """)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Транзакция под блокировкой: всё или ничего."""
        with self._lock:
            self.conn.execute("BEGIN")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.conn.execute("COMMIT")

    def query(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, args).fetchone()

    def run(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, args)

    def close(self) -> None:
        with self._lock:
            self.conn.close()


# ====================================================================== лимиты частоты


class RateLimiter:
    """Скользящее окно событий по ключу (в памяти процесса)."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self._events: dict[str, collections.deque[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    def count(self, key: str, window_s: float) -> int:
        with self._lock:
            return len(self._trim(key, window_s))

    def add(self, key: str, window_s: float) -> int:
        """Записать событие; вернуть число событий в окне вместе с ним."""
        with self._lock:
            q = self._trim(key, window_s)
            q.append(self.clock())
            return len(q)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
            self._locked.pop(key, None)

    def lock(self, key: str, seconds: float) -> None:
        with self._lock:
            self._locked[key] = self.clock() + seconds

    def locked_for(self, key: str) -> float:
        """Сколько секунд ключ ещё закрыт (0 — открыт)."""
        with self._lock:
            until = self._locked.get(key)
            if until is None:
                return 0.0
            left = until - self.clock()
            if left <= 0:
                del self._locked[key]
                self._events.pop(key, None)
                return 0.0
            return left

    def _trim(self, key: str, window_s: float) -> collections.deque[float]:
        q = self._events.setdefault(key, collections.deque())
        edge = self.clock() - window_s
        while q and q[0] <= edge:
            q.popleft()
        return q


def _minutes(seconds: float) -> str:
    m = max(1, int(-(-seconds // 60)))
    return f"{m} мин"


# ====================================================================== аккаунты


class Accounts:
    """Регистрация, вход, сессии, смена пароля, удаление строк пользователя."""

    def __init__(self, db: Database, settings: PublicSettings,
                 clock: Callable[[], float] = time.time) -> None:
        self.db = db
        self.settings = settings
        self.clock = clock
        self.hasher = PasswordHasher()
        self.limits = RateLimiter(lambda: self.clock())
        # Для несуществующей почты тоже считаем хеш: время ответа не выдаёт, есть ли аккаунт.
        self._dummy_hash = self.hasher.hash(secrets.token_hex(16))

    # ------------------------------------------------------------ пароли

    def check_password_rules(self, password: Any) -> str:
        a = self.settings.accounts
        if not isinstance(password, str) or len(password) < a.password_min:
            raise AccountError(400, f"Пароль слишком короткий — нужно не меньше "
                                    f"{a.password_min} символов")
        if len(password) > a.password_max:
            raise AccountError(400, f"Пароль слишком длинный — не больше {a.password_max} "
                                    "символов")
        return password

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self.hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_user_password(self, user_id: int, password: Any) -> None:
        """Текущий пароль пользователя (смена пароля, удаление аккаунта); неверный — 403."""
        row = self.db.one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        if row is None or not isinstance(password, str) \
                or not self._verify(row["password_hash"], password):
            raise AccountError(403, "Неверный текущий пароль")

    # ------------------------------------------------------------ регистрация и вход

    def register(self, email: Any, password: Any, ip: str) -> tuple[User, str]:
        """Новый аккаунт и сразу вход; `(пользователь, токен cookie)`."""
        lim = self.settings.limits
        key = f"register:{ip}"
        if self.limits.count(key, lim.register_window_s) >= lim.register_per_ip:
            raise AccountError(429, "Слишком много регистраций с вашего адреса — "
                                    "попробуйте через час")
        email = normalize_email(email)
        password = self.check_password_rules(password)
        if self.db.one("SELECT 1 FROM users WHERE email = ?", (email,)):
            raise AccountError(409, "Эта почта уже зарегистрирована — войдите")
        password_hash = self.hasher.hash(password)
        try:
            cur = self.db.run("INSERT INTO users (email, password_hash, created) VALUES (?, ?, ?)",
                              (email, password_hash, self.clock()))
        except sqlite3.IntegrityError as e:
            raise AccountError(409, "Эта почта уже зарегистрирована — войдите") from e
        self.limits.add(key, lim.register_window_s)
        user_id = int(cur.lastrowid or 0)
        return self.open_session(user_id)

    def login(self, email: Any, password: Any) -> tuple[User, str]:
        lim = self.settings.limits
        try:
            email = normalize_email(email)
        except AccountError:
            raise AccountError(401, "Неверная почта или пароль") from None
        key = f"login:{email}"
        left = self.limits.locked_for(key)
        if left > 0:
            raise AccountError(429, "Слишком много неверных попыток входа — попробуйте "
                                    f"через {_minutes(left)}")
        row = self.db.one("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        ok = isinstance(password, str) and self._verify(
            row["password_hash"] if row else self._dummy_hash, password)
        if row is None or not ok:
            if self.limits.add(key, lim.login_window_s) >= lim.login_failures:
                self.limits.lock(key, lim.login_lockout_s)
            raise AccountError(401, "Неверная почта или пароль")
        self.limits.reset(key)
        if self.hasher.check_needs_rehash(row["password_hash"]):
            self.db.run("UPDATE users SET password_hash = ? WHERE id = ?",
                        (self.hasher.hash(password), row["id"]))
        return self.open_session(int(row["id"]))

    # ------------------------------------------------------------ сессии

    def open_session(self, user_id: int) -> tuple[User, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = self.clock()
        expires = now + self.settings.accounts.session_days * 86400
        with self.db.tx() as c:
            c.execute("INSERT INTO sessions (token_hash, user_id, csrf, created, expires) "
                      "VALUES (?, ?, ?, ?, ?)", (_token_hash(token), user_id, csrf, now, expires))
            c.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))
        user = self.session(token)
        assert user is not None
        return user, token

    def session(self, token: str | None) -> User | None:
        """Пользователь по токену cookie; нет, истёк — `None`."""
        if not token or len(token) > 200:
            return None
        row = self.db.one(
            "SELECT u.id, u.email, u.role, s.csrf, s.expires FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (_token_hash(token),))
        if row is None:
            return None
        if row["expires"] <= self.clock():
            self.db.run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
            return None
        return User(id=int(row["id"]), email=row["email"], role=row["role"], csrf=row["csrf"],
                    token=token)

    def close_session(self, token: str) -> None:
        self.db.run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ------------------------------------------------------------ профиль

    def change_password(self, user: User, current: Any, new: Any) -> None:
        """Новый пароль после проверки текущего; остальные сессии пользователя закрываются."""
        self.verify_user_password(user.id, current)
        new = self.check_password_rules(new)
        with self.db.tx() as c:
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                      (self.hasher.hash(new), user.id))
            c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                      (user.id, _token_hash(user.token)))

    def delete_user(self, user_id: int) -> None:
        """Строки пользователя: аккаунт, сессии, реплеи (каскадом)."""
        with self.db.tx() as c:
            c.execute("DELETE FROM replays WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            c.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def user_ids(self) -> list[int]:
        return [int(r["id"]) for r in self.db.query("SELECT id FROM users ORDER BY id")]

    def exists(self, user_id: int) -> bool:
        return self.db.one("SELECT 1 FROM users WHERE id = ?", (user_id,)) is not None
