"""Контракт модуля-сценария и поиск модулей.

Модуль (пчёлки, карьер, город) реализует `Module`; ядро вызывает его из цикла
симуляции и ничего не знает о его предметной области. Модули регистрируются в
`pyproject.toml` в группе entry points `swarmlab.modules` и загружаются по имени
из конфига матча — ядро их не импортирует.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

from swarmlab.core.protocol import CommandBatch, SensorBatch, TeamId

if TYPE_CHECKING:
    from swarmlab.core.config import MatchConfig
    from swarmlab.core.physics import PhysicsBackend
    from swarmlab.core.rng import RngRegistry

#: Группа entry points, в которой модули объявляют свой класс.
ENTRY_POINT_GROUP = "swarmlab.modules"


@dataclass(frozen=True)
class TeamSpec:
    """Команда, управляемая кодом игрока: для неё ядро запускает раннер."""

    team: TeamId
    name: str
    script: Path | None = None
    color: str | None = None


@dataclass
class Frame:
    """Снимок состояния для реплея и стрима.

    `arrays` — именованные массивы состояния (позиции, флаги…), `events` —
    события, произошедшие с прошлого кадра. Состав полей определяет модуль.
    """

    tick: int
    time: float
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScoreBoard:
    """Счёт матча: метрики по командам и победитель (если определён)."""

    teams: dict[TeamId, dict[str, float]] = field(default_factory=dict)
    winner: TeamId | None = None


@runtime_checkable
class Module(Protocol):
    """Модуль-сценарий. Порядок вызовов ядром:

    `build` → `physics` → `agent_teams`; затем на каждом шаге физики:
    [`decide` → `collect_sensors`/`apply_commands` — на тиках решений]
    → `pre_physics` → шаг физики → `post_physics` → [`snapshot` — на кадрах].
    """

    name: str

    def build(self, cfg: MatchConfig, rng: RngRegistry) -> None:
        """Построить мир, тела и команды по конфигу. Вся случайность — из `rng`."""
        ...

    def physics(self) -> PhysicsBackend:
        """Физический бэкенд, собранный в `build`."""
        ...

    def agent_teams(self) -> list[TeamSpec]:
        """Команды с кодом игрока — для каждой ядро запустит раннер."""
        ...

    def decide(self, tick: int) -> None:
        """Тик решений для доверенных агентов внутри процесса симуляции.

        Встроенные боты (враги), демо-скрипты, простые автоматы. Код игрока сюда
        не попадает — он живёт только в раннере.
        """
        ...

    def collect_sensors(self, team: TeamId) -> SensorBatch:
        """Сенсоры команды на текущий тик решений."""
        ...

    def apply_commands(self, team: TeamId, cmds: CommandBatch) -> None:
        """Применить решения команды; действуют до следующего тика решений."""
        ...

    def pre_physics(self, dt: float) -> None:
        """Перед шагом физики: силы, автопилот — векторно по всем телам."""
        ...

    def post_physics(self, dt: float) -> None:
        """После шага физики: энергия, контакты, экономика, события."""
        ...

    def snapshot(self) -> Frame:
        """Кадр для реплея и стрима."""
        ...

    def score(self) -> ScoreBoard:
        """Текущий счёт."""
        ...

    def is_finished(self) -> bool:
        """Матч закончился по правилам модуля (помимо истечения `duration_s`)."""
        ...


@runtime_checkable
class DebugViewer(Protocol):
    """Отладочное окно движка (например, MuJoCo-вьюер), работающее в процессе симуляции."""

    def is_running(self) -> bool:
        """Окно ещё открыто."""
        ...

    def sync(self) -> None:
        """Перерисовать окно по текущему состоянию физики."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class DebugViewable(Protocol):
    """Необязательная возможность модуля: открыть отладочное окно своего движка."""

    def open_debug_viewer(self) -> DebugViewer: ...


def available_modules() -> list[str]:
    """Имена установленных модулей."""
    return sorted(ep.name for ep in entry_points(group=ENTRY_POINT_GROUP))


def load_module(name: str) -> Module:
    """Создать экземпляр модуля по имени из entry points `swarmlab.modules`."""
    matches = [ep for ep in entry_points(group=ENTRY_POINT_GROUP) if ep.name == name]
    if not matches:
        known = ", ".join(available_modules()) or "нет ни одного"
        raise LookupError(f"Модуль {name!r} не найден. Установленные модули: {known}")
    cls = matches[0].load()
    module = cls()
    if not isinstance(module, Module):
        raise TypeError(f"{cls!r} не реализует контракт Module")
    return module
