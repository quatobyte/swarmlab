"""Сообщения между ядром и раннером кода игрока («пакет сенсоров → пакет команд»).

Протокол один для всех `AgentLink` (процесс, контейнер, робот) и всех модулей,
поэтому содержимое сенсоров и команд — простые структуры (dict/list/числа),
которые сериализуются в msgpack без pickle. Форму `agents[i]` и `commands[id]`
определяет модуль (для пчёлок — BEES_SPEC §3.3, §5.1).

Транспорт (кадр = 4 байта длины + msgpack) появится в вехе M2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Идентификатор команды (улья, бригады, оператора).
TeamId = int
#: Идентификатор агента внутри матча.
AgentId = int


@dataclass
class SensorBatch:
    """Ядро → раннер: всё, что команда знает на тике `tick`.

    `team_view` — сенсоры уровня команды (для пчёлок — улей), `agents` — по записи
    на каждого агента команды, `budget_ms` — CPU-бюджет команды на этот тик.
    """

    tick: int
    team: TeamId
    budget_ms: float
    team_view: dict[str, Any] = field(default_factory=dict)
    agents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommandBatch:
    """Раннер → ядро: решения команды на тике `tick`.

    `commands` — команда для каждого агента, `team_command` — решение уровня
    команды (для пчёлок — `hive_step`), `cpu_ms` — израсходованное CPU-время.
    """

    tick: int
    commands: dict[AgentId, dict[str, Any]] = field(default_factory=dict)
    team_command: dict[str, Any] | None = None
    cpu_ms: float = 0.0
