"""`BeesModule` — модуль «Swarm Logic» для ядра SwarmLab."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import ValidationError

from swarmlab.bees.autopilot import Autopilot
from swarmlab.bees.demo import WaypointPilot
from swarmlab.bees.params import FLYING_KINDS, BeesParams
from swarmlab.bees.physics.mjcf import DEFAULT_HIVE_COLORS, BodySlot, build_mjcf, hex_to_rgba
from swarmlab.bees.world import World, generate_world
from swarmlab.core.config import ConfigError, MatchConfig
from swarmlab.core.module import DebugViewer, Frame, ScoreBoard, TeamSpec
from swarmlab.core.physics import PhysicsBackend
from swarmlab.core.protocol import CommandBatch, SensorBatch, TeamId
from swarmlab.core.rng import RngRegistry

if TYPE_CHECKING:
    from swarmlab.bees.physics.backend import MujocoBackend


class BeesModule:
    """Пчёлки: мир по seed, MuJoCo-физика, векторный автопилот.

    Состояние пчёл — массивы по слотам тел (SoA); индекс слота = индекс тела в бэкенде.
    """

    name = "bees"

    def __init__(self) -> None:
        self.params: BeesParams
        self.world: World
        self.backend: MujocoBackend  # создаётся в build()
        self.autopilot: Autopilot
        self.pilot: WaypointPilot
        self.hive_colors: list[str] = []
        self.teams: list[TeamSpec] = []
        self._decision_dt = 0.1
        self._steps = 0
        self._dt = 0.0

    # --------------------------------------------------------------- построение

    def build(self, cfg: MatchConfig, rng: RngRegistry) -> None:
        # Импорт здесь: модуль пчёлок можно импортировать (схемы, мир) без MuJoCo.
        from swarmlab.bees.physics.backend import MujocoBackend

        try:
            p = BeesParams.model_validate(cfg.params)
        except ValidationError as e:
            raise ConfigError(f"{cfg.source}: неверные параметры модуля bees:\n{e}") from e
        self.params = p
        spiders = p.enemies.get("spiders", {})
        self.world = generate_world(
            p.world,
            rng,
            spiders_enabled=bool(spiders.get("enabled", False)),
            spider_fraction=float(spiders.get("flower_fraction", 0.0)),
        )
        self.hive_colors = [
            (p.hives[i].color if p.hives and p.hives[i].color else None)
            or DEFAULT_HIVE_COLORS[i % len(DEFAULT_HIVE_COLORS)]
            for i in range(self.world.n_hives)
        ]
        self.teams = [
            TeamSpec(team=i, name=f"hive{i}", script=Path(h.script), color=self.hive_colors[i])
            for i, h in enumerate(p.hives)
            if h.script
        ]

        slots, kinds, hives = self._demo_slots(p)
        self.kind = np.array([FLYING_KINDS.index(k) for k in kinds], dtype=np.int64)
        self.hive = np.array(hives, dtype=np.int64)
        types = [p.bee_types.of(k) for k in kinds]
        self.mass = np.array([t.mass for t in types])
        self.thrust_max = np.array([t.thrust_max for t in types])
        self.cruise_speed = np.array([t.cruise_speed for t in types])

        xml = build_mjcf(
            self.world,
            slots,
            timestep=1.0 / cfg.timing.physics_hz,
            gravity=p.physics.gravity,
            hive_colors=self.hive_colors,
        )
        self.backend = MujocoBackend(
            xml, [s.name for s in slots], angular_damping=p.physics.angular_damping
        )
        self._dt = self.backend.timestep
        self._decision_dt = 1.0 / cfg.timing.decision_hz
        self._all = np.arange(len(slots))

        self.autopilot = Autopilot(
            len(slots),
            p.autopilot,
            gravity=p.physics.gravity,
            ground=self.world.ground_height,
            map_half_size=self.world.half_size,
            ceiling_agl=self.world.ceiling_agl,
        )
        pos, _ = self.backend.poses()
        self.autopilot.hover(self._all, pos)
        self.pilot = WaypointPilot(self.autopilot, p.autopilot.arrive_radius)
        for i, bee in enumerate(p.demo.bees):
            origin = self.world.hive_entrance[bee.hive, :2]
            self.pilot.add(i, bee, origin, speed=float(self.cruise_speed[i]))

    def _demo_slots(self, p: BeesParams) -> tuple[list[BodySlot], list[str], list[int]]:
        """Слоты тел для демо-пчёл: стартуют у летка своего улья, по 1 м друг от друга."""
        slots: list[BodySlot] = []
        kinds: list[str] = []
        hives: list[int] = []
        per_hive: dict[int, int] = {}
        for i, bee in enumerate(p.demo.bees):
            t = p.bee_types.of(bee.kind)
            k = per_hive.get(bee.hive, 0)
            per_hive[bee.hive] = k + 1
            entrance = self.world.hive_entrance[bee.hive]
            xy = entrance[:2] + np.array([0.5 + t.radius, 1.0 * k])
            z = max(entrance[2], float(self.world.ground_height(xy)) + t.radius + 0.5)
            rgba = hex_to_rgba(self.hive_colors[bee.hive])
            slots.append(BodySlot(f"bee{i}", t.radius, t.mass, (xy[0], xy[1], z), rgba))
            kinds.append(bee.kind)
            hives.append(bee.hive)
        return slots, kinds, hives

    # --------------------------------------------------------------- Module

    def physics(self) -> PhysicsBackend:
        return self.backend

    def agent_teams(self) -> list[TeamSpec]:
        return list(self.teams)

    def decide(self, tick: int) -> None:
        pos, _ = self.backend.poses()
        vel = self.backend.velocities()[:, :3]
        self.pilot.decide(pos, vel, self._decision_dt)

    def collect_sensors(self, team: TeamId) -> SensorBatch:
        raise NotImplementedError("Сенсоры для раннера появятся в вехе M2")

    def apply_commands(self, team: TeamId, cmds: CommandBatch) -> None:
        raise NotImplementedError("Команды от раннера появятся в вехе M2")

    def pre_physics(self, dt: float) -> None:
        if not len(self._all):
            return
        pos, _ = self.backend.poses()
        vel = self.backend.velocities()[:, :3]
        thrust = self.autopilot.thrust(pos, vel, self.mass, self.thrust_max)
        self.backend.set_forces(self._all, thrust)

    def post_physics(self, dt: float) -> None:
        self._steps += 1

    def snapshot(self) -> Frame:
        pos, quat = self.backend.poses()
        return Frame(
            tick=self._steps,
            time=self._steps * self._dt,
            arrays={
                "pos": pos.copy(),
                "quat": quat.copy(),
                "vel": self.backend.velocities()[:, :3].copy(),
                "kind": self.kind.copy(),
                "hive": self.hive.copy(),
            },
        )

    def score(self) -> ScoreBoard:
        return ScoreBoard()  # счёт — веха M3

    def is_finished(self) -> bool:
        return False

    # --------------------------------------------------------------- DebugViewable

    def open_debug_viewer(self) -> DebugViewer:
        from swarmlab.bees.physics.viewer import MujocoDebugViewer

        return MujocoDebugViewer(self.backend, track_body=0 if len(self._all) else None)
