"""Сообщения между ядром и раннером кода игрока («пакет сенсоров → пакет команд»).

Протокол один для всех `AgentLink` (процесс, контейнер, робот) и всех модулей,
поэтому содержимое сенсоров и команд — простые структуры (dict/list/числа/строки),
которые сериализуются в msgpack без pickle. Форму `agents[i]`, `team_view`,
`commands[id]` и `team_command` определяет модуль (для пчёлок — BEES_SPEC §3.3, §5).

Транспорт: кадр = 4 байта длины (uint32, little-endian) + msgpack. Каждое
сообщение — словарь с типом `"t"` (ARCHITECTURE §3.3):

| Направление   | `t`        | Поля |
|---------------|------------|------|
| ядро → раннер | `hello`    | `v, module, team, script, seed, budget_ms, options` |
| раннер → ядро | `ready`    | `v, ok, classes, hive_step, error, log` |
| ядро → раннер | `sensors`  | SensorBatch: `tick, team, budget_ms, team_view, agents` |
| раннер → ядро | `commands` | CommandBatch: `tick, commands, team_command, cpu_ms, errors, log` |
| ядро → раннер | `stop`     | — |
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Protocol, runtime_checkable

import msgpack

#: Версия протокола раннера.
PROTOCOL_VERSION = 1
#: Предел размера кадра: защита от мусора в канале.
MAX_FRAME_BYTES = 16 * 1024 * 1024
_HEADER = struct.Struct("<I")

#: Идентификатор команды (улья, бригады, оператора).
TeamId = int
#: Идентификатор агента внутри матча.
AgentId = int


class ProtocolError(RuntimeError):
    """Нарушение протокола: битый кадр, неизвестный тип, слишком длинное сообщение."""


@dataclass
class SensorBatch:
    """Ядро → раннер: всё, что команда знает на тике `tick`.

    `team_view` — сенсоры уровня команды (для пчёлок — улей), `agents` — по записи
    на каждого агента команды, `budget_ms` — бюджет времени команды на этот тик.
    """

    tick: int
    team: TeamId
    budget_ms: float
    team_view: dict[str, Any] = field(default_factory=dict)
    agents: list[dict[str, Any]] = field(default_factory=list)

    def to_message(self) -> dict[str, Any]:
        return {
            "t": "sensors",
            "tick": self.tick,
            "team": self.team,
            "budget_ms": self.budget_ms,
            "team_view": self.team_view,
            "agents": self.agents,
        }

    @classmethod
    def from_message(cls, msg: dict[str, Any]) -> SensorBatch:
        return cls(
            tick=int(msg["tick"]),
            team=int(msg["team"]),
            budget_ms=float(msg["budget_ms"]),
            team_view=msg.get("team_view") or {},
            agents=msg.get("agents") or [],
        )


@dataclass
class CommandBatch:
    """Раннер → ядро: решения команды на тике `tick`.

    `commands` — команда для каждого агента, который что-то решил (остальные
    продолжают прошлую команду); `team_command` — решение уровня команды (для
    пчёлок — `hive_step`); `cpu_ms` — время кода игрока на этот тик, мс; `errors` —
    агенты, у которых код упал с исключением; `log` — вывод `print` и трассировки.
    """

    tick: int
    commands: dict[AgentId, dict[str, Any]] = field(default_factory=dict)
    team_command: dict[str, Any] | None = None
    cpu_ms: float = 0.0
    errors: list[AgentId] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def to_message(self) -> dict[str, Any]:
        return {
            "t": "commands",
            "tick": self.tick,
            "commands": self.commands,
            "team_command": self.team_command,
            "cpu_ms": self.cpu_ms,
            "errors": self.errors,
            "log": self.log,
        }

    @classmethod
    def from_message(cls, msg: dict[str, Any]) -> CommandBatch:
        commands = msg.get("commands") or {}
        if not isinstance(commands, dict):
            raise ProtocolError("commands: ожидался словарь agent_id → команда")
        return cls(
            tick=int(msg["tick"]),
            commands={int(k): v for k, v in commands.items() if isinstance(v, dict)},
            team_command=msg.get("team_command"),
            cpu_ms=float(msg.get("cpu_ms", 0.0)),
            errors=[int(e) for e in msg.get("errors") or []],
            log=[str(s) for s in msg.get("log") or []],
        )


# --------------------------------------------------------------- кадры


def encode(msg: dict[str, Any]) -> bytes:
    """Сообщение → кадр (длина + msgpack)."""
    body = msgpack.packb(msg, use_bin_type=True)
    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError(f"Сообщение {len(body)} байт больше предела {MAX_FRAME_BYTES}")
    return _HEADER.pack(len(body)) + body


def decode(body: bytes) -> dict[str, Any]:
    """Тело кадра → сообщение-словарь с полем `t`."""
    try:
        msg = msgpack.unpackb(body, raw=False, strict_map_key=False)
    except Exception as e:  # msgpack бросает разные исключения на мусор
        raise ProtocolError(f"Битый кадр msgpack: {e}") from e
    if not isinstance(msg, dict) or not isinstance(msg.get("t"), str):
        raise ProtocolError("Сообщение должно быть словарём с полем 't'")
    return msg


def write_frame(stream: BinaryIO, msg: dict[str, Any]) -> None:
    """Записать сообщение в поток и сбросить буфер."""
    stream.write(encode(msg))
    stream.flush()


def _read_exact(stream: BinaryIO, n: int) -> bytes | None:
    """Прочитать ровно `n` байт; `None` — поток закрыт до начала чтения."""
    chunks = []
    got = 0
    while got < n:
        chunk = stream.read(n - got)
        if not chunk:
            if got == 0:
                return None
            raise ProtocolError(f"Поток оборвался посреди кадра ({got} из {n} байт)")
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> dict[str, Any] | None:
    """Прочитать одно сообщение; `None` — поток закрыт (EOF между кадрами)."""
    header = _read_exact(stream, _HEADER.size)
    if header is None:
        return None
    (length,) = _HEADER.unpack(header)
    if length > MAX_FRAME_BYTES:
        raise ProtocolError(f"Кадр {length} байт больше предела {MAX_FRAME_BYTES}")
    body = _read_exact(stream, length)
    if body is None:
        raise ProtocolError("Поток оборвался после заголовка кадра")
    return decode(body)


# --------------------------------------------------------------- контракты


@runtime_checkable
class AgentLink(Protocol):
    """Канал «команда ↔ код игрока» (процесс, позже контейнер или робот).

    Ядро сначала отправляет пакеты всем каналам (`send`), потом собирает ответы
    (`receive`) с общим дедлайном — каналы работают параллельно.
    """

    @property
    def team(self) -> TeamId: ...

    def start(self) -> None:
        """Запустить исполнитель и отправить `hello` (без ожидания ответа)."""
        ...

    def wait_ready(self, deadline: float) -> bool:
        """Дождаться `ready` до момента `deadline` (часы `time.monotonic`)."""
        ...

    def send(self, batch: SensorBatch) -> bool:
        """Отправить пакет сенсоров; `False` — канал занят или не готов, тик пропущен."""
        ...

    def receive(self, tick: int, deadline: float) -> CommandBatch | None:
        """Ответ на тик `tick` до момента `deadline`; `None` — ответа нет."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class AgentHost(Protocol):
    """Сторона модуля внутри процесса-раннера: загружает код игрока и вызывает его.

    Хост находится по имени модуля в entry points `swarmlab.agent_hosts` и
    работает только в раннере — ядро его не импортирует. Конструктор принимает
    `log: Callable[[str], None]` — запись строки в лог игрока.
    """

    def load(self, hello: dict[str, Any]) -> dict[str, Any]:
        """Загрузить скрипт игрока; вернуть поля ответа `ready` (`classes`, `hive_step`)."""
        ...

    def step(self, batch: SensorBatch) -> CommandBatch:
        """Один тик решений: вызвать код игрока, собрать команды.

        Хост сам ловит исключения в коде отдельных агентов и пишет их в `log`, и
        сам меряет `cpu_ms` — время, проведённое в коде игрока (`time.perf_counter`,
        DECISIONS №32), без разбора сенсоров и сборки команд.
        """
        ...
