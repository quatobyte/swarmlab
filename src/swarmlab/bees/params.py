"""Схема параметров модуля пчёлок (валидация слитого конфига `MatchConfig.params`).

Значения по умолчанию живут в `configs/bees/defaults.yaml`, здесь — только типы и
ограничения.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FlyingKind = Literal["scout", "forager", "guard"]
FLYING_KINDS: tuple[FlyingKind, ...] = ("scout", "forager", "guard")
#: Все типы пчёл, включая домашнюю (без тела).
BeeKind = Literal["scout", "forager", "guard", "house"]
BEE_KINDS: tuple[BeeKind, ...] = ("scout", "forager", "guard", "house")
WeatherKind = Literal["clear", "windy", "rain"]

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
    # Выведены из целей скриптом tools/calibrate.py.
    drag_coef: float = Field(gt=0)
    energy_max: float = Field(gt=0)
    power_idle: float = Field(ge=0)
    power_coef: float = Field(ge=0)


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
    rain_force_coef: float = Field(ge=0)
    rain_drag_multiplier: float = Field(ge=0)
    wall_stiffness: float = Field(ge=0)
    bee_solref: tuple[float, float]
    parking_depth: float = Field(gt=0)


class WindParams(_Strict):
    height_ref: float = Field(gt=0)
    shear_exponent: float = Field(ge=0)
    min_agl: float = Field(gt=0)
    gust_harmonics: int = Field(ge=0)
    gust_amplitude: float = Field(ge=0)
    gust_period_s: Range
    gust_wavelength: Range
    turn_rate_deg_s: float = Field(ge=0)


class EnergyParams(_Strict):
    dead_on_ground: bool
    ground_contact_margin: float = Field(ge=0)


class WeatherStateParams(_Strict):
    wind: Range
    rain: bool


class WeatherParams(_Strict):
    enabled: bool
    wind: bool = True
    rain: bool = True
    initial: WeatherKind
    mean_duration_s: float = Field(gt=0)
    states: dict[WeatherKind, WeatherStateParams]


class HornetParams(_Strict):
    """Шершни (BEES_SPEC §7.1, DECISIONS №37–38)."""

    enabled: bool
    attack: bool = True
    rob: bool = True
    heat_ball: bool = True
    max: int = Field(ge=0)
    radius: float = Field(gt=0)
    mass: float = Field(gt=0)
    cruise_speed: float = Field(gt=0)
    thrust_max: float = Field(gt=0)
    view_radius: float = Field(gt=0)
    hp: float = Field(gt=0)
    first_wave_s: float = Field(ge=0)
    wave_interval_s: float = Field(gt=0)
    wave_growth_s: float = Field(gt=0)
    spawn_agl: float = Field(gt=0)
    target_max_allies: int = Field(ge=0)
    target_ally_radius: float = Field(ge=0)
    kill_contact_s: float = Field(gt=0)
    touch_margin: float = Field(ge=0)
    rob_radius: float = Field(ge=0)
    rob_guard_radius: float = Field(ge=0)
    rob_rate: float = Field(ge=0)
    heat_ball_min_guards: int = Field(ge=1)
    heat_ball_distance: float = Field(ge=0)
    heat_ball_dps: float = Field(ge=0)
    flee_hp: float = Field(ge=0)
    leave_margin: float = Field(ge=0)

    @model_validator(mode="after")
    def _can_fly(self) -> HornetParams:
        if self.thrust_max <= self.mass * 9.81:
            raise ValueError("enemies.hornets.thrust_max: тяга меньше веса — шершень не взлетит")
        return self


class SpiderParams(_Strict):
    """Пауки (BEES_SPEC §7.2)."""

    enabled: bool
    flower_fraction: float = Field(ge=0, le=1)
    kill_prob_per_s: float = Field(ge=0, le=1)


class EnemiesParams(_Strict):
    hornets: HornetParams
    spiders: SpiderParams


class SensorParams(_Strict):
    rain_view_multiplier: float = Field(gt=0)
    noise_pos_sigma: float = Field(ge=0)
    noise_vel_sigma: float = Field(ge=0)
    spider_visible_radius: float = Field(ge=0)
    grid_cell: float = Field(gt=0)


class CommsParams(_Strict):
    radius: float = Field(gt=0)
    max_values: int = Field(ge=1)


class PheromoneParams(_Strict):
    cell: float = Field(gt=0)
    channels: int = Field(ge=1)
    half_life_s: float = Field(gt=0)
    neighborhood: Literal[3]


class AutopilotParams(_Strict):
    kp: float = Field(gt=0)
    kd: float = Field(gt=0)
    default_agl: float = Field(ge=0)
    min_clearance: float = Field(ge=0)
    arrive_radius: float = Field(gt=0)
    avoid_obstacles: bool
    avoid_gain: float = Field(ge=0)
    avoid_margin: float = Field(gt=0)
    terrain_lookahead_s: float = Field(ge=0)
    separation: bool
    separation_gain: float = Field(ge=0)
    separation_margin: float = Field(gt=0)


class CollectParams(_Strict):
    rate: float = Field(ge=0)
    max_horizontal: float = Field(gt=0)
    max_height: float = Field(gt=0)
    max_speed: float = Field(gt=0)


class ProcessingParams(_Strict):
    k_proc: float = Field(ge=0)
    honey_per_nectar: float = Field(ge=0)


class FeedingParams(_Strict):
    joules_per_honey: float = Field(gt=0)
    refuel_rate: float = Field(ge=0)
    house_consumption: float = Field(ge=0)


class BreedParams(_Strict):
    cost: float = Field(ge=0)
    time_s: float = Field(gt=0)


class EconomyParams(_Strict):
    """Экономика улья (BEES_SPEC §4)."""

    start_honey: float = Field(ge=0)
    start_nectar: float = Field(ge=0)
    start_bees: dict[BeeKind, int]
    collect: CollectParams
    processing: ProcessingParams
    feeding: FeedingParams
    breeding: dict[BeeKind, BreedParams]

    @model_validator(mode="after")
    def _all_kinds(self) -> EconomyParams:
        missing = set(BEE_KINDS) - set(self.breeding)
        if missing:
            raise ValueError(f"economy.breeding: нет типов {sorted(missing)}")
        if any(n < 0 for n in self.start_bees.values()):
            raise ValueError("economy.start_bees: число пчёл не может быть отрицательным")
        return self


class HiveTrafficParams(_Strict):
    """Вход в улей и вылет (уточнение BEES_SPEC §3.3)."""

    enter_radius: float = Field(gt=0)
    exit_per_tick: int = Field(ge=1)
    approach_margin: float = Field(gt=0)


class ProgramParams(_Strict):
    """Ожидание команд в `step()` с `yield` (BEES_SPEC §3.1, DECISIONS №57, №61)."""

    arrive_tolerance: float = Field(gt=0)
    arrive_max_speed: float = Field(gt=0)
    command_timeout_s: float = Field(gt=0)


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


class DemoSwarm(_Strict):
    """Демо-рой M1: пчёлы каждого улья летают по случайным точкам карты."""

    per_hive: dict[FlyingKind, int]
    agl: Range = (3.0, 15.0)  # высота точек над рельефом, м
    edge_margin: float = Field(10.0, ge=0)  # точки не ближе к краю карты, м
    arrive_radius: float = Field(2.0, gt=0)  # «долетела» для бота, м
    dwell_s: float = Field(0.0, ge=0)
    retarget_s: float = Field(120.0, gt=0)  # не долетела за это время — новая точка

    @model_validator(mode="after")
    def _range(self) -> DemoSwarm:
        _check_range(self.agl, "agl")
        return self


class DemoParams(_Strict):
    bees: list[DemoBee] = Field(default_factory=list)
    swarm: DemoSwarm | None = None


class BeesParams(_Strict):
    """Все параметры модуля пчёлок после слияния слоёв конфига."""

    world: WorldParams
    bee_types: BeeTypes
    physics: PhysicsParams
    autopilot: AutopilotParams
    pool: PoolParams
    wind: WindParams
    energy: EnergyParams
    economy: EconomyParams
    hive: HiveTrafficParams
    program: ProgramParams
    sensors: SensorParams
    comms: CommsParams
    pheromones: PheromoneParams
    weather: WeatherParams
    enemies: EnemiesParams
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
        start = sum(self.economy.start_bees.values())
        if any(h.script for h in self.hives) and start > self.pool.max_bees_per_hive:
            raise ValueError(
                f"economy.start_bees: {start} пчёл, а лимит улья — "
                f"{self.pool.max_bees_per_hive} (pool.max_bees_per_hive)"
            )
        per_hive = [0] * n
        for bee in self.demo.bees:
            per_hive[bee.hive] += 1
        if self.demo.swarm is not None:
            per_hive = [c + sum(self.demo.swarm.per_hive.values()) for c in per_hive]
        if max(per_hive) > self.pool.max_bees_per_hive:
            raise ValueError(
                f"демо-пчёл в улье {max(per_hive)}, а пул улья — "
                f"{self.pool.max_bees_per_hive} (pool.max_bees_per_hive)"
            )
        missing = {"clear", "windy", "rain"} - set(self.weather.states)
        if missing:
            raise ValueError(f"weather.states: нет состояний {sorted(missing)}")
        return self
