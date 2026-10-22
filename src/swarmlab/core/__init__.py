"""Ядро SwarmLab: цикл симуляции, часы, конфиг, RNG и контракты модулей.

Ядро не знает о конкретных модулях и физических движках: модули подключаются
через `Module` и `PhysicsBackend`.

Имена экспортируются лениво (PEP 562): процесс-раннер импортирует только
`swarmlab.core.protocol` и не должен платить за pydantic и NumPy при старте.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS = {
    "Clock": "clock",
    "Rates": "clock",
    "RealtimePacer": "clock",
    "ConfigError": "config",
    "MatchConfig": "config",
    "RunnerConfig": "config",
    "TimingConfig": "config",
    "deep_merge": "config",
    "load_match": "config",
    "DebugViewable": "module",
    "DebugViewer": "module",
    "Frame": "module",
    "Module": "module",
    "Replayable": "module",
    "ScoreBoard": "module",
    "TeamSpec": "module",
    "available_modules": "module",
    "load_module": "module",
    "STATIC": "physics",
    "ContactList": "physics",
    "PhysicsBackend": "physics",
    "AgentHost": "protocol",
    "AgentId": "protocol",
    "AgentLink": "protocol",
    "CommandBatch": "protocol",
    "SensorBatch": "protocol",
    "TeamId": "protocol",
    "Replay": "replay",
    "ReplayWriter": "replay",
    "read_replay": "replay",
    "RngRegistry": "rng",
    "RunnerPool": "runner_host",
    "RunnerStats": "runner_host",
    "RunStats": "sim",
    "Simulation": "sim",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    sub = _EXPORTS.get(name)
    if sub is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{sub}"), name)
