"""Схема параметров модуля пчёлок (валидация слитого конфига `MatchConfig.params`).

Значения по умолчанию живут в `configs/bees/defaults.yaml`, здесь — только типы и
ограничения. Разделы, которые ещё не реализованы (ветер, энергия, экономика,
враги…), пока принимаются словарями и получат строгие схемы в своих вехах.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FlyingKind = Literal["scout", "forager", "guard"]
FLYING_KINDS: tuple[FlyingKind, ...] = ("scout", "forager", "guard")

Range = tuple[float, float]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_range(r: Range, name: str) -> None:
    if r[0] > r[1]:
        raise ValueError(f"{name}: нижняя граница {r[0]} больше верхней {r[1]}")


class TerrainParams(_Strict):
    grid: int = Field(ge=4)
    max_relief: float = Field(ge=0)
    octaves: int = Field(ge=1)
    base_cells: int = Field(ge=1)
    persistence: float = Field(gt=0)
    base_thickness: float = Field(gt=0)


class TreeParams(_Strict):
    per_ha: float = Field(ge=0)
    trunk_radius: Range
    trunk_height: Range
    crown_radius: Range
    hive_clearance: float = Field(ge=0)
    edge_margin: float = Field(ge=0)

    @model_validator(mode="after")
    def _ranges(self) -> TreeParams:
        for name in ("trunk_radius", "trunk_height", "crown_radius"):
            _check_range(getattr(self, name), name)
        return self


class RockParams(_Strict):
    per_ha: float = Field(ge=0)
    half_size: Range
    hive_clearance: float = Field(ge=0)
    edge_margin: float = Field(ge=0)


class HiveGeomParams(_Strict):
    spacing: float = Field(gt=0)
    half_size: tuple[float, float]
    height: float = Field(gt=0)
    entrance_offset: float = Field(ge=0)
    entrance_height: float = Field(ge=0)


class FlowerParams(_Strict):
    clusters_per_hive: int = Field(ge=0)
    flowers_per_cluster: int = Field(ge=0)
    cluster_radius: float = Field(ge=0)
    cluster_distance: Range
    edge_margin: float = Field(ge=0)
    height: float = Field(ge=0)
    nectar_max: float = Field(ge=0)
    regen_per_s: float = Field(ge=0)


class WorldParams(_Strict):
    map_size: float = Field(gt=0)
    ceiling_agl: float = Field(gt=0)
    n_hives: int = Field(ge=1, le=3)
    terrain: TerrainParams
    trees: TreeParams
    rocks: RockParams
    hives: HiveGeomParams
    flowers: FlowerParams


class BeeTypeParams(_Strict):
    radius: float = Field(gt=0)
    mass: float = Field(gt=0)
    cargo_max: float = Field(ge=0)
    thrust_max: float = Field(gt=0)
    cruise_speed: float = Field(gt=0)
    view_radius: float = Field(gt=0)
    flight_time_s: float = Field(gt=0)
    drag_coef: float | None = None
    energy_max: float | None = None
    power_idle: float | None = None
    power_coef: float | None = None


class BeeTypes(_Strict):
    scout: BeeTypeParams
    forager: BeeTypeParams
    guard: BeeTypeParams

    def of(self, kind: FlyingKind) -> BeeTypeParams:
        return getattr(self, kind)


class PhysicsParams(_Strict):
    gravity: float = Field(gt=0)
    angular_damping: float = Field(ge=0)
    cargo_unit_mass: float = Field(ge=0)
    rain_force_coef: float | None = None
    rain_drag_multiplier: float = Field(ge=0)
    wall_stiffness: float = Field(ge=0)


class AutopilotParams(_Strict):
    kp: float = Field(gt=0)
    kd: float = Field(gt=0)
    default_agl: float = Field(ge=0)
    min_clearance: float = Field(ge=0)
    arrive_radius: float = Field(gt=0)
    avoid_obstacles: bool
    avoid_gain: float = Field(ge=0)
    avoid_margin: float = Field(ge=0)


class PoolParams(_Strict):
    max_bees_per_hive: int = Field(ge=1)


class HiveEntry(_Strict):
    """Запись улья в матче: скрипт игрока и цвет команды."""

    script: str | None = None
    color: str | None = None


class DemoBee(_Strict):
    """Демо-пчела без раннера: облетает точки `[dx, dy, agl]` относительно летка своего улья."""

    kind: FlyingKind = "forager"
    hive: int = Field(0, ge=0)
    waypoints: list[tuple[float, float, float]] = Field(min_length=1)
    loop: bool = True
    dwell_s: float = Field(1.0, ge=0)


class DemoParams(_Strict):
    bees: list[DemoBee] = Field(default_factory=list)


class BeesParams(_Strict):
    """Все параметры модуля пчёлок после слияния слоёв конфига."""

    world: WorldParams
    bee_types: BeeTypes
    physics: PhysicsParams
    autopilot: AutopilotParams
    pool: PoolParams
    wind: dict[str, Any]
    energy: dict[str, Any]
    economy: dict[str, Any]
    sensors: dict[str, Any]
    comms: dict[str, Any]
    pheromones: dict[str, Any]
    weather: dict[str, Any]
    enemies: dict[str, Any]
    advanced_control: bool = False
    sensor_noise: bool = False
    hives: list[HiveEntry] = Field(default_factory=list)
    demo: DemoParams = DemoParams()

    @model_validator(mode="after")
    def _consistent(self) -> BeesParams:
        n = self.world.n_hives
        if self.hives and len(self.hives) != n:
            raise ValueError(
                f"hives: в матче {len(self.hives)} записей, а профиль задаёт {n} ульев"
            )
        for i, bee in enumerate(self.demo.bees):
            if bee.hive >= n:
                raise ValueError(f"demo.bees[{i}].hive = {bee.hive}, а ульев всего {n}")
        return self
