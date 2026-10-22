"""Процесс-раннер: рукопожатие, цикл «сенсоры → команды», перехват вывода игрока.

Жизненный цикл (ARCHITECTURE §3.4):

1. Раннер забирает себе бинарные stdin/stdout — это канал протокола. `sys.stdout`
   подменяется буфером: `print` игрока уходит в `CommandBatch.log`, а не в канал;
   `sys.stdin` — пустой, `input()` не съест кадры ядра.
2. Ждёт `hello`, находит хост модуля по entry point `swarmlab.agent_hosts`,
   задаёт seed модуля `random` (детерминизм скриптов), хост загружает скрипт.
   Ответ `ready` (`ok: false` и трассировка, если скрипт не загрузился).
3. На каждый `sensors` отвечает `commands`. Время кода игрока меряет хост.
4. `stop` — выход. Ядро закрыло канал (EOF) — выход, даже если код игрока
   завис в `while True`: поток-читатель завершает процесс через `os._exit`.
"""

from __future__ import annotations

import io
import os
import queue
import random
import sys
import threading
import time
import traceback
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

from swarmlab.core.protocol import (
    PROTOCOL_VERSION,
    AgentHost,
    CommandBatch,
    ProtocolError,
    SensorBatch,
    read_frame,
    write_frame,
)

#: Группа entry points: имя модуля → класс хоста (`AgentHost`).
HOSTS_GROUP = "swarmlab.agent_hosts"
#: После закрытия канала ядром — столько секунд на нормальный выход, потом `os._exit`.
_EOF_GRACE_S = 1.0
#: Ограничения вывода игрока за один тик.
_MAX_LINES_PER_TICK = 200
_MAX_LINE_CHARS = 500


class OutputCapture(io.TextIOBase):
    """Замена `sys.stdout`: строки вывода копятся до конца тика."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._partial = ""
        self._dropped = 0

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        data = self._partial + str(text)
        *lines, self._partial = data.split("\n")
        for line in lines:
            self.add(line)
        return len(text)

    def add(self, line: str) -> None:
        if len(self._lines) >= _MAX_LINES_PER_TICK:
            self._dropped += 1
            return
        if len(line) > _MAX_LINE_CHARS:
            line = line[:_MAX_LINE_CHARS] + "…"
        self._lines.append(line)

    def drain(self) -> list[str]:
        """Забрать накопленные строки (недописанная строка тоже уходит)."""
        if self._partial:
            self.add(self._partial)
            self._partial = ""
        out, self._lines = self._lines, []
        if self._dropped:
            out.append(f"… вывод обрезан: ещё {self._dropped} строк за этот тик")
            self._dropped = 0
        return out


def load_host(module: str, log: Callable[[str], None]) -> AgentHost:
    """Хост модуля по имени; конструктор хоста принимает функцию записи в лог."""
    found = [ep for ep in entry_points(group=HOSTS_GROUP) if ep.name == module]
    if not found:
        raise LookupError(f"Нет хоста раннера для модуля {module!r} ({HOSTS_GROUP})")
    return found[0].load()(log=log)


def _stdin_reader(stream: Any, inbox: queue.Queue[dict[str, Any] | None]) -> None:
    """Кадры ядра → очередь. EOF или битый канал → выход процесса."""
    try:
        while True:
            msg = read_frame(stream)
            if msg is None:
                break
            inbox.put(msg)
    except (OSError, ValueError, ProtocolError):
        pass
    inbox.put(None)
    time.sleep(_EOF_GRACE_S)
    os._exit(0)  # главный поток мог зависнуть в коде игрока


def main() -> int:
    channel_in = sys.stdin.buffer
    channel_out = sys.stdout.buffer
    capture = OutputCapture()
    sys.stdout = capture
    sys.stdin = io.StringIO("")

    inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
    threading.Thread(target=_stdin_reader, args=(channel_in, inbox), daemon=True).start()

    hello = inbox.get()
    if hello is None or hello.get("t") != "hello":
        return 1
    ready: dict[str, Any] = {"t": "ready", "v": PROTOCOL_VERSION, "ok": False}
    host: AgentHost | None = None
    try:
        if hello.get("v") != PROTOCOL_VERSION:
            raise ProtocolError(
                f"версия протокола ядра {hello.get('v')}, раннера {PROTOCOL_VERSION}"
            )
        random.seed(int(hello.get("seed", 0)) * 1000 + int(hello.get("team", 0)))
        host = load_host(str(hello["module"]), capture.add)
        ready.update(host.load(hello))
        ready["ok"] = True
    except Exception as e:
        ready["error"] = getattr(e, "player_message", None) or traceback.format_exc()
    ready["log"] = capture.drain()
    write_frame(channel_out, ready)
    if host is None or not ready["ok"]:
        return 0

    while True:
        msg = inbox.get()
        if msg is None or msg.get("t") == "stop":
            return 0
        if msg.get("t") != "sensors":
            continue
        batch = SensorBatch.from_message(msg)
        try:
            reply = host.step(batch)
        except Exception:  # ошибка вне кода отдельной пчелы: тик без команд
            reply = CommandBatch(tick=batch.tick, log=[traceback.format_exc()])
        reply.log = capture.drain() + reply.log
        write_frame(channel_out, reply.to_message())
