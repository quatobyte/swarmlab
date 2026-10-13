"""Ядро SwarmLab: цикл симуляции, часы, конфиг, RNG и контракты модулей.

Ядро не знает о конкретных модулях и физических движках: модули подключаются
через `Module` и `PhysicsBackend`.
"""

from swarmlab.core.clock import Clock, Rates, RealtimePacer
from swarmlab.core.config import ConfigError, MatchConfig, TimingConfig, deep_merge, load_match
from swarmlab.core.module import (
    DebugViewable,
    DebugViewer,
    Frame,
    Module,
    ScoreBoard,
    TeamSpec,
    available_modules,
    load_module,
)
from swarmlab.core.physics import STATIC, ContactList, PhysicsBackend
from swarmlab.core.protocol import AgentId, CommandBatch, SensorBatch, TeamId
from swarmlab.core.rng import RngRegistry
from swarmlab.core.sim import RunStats, Simulation

__all__ = [
    "STATIC",
    "AgentId",
    "Clock",
    "CommandBatch",
    "ConfigError",
    "ContactList",
    "DebugViewable",
    "DebugViewer",
    "Frame",
    "MatchConfig",
    "Module",
    "PhysicsBackend",
    "Rates",
    "RealtimePacer",
    "RngRegistry",
    "RunStats",
    "ScoreBoard",
    "SensorBatch",
    "Simulation",
    "TeamId",
    "TeamSpec",
    "TimingConfig",
    "available_modules",
    "deep_merge",
    "load_match",
    "load_module",
]
