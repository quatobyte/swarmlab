"""`BeesModule` — модуль «Swarm Logic» для ядра SwarmLab."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import ValidationError

from swarmlab.bees.autopilot import Autopilot
from swarmlab.bees.comms import Delivery, MessageBoard
from swarmlab.bees.control import (
    ARRIVE,
    COLLECT,
    COLLECT_AT,
    COLLECTED,
    ENTER,
    FLY_TO,
    FOUND,
    GO_HOME,
    HOVER,
    REFUELED,
    SEARCH,
    WAIT_COND,
    Control,
    Parsed,
    parse,
)
from swarmlab.bees.demo import RandomWaypoints, WaypointPilot
from swarmlab.bees.economy import HiveEconomy
from swarmlab.bees.enemies import Enemies
from swarmlab.bees.params import FLYING_KINDS, BeeKind, BeesParams, FlyingKind
from swarmlab.bees.pheromones import PheromoneField
from swarmlab.bees.physics import forces
from swarmlab.bees.physics.mjcf import DEFAULT_HIVE_COLORS, BodySlot, build_mjcf, hex_to_rgba
from swarmlab.bees.sensors import AgentSensors, SensorBuilder, SensorInputs
from swarmlab.bees.state import FALLING, FLYING, FREE, IN_HIVE, STATE_NAMES, BeeState
from swarmlab.bees.weather import Weather
from swarmlab.bees.world import World, generate_world
from swarmlab.core.config import ConfigError, MatchConfig
from swarmlab.core.module import DebugViewer, Frame, ScoreBoard, ScoreColumn, TeamSpec
from swarmlab.core.physics import STATIC, PhysicsBackend
from swarmlab.core.program import DONE, FAILED, RUNNING
from swarmlab.core.protocol import CommandBatch, SensorBatch, TeamId
from swarmlab.core.rng import RngRegistry
from swarmlab.core.spatial import UniformGrid

if TYPE_CHECKING:
    from swarmlab.bees.physics.backend import MujocoBackend

#: Решётка точек появления перед летком: столько по y, столько по x, шаг, м.
_SPAWN_COLUMNS, _SPAWN_ROWS, _SPAWN_STEP = 5, 5, 1.0
#: Слоёв решётки для вылета из улья.
_EXIT_LAYERS = 2
#: `collect`: высота цели над цветком (автопилот всё равно держит просвет над рельефом), м.
_COLLECT_HOVER = 1.0
#: `from_id` сообщений улья (`Hive.say`).
HIVE_SENDER = -1
#: Запас рамки квантования позиций за краем карты и под нулём, м.
_POS_MARGIN = 10.0
_WEATHER_STATES = ("clear", "windy", "rain")
_U16 = 65535.0
#: Классы API по типам пчёл (для сообщений игроку).
_KIND_CLASS = {"scout": "Scout", "forager": "Collector", "house": "Worker"}
#: Причины гибели пчёл (`cause` события `death`), по которым ведётся счёт.
DEATH_CAUSES = ("energy", "spider")


class BeesModule:
    """Пчёлки: мир по seed, пул тел MuJoCo, силы, энергия, автопилот, сенсоры, улей.

    Состояние пчёл — массивы по слотам пула (`BeeState`, SoA); индекс слота = индекс
    тела в бэкенде. Горячий цикл (`pre_physics`/`post_physics`) — только векторные
    операции по массиву слотов в воздухе. Экономика, сбор нектара, вход в улей и
    вылет — на тике решений (10 Гц), тоже векторно.
    """

    name = "bees"

    def __init__(self) -> None:
        self.params: BeesParams
        self.world: World
        self.backend: MujocoBackend  # создаётся в build()
        self.autopilot: Autopilot
        self.bees: BeeState
        self.control: Control
        self.economy: HiveEconomy
        self.weather: Weather
        self.pilot: WaypointPilot
        self.swarm: RandomWaypoints | None = None
        self.hive_colors: list[str] = []
        self.teams: list[TeamSpec] = []
        self.events: list[dict[str, Any]] = []
        #: Отброшенные битые команды по ульям (защитная проверка, см. control.py).
        self.invalid_commands: list[int] = []
        self.deaths: dict[str, np.ndarray] = {}
        #: Сообщения игроку (отказ выведения…) — уходят в `team_view.notes` следующего тика.
        self._notes: list[list[str]] = []
        self._decision_dt = 0.1
        self._budget_ms = 20.0
        self._steps = 0
        self._dt = 0.0
        self._tick = 0
        self._economy_time = 0.0
        self._spawned = np.zeros(0, dtype=np.int64)

    # --------------------------------------------------------------- построение

    def build(self, cfg: MatchConfig, rng: RngRegistry) -> None:
        # Импорт здесь: модуль пчёлок можно импортировать (схемы, мир) без MuJoCo.
        from swarmlab.bees.physics.backend import MujocoBackend

        try:
            p = BeesParams.model_validate(cfg.params)
        except ValidationError as e:
            raise ConfigError(f"{cfg.source}: неверные параметры модуля bees:\n{e}") from e
        self.params = p
        spiders = p.enemies.spiders
        self.world = world = generate_world(
            p.world,
            rng,
            spiders_enabled=spiders.enabled,
            spider_fraction=spiders.flower_fraction,
        )
        self.hive_colors = [
            (p.hives[i].color if p.hives and p.hives[i].color else None)
            or DEFAULT_HIVE_COLORS[i % len(DEFAULT_HIVE_COLORS)]
            for i in range(world.n_hives)
        ]
        self.teams = [
            TeamSpec(
                team=i,
                name=f"hive{i}",
                script=_resolve_script(h.script, cfg.source),
                color=self.hive_colors[i],
                options={"max_word": p.comms.max_word, "max_say": p.comms.max_say},
            )
            for i, h in enumerate(p.hives)
            if h.script
        ]
        self.weather = Weather(p.weather, p.wind, rng.get("weather"), rng.get("weather.chain"))
        self.gravity = p.physics.gravity
        self._budget_ms = cfg.runner.budget_ms
        #: Случайный бак при рождении и точки `explore` (DECISIONS №86, №87).
        self._tank_rng = rng.get("bees.tank")
        self._explore_rng = rng.get("bees.explore")

        # Пул тел: max_bees_per_hive слотов на улей, все стартуют припаркованными.
        self.bees = bees = BeeState(
            world.n_hives, p.pool.max_bees_per_hive, p.bee_types, p.physics.cargo_unit_mass
        )
        self.control = Control(bees.n)
        self.economy = HiveEconomy(world.n_hives, p.economy, p.pool.max_bees_per_hive)
        #: Порог автовозврата и уровень заправки по ульям, % (команды улья, DECISIONS №86).
        self.home_energy = np.full(world.n_hives, p.energy.home_energy)
        self.refuel_energy = np.full(world.n_hives, p.energy.refuel_energy)
        self.invalid_commands = [0] * world.n_hives
        self._notes = [[] for _ in range(world.n_hives)]
        self._park_pos = self._parking_positions(bees.n)
        placeholder = p.bee_types.forager
        slots = [
            BodySlot(
                f"bee{i}",
                placeholder.radius,
                placeholder.mass,
                tuple(self._park_pos[i]),
                hex_to_rgba(self.hive_colors[int(bees.hive[i])]),
            )
            for i in range(bees.n)
        ]
        xml = build_mjcf(
            world,
            slots,
            timestep=1.0 / cfg.timing.physics_hz,
            gravity=p.physics.gravity,
            hive_colors=self.hive_colors,
            bee_solref=p.physics.bee_solref,
        )
        self.backend = MujocoBackend(
            xml, [s.name for s in slots], angular_damping=p.physics.angular_damping
        )
        self.backend.park(np.arange(len(slots)), self._park_pos)
        self._dt = self.backend.timestep
        self._decision_dt = 1.0 / cfg.timing.decision_hz

        self.obstacles = world.obstacles()
        self.autopilot = Autopilot(
            bees.n,
            p.autopilot,
            gravity=p.physics.gravity,
            ground=world.ground_height,
            map_half_size=world.half_size,
            ceiling_agl=world.ceiling_agl,
            obstacles=self.obstacles,
        )
        self.pheromones = PheromoneField(world.n_hives, world.map_size, p.pheromones)
        self.comms = MessageBoard(world.n_hives, p.comms.radius)
        self.sensors = SensorBuilder(
            p.sensors,
            world,
            bees,
            self.pheromones,
            self.obstacles,
            noise=rng.get("sensor_noise") if p.sensor_noise else None,
        )
        self.bee_grid = UniformGrid(world.half_size, p.sensors.grid_cell)
        self._delivery = Delivery.empty(world.n_hives)
        self._sensor_cache: dict[int, list[AgentSensors]] | None = None
        self._pairs_for: np.ndarray | None = None
        self._pairs_slots = (np.zeros(0, np.int64),) * 4
        self._local_pairs: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]
        self._local_pairs = ((np.zeros(0, np.int64),) * 2, (np.zeros(0, np.int64),) * 2)
        # Запас радиуса поиска пар на время между тиками решений.
        v_max = max(p.bee_types.of(k).cruise_speed for k in FLYING_KINDS) * 1.5
        self._pair_slack = 2.0 * v_max * self._decision_dt  # обе пчелы движутся
        self._obstacle_slack = v_max * self._decision_dt  # препятствие неподвижно
        # Ветер и рельеф впереди по курсу обновляются на тике решений (10 Гц): порывы —
        # секунды и десятки метров, за 0.1 с пчела пролетает меньше метра.
        self._wind = np.zeros((bees.n, 3))
        self._ground_ahead = np.zeros(bees.n)
        self._r_max = max(p.bee_types.of(k).radius for k in FLYING_KINDS)
        self._spawned = np.zeros(world.n_hives, dtype=np.int64)
        self._exit_points = [self._exit_grid(h) for h in range(world.n_hives)]
        self._exit_turn = np.zeros(world.n_hives, dtype=np.int64)

        # Демо-пчёлы (доверенные скрипты, не код игрока).
        self.pilot = WaypointPilot(self.autopilot, p.autopilot.arrive_radius)
        for bee in p.demo.bees:
            s = self.spawn(bee.hive, bee.kind)
            origin = world.hive_entrance[bee.hive, :2]
            self.pilot.add(s, bee, origin, speed=float(bees.cruise_empty[s]))
        if p.demo.swarm is not None:
            self.swarm = RandomWaypoints(
                self.autopilot, p.demo.swarm, rng.get("demo"), world.half_size
            )
            for h in range(world.n_hives):
                for kind in FLYING_KINDS:
                    for _ in range(p.demo.swarm.per_hive.get(kind, 0)):
                        s = self.spawn(h, kind)
                        self.swarm.add(int(bees.uid[s]), s, 0.0)

        # Стартовый состав (§4.6) — у ульев с кодом игрока; все начинают в улье.
        for spec in self.teams:
            for kind, n in p.economy.start_bees.items():
                for _ in range(n):
                    self.give_birth(spec.team, kind)

        # Враги — после стартового состава (id пчёл не зависят от включения врагов).
        self.enemies = Enemies(
            p, world, bees, rng=rng, kill_bees=self.kill, decision_dt=self._decision_dt
        )
        #: Время выбывания ульев со скриптом (NaN — в игре), BEES_SPEC §8.
        self.eliminated_at = np.full(world.n_hives, np.nan)
        #: Гибели пчёл по ульям и причинам (`kill(..., cause)`), для счёта и серий.
        self.deaths = {cause: np.zeros(world.n_hives, dtype=np.int64) for cause in DEATH_CAUSES}
        self._playing = [spec.team for spec in self.teams]
        self._min_flying_cost = min(p.economy.breeding[k].cost for k in FLYING_KINDS)

    def _parking_positions(self, n: int) -> np.ndarray:
        """Места парковки под картой: решётка с шагом 1 м, глубина `parking_depth`."""
        side = max(1, int(np.ceil(np.sqrt(n))))
        i = np.arange(n)
        xy = (np.column_stack([i % side, i // side]) - side / 2) * 1.0
        z = np.full(n, -self.params.physics.parking_depth)
        return np.column_stack([xy, z])

    def _grid_point(self, hive: int, k: int, radius: float) -> np.ndarray:
        """Точка `k` решётки перед летком улья (слои по высоте)."""
        per_layer = _SPAWN_COLUMNS * _SPAWN_ROWS
        layer, rest = divmod(k, per_layer)
        row, col = divmod(rest, _SPAWN_COLUMNS)
        entrance = self.world.hive_entrance[hive]
        xy = entrance[:2] + _SPAWN_STEP * np.array(
            [1.0 + row, col - (_SPAWN_COLUMNS - 1) / 2]
        )
        base = max(entrance[2], float(self.world.ground_height(xy)) + radius + 0.5)
        return np.array([xy[0], xy[1], base + _SPAWN_STEP * layer])

    def _spawn_point(self, hive: int, radius: float) -> np.ndarray:
        """Следующая точка решётки перед летком (демо-пчёлы рождаются сразу в воздухе)."""
        k = int(self._spawned[hive])
        self._spawned[hive] += 1
        return self._grid_point(hive, k, radius)

    def _exit_grid(self, hive: int) -> np.ndarray:
        """Точки вылета из улья: решётка перед летком, ближние к летку — первыми."""
        n = _SPAWN_COLUMNS * _SPAWN_ROWS * _EXIT_LAYERS
        pts = np.array([self._grid_point(hive, k, self._r_max) for k in range(n)])
        d = np.linalg.norm(pts - self.world.hive_entrance[hive], axis=1)
        return pts[np.argsort(d, kind="stable")]

    # --------------------------------------------------------------- пул: рождение и гибель

    @property
    def time(self) -> float:
        return self._steps * self._dt

    def _tank(self) -> float:
        """Множитель бака новой пчелы: 1 ± `tank_spread` (DECISIONS №86)."""
        spread = self.params.energy.tank_spread
        return 1.0 + spread * float(self._tank_rng.uniform(-1.0, 1.0)) if spread > 0 else 1.0

    def spawn(self, hive: int, kind: FlyingKind, pos: np.ndarray | None = None) -> int:
        """Родить летающую пчелу сразу в воздухе (демо, тесты); вернуть слот."""
        b = self.bees
        s = b.allocate(hive, kind, FLYING, tank=self._tank())
        if pos is None:
            pos = self._spawn_point(hive, float(b.radius[s]))
        self.control.reset(np.array([s]))
        self._activate(np.array([s]), np.asarray(pos, dtype=np.float64)[None])
        self.autopilot.speed[s] = np.nan
        self.autopilot.avoid[s] = True
        self._event_birth(hive, kind, int(b.uid[s]), s)
        return s

    def give_birth(self, hive: int, kind: BeeKind) -> int:
        """Родить пчелу внутри улья (выведение, стартовый состав); вернуть uid."""
        b = self.bees
        if kind == "house":
            uid = b.new_uid()
            self.economy.add_house(hive, uid)
            self._event_birth(hive, kind, uid, None)
            return uid
        s = b.allocate(hive, kind, IN_HIVE, tank=self._tank())
        self.control.reset(np.array([s]))
        self.autopilot.speed[s] = np.nan
        self.autopilot.avoid[s] = True
        uid = int(b.uid[s])
        self._event_birth(hive, kind, uid, s)
        return uid

    def _emit(self, event: dict[str, Any]) -> None:
        """Событие для реплея и стрима (§8)."""
        self.events.append(event)

    def _event_birth(self, hive: int, kind: str, uid: int, slot: int | None) -> None:
        self.events.append(
            {"type": "birth", "time": self.time, "bee": uid, "slot": slot,
             "hive": hive, "kind": kind}
        )

    def _activate(self, slots: np.ndarray, pos: np.ndarray) -> None:
        """Тело слота появляется в воздухе в точках `pos` и висит там."""
        b = self.bees
        self.backend.activate(slots, pos, b.radius[slots], b.mass[slots])
        self.autopilot.hover(slots, pos)
        self._refresh_environment(slots, pos, np.zeros_like(pos))

    def kill(self, slots: np.ndarray, cause: str) -> None:
        """Пчёлы погибают: событие, слот паркуется и возвращается в пул."""
        slots = np.atleast_1d(np.asarray(slots, dtype=np.int64))
        b = self.bees
        counter = self.deaths.get(cause)
        for s in slots.tolist():
            self.events.append(
                {"type": "death", "time": self.time, "bee": int(b.uid[s]), "slot": s,
                 "hive": int(b.hive[s]), "kind": b.kind_name(s), "cause": cause}
            )
            if counter is not None:
                counter[int(b.hive[s])] += 1
            if self.swarm is not None:
                self.swarm.remove(int(b.uid[s]))
        self.backend.park(slots, self._park_pos[slots])
        self.control.reset(slots)
        b.release(slots)

    def set_cargo(self, slots: np.ndarray, cargo: np.ndarray | float) -> None:
        """Груз нектара: меняет массу тела (вес и инерцию), DECISIONS №25."""
        slots = np.atleast_1d(np.asarray(slots, dtype=np.int64))
        b = self.bees
        b.cargo[slots] = np.clip(cargo, 0.0, b.cargo_max[slots])
        self.backend.set_mass(slots, b.mass[slots], b.radius[slots])

    # --------------------------------------------------------------- связь

    def say(self, slot: int, word: str, where: tuple[float, float]) -> None:
        """Сообщение пчелы своим (доставка на следующем тике решений); в улье — у летка."""
        b = self.bees
        if b.state[slot] == IN_HIVE:
            pos = self.world.hive_entrance[int(b.hive[slot])]
        else:
            pos = self.backend.body_state(np.array([slot]))[0][0]
        self.comms.post(slot, int(b.uid[slot]), int(b.hive[slot]), pos, word, where)

    def mark(self, slot: int, channel: int, amount: float = 1.0) -> None:
        """Феромон в клетку под пчелой."""
        pos, _ = self.backend.body_state(np.array([slot]))
        self.pheromones.mark(np.array([self.bees.hive[slot]]), pos, np.array([channel]),
                             np.array([amount]))

    # --------------------------------------------------------------- улей: вход, вылет, сбор

    def _economy_tick(self, dt: float, a: np.ndarray, pos: np.ndarray, vel: np.ndarray) -> None:
        """Цветы, сбор нектара, заправка в улье, домашние пчёлы и выведение за `dt`."""
        w = self.world
        fp = self.params.world.flowers
        np.minimum(w.flower_nectar + fp.regen_per_s * dt, fp.nectar_max, out=w.flower_nectar)
        self._collect(a, pos, vel, dt)

        b = self.bees
        inside = np.flatnonzero(b.state == IN_HIVE)
        if inside.size:
            given = self.economy.refuel(b.hive[inside], b.energy_max[inside] - b.energy[inside], dt)
            b.energy[inside] += given

        for birth in self.economy.step(dt):
            self.give_birth(birth.hive, birth.kind)

    def _collect(self, a: np.ndarray, pos: np.ndarray, vel: np.ndarray, dt: float) -> None:
        """Сборщики в режиме `collect` над своим цветком набирают нектар (§4.2)."""
        b, c, w = self.bees, self.control, self.world
        self.enemies.prey = (np.zeros(0, np.int64), np.zeros(0, np.int64))
        m = (c.mode[a] == COLLECT) & (b.state[a] == FLYING)
        if not np.any(m):
            return
        p = self.params.economy.collect
        slots = a[m]
        flower = c.target[slots]
        fpos = w.flower_pos[flower]
        d = pos[m] - fpos
        over = (
            (np.hypot(d[:, 0], d[:, 1]) <= p.max_horizontal)
            & (np.abs(d[:, 2]) <= p.max_height)
            & (np.linalg.norm(vel[m], axis=1) < p.max_speed)
        )
        room = b.cargo_max[slots] - b.cargo[slots]
        want = np.where(over, np.minimum(p.rate * dt, room), 0.0)
        # Несколько сборщиков на одном цветке делят остаток поровну (пропорционально).
        demand = np.bincount(flower, weights=want, minlength=w.flower_nectar.shape[0])
        scale = np.ones_like(demand)
        short = demand > w.flower_nectar
        scale[short] = w.flower_nectar[short] / demand[short]
        take = want * scale[flower]
        # Добыча пауков — сборщики, которые сейчас набирают нектар на цветке с пауком.
        bitten = (take > 0) & w.flower_spider[flower]
        if np.any(bitten):
            self.enemies.prey = (slots[bitten], flower[bitten])
        if np.any(take > 0):
            np.subtract.at(w.flower_nectar, flower, take)
            np.maximum(w.flower_nectar, 0.0, out=w.flower_nectar)
            self.set_cargo(slots, b.cargo[slots] + take)
        done = (b.cargo[slots] >= b.cargo_max[slots] - 1e-9) | (w.flower_nectar[flower] <= 1e-9)
        c.mode[slots[done]] = HOVER  # висит над цветком, ждёт нового решения

    def _enter_hives(self, a: np.ndarray, pos: np.ndarray) -> None:
        """`go_home`: пчёлы у летка входят в улей — тело паркуется, нектар выгружается.

        Выгрузка автоматическая (DECISIONS №82): весь груз сборщика сразу на склад.
        """
        b, c = self.bees, self.control
        entrance = self.world.hive_entrance[b.hive[a]]
        near = np.linalg.norm(pos - entrance, axis=1) <= self.params.hive.enter_radius
        enter = a[near & (c.mode[a] == GO_HOME) & (b.state[a] == FLYING)]
        if enter.size == 0:
            return
        self.backend.park(enter, self._park_pos[enter])
        b.set_state(enter, IN_HIVE)
        b.thrust[enter] = 0.0
        c.mode[enter] = HOVER
        c.exit_pending[enter] = False
        loaded = enter[b.cargo[enter] > 0]
        for s in loaded.tolist():
            amount, h = float(b.cargo[s]), int(b.hive[s])
            self.economy.deliver(h, amount)
            self.events.append({"type": "delivery", "time": self.time, "bee": int(b.uid[s]),
                                "hive": h, "nectar": amount})
        if loaded.size:
            self.set_cargo(loaded, 0.0)

    def _exit_hives(self) -> None:
        """Пчёлы, которые хотят вылететь, появляются в свободных точках перед летком."""
        b, c = self.bees, self.control
        want = np.flatnonzero((b.state == IN_HIVE) & c.exit_pending)
        if want.size == 0:
            return
        limit = self.params.hive.exit_per_tick
        a = b.airborne
        air_pos, _ = self.backend.body_state(a)
        clearance = 2.0 * self._r_max + 0.2
        for h in np.unique(b.hive[want]).tolist():
            leaving = want[b.hive[want] == h][:limit]
            pts = self._exit_points[h]
            if air_pos.shape[0]:
                d = np.linalg.norm(pts[:, None, :] - air_pos[None, :, :], axis=2)
                free = np.flatnonzero(d.min(axis=1) > clearance)
            else:
                free = np.arange(pts.shape[0])
            # Каждый тик начинаем с другой точки — пчёлы не толпятся в одной.
            free = np.roll(free, -int(self._exit_turn[h] % max(free.size, 1)))
            self._exit_turn[h] += 1
            n = min(leaving.size, free.size)
            if n == 0:
                continue
            slots, at = leaving[:n], pts[free[:n]]
            b.set_state(slots, FLYING)
            c.exit_pending[slots] = False
            hovering = c.mode[slots] == HOVER
            targets = self.autopilot.target[slots].copy()
            target_agl = self.autopilot.target_agl[slots].copy()
            self._activate(slots, at)
            # Команда, отданная в улье (fly_to…), продолжает действовать после вылета.
            keep = ~hovering
            self.autopilot.target[slots[keep]] = targets[keep]
            self.autopilot.target_agl[slots[keep]] = target_agl[keep]
            air_pos = np.vstack([air_pos, at])

    def _refresh_targets(self, slots: np.ndarray, pos: np.ndarray, vel: np.ndarray) -> None:
        """Цели автопилота для режимов, которым нужна свежая цель каждый тик."""
        if slots.size == 0:
            return
        b, c, w, ap = self.bees, self.control, self.world, self.autopilot
        mode = c.mode[slots]

        m = mode == GO_HOME
        if np.any(m):
            ids = slots[m]
            hive = b.hive[ids]
            entrance = w.hive_entrance[hive]
            # Леток — на грани +x. Пчела позади этой грани летит сначала к точке
            # сбоку от улья, иначе прямой путь к летку упирается в стенку.
            front = w.hive_pos[hive, 0] + w.hive_half[hive, 0]
            dy = pos[m][:, 1] - w.hive_pos[hive, 1]
            side = np.where(dy >= 0.0, 1.0, -1.0)
            goal = entrance[:, :2].copy()
            behind = pos[m][:, 0] < front + 0.5
            margin = self.params.hive.approach_margin
            goal[behind, 0] = front[behind] + 1.0
            goal[behind, 1] = w.hive_pos[hive[behind], 1] + side[behind] * (
                w.hive_half[hive[behind], 1] + margin
            )
            ap.fly_to(ids, goal, z=entrance[:, 2], speed=c.speed[ids])

        m = mode == COLLECT
        if np.any(m):
            ids = slots[m]
            fpos = w.flower_pos[c.target[ids]]
            ap.fly_to(ids, fpos[:, :2], z=fpos[:, 2] + _COLLECT_HOVER, speed=c.speed[ids])

    # ------------------------------------------------- автовозврат, поиск, сбор у места

    def _energy_percent(self, slots: np.ndarray) -> np.ndarray:
        b = self.bees
        return 100.0 * b.energy[slots] / np.maximum(b.energy_max[slots], 1e-12)

    def _auto_home(self) -> None:
        """Автовозврат (DECISIONS №86): ниже порога — домой; дома до уровня — снова свободна.

        Текущая ждущая команда получает «не вышло»; конец автовозврата увеличивает
        `epoch` — раннер начинает `loop()` с начала.
        """
        b, c = self.bees, self.control
        alive = b.alive
        alive = alive[np.isin(b.hive[alive], self._playing)]  # только ульи с кодом игрока
        if alive.size == 0:
            return
        pct = self._energy_percent(alive)
        hive = b.hive[alive]
        state = b.state[alive]
        threshold = self.home_energy[hive]
        low = alive[(state == FLYING) & ~c.auto_home[alive] & (threshold > 0)
                    & (pct < threshold)]
        if low.size:
            c.auto_home[low] = True
            c.mode[low] = GO_HOME
            c.speed[low] = np.nan
            c.exit_pending[low] = False
            busy = low[(c.wait_seq[low] > 0) & (c.wait_state[low] == RUNNING)]
            c.wait_state[busy] = FAILED
            self.autopilot.avoid[low] = True
            self._refresh_targets(low, *self.backend.body_state(low))
        home = alive[(state == IN_HIVE) & c.auto_home[alive]]
        if home.size:
            c.exit_pending[home] = False
            ready = home[self._energy_percent(home)
                         >= self.refuel_energy[b.hive[home]] - 1e-9]
            c.auto_home[ready] = False
            c.epoch[ready] += 1

    def _check_search(self, a: np.ndarray, pos: np.ndarray) -> None:
        """`search`/`explore`: остановиться у первого увиденного цветка с нектаром."""
        c, w = self.control, self.world
        m = (c.mode[a] == SEARCH) & (self.bees.state[a] == FLYING)
        if not np.any(m):
            return
        slots, p = a[m], pos[m]
        view = self.sensors.view_radius(slots, self.weather.rain)
        pairs = self.sensors.flower_grid.within(p, view)
        rich = w.flower_nectar[pairs.point] >= self.params.program.search_min_nectar
        q, f, d = pairs.query[rich], pairs.point[rich], pairs.dist[rich]
        if q.size == 0:
            return
        order = np.lexsort((f, d, q))  # по пчеле, затем ближний цветок (ничья — меньший номер)
        q, f = q[order], f[order]
        first = np.flatnonzero(np.r_[True, q[1:] != q[:-1]])
        found, flower = slots[q[first]], f[first]
        c.mode[found] = HOVER
        c.wait_result[found] = flower
        self.autopilot.hover(found, p[q[first]])

    def _check_collect_at(self, a: np.ndarray, pos: np.ndarray) -> None:
        """`collect(место)`: подлетев к месту, выбрать ближайший к нему цветок с нектаром."""
        c, w, pp = self.control, self.world, self.params.program
        m = (c.mode[a] == COLLECT_AT) & (self.bees.state[a] == FLYING)
        if not np.any(m):
            return
        slots, p = a[m], pos[m]
        view = self.sensors.view_radius(slots, self.weather.rain)
        place = c.place[slots]
        to_place = np.hypot(p[:, 0] - place[:, 0], p[:, 1] - place[:, 1])
        near = to_place <= view
        arrived = to_place <= max(pp.arrive_tolerance, 2.0)
        fxy = w.flower_pos[:, :2]
        for i in np.flatnonzero(near).tolist():
            s = int(slots[i])
            dp = np.hypot(fxy[:, 0] - place[i, 0], fxy[:, 1] - place[i, 1])
            db = np.hypot(fxy[:, 0] - p[i, 0], fxy[:, 1] - p[i, 1])
            ok = (dp <= pp.collect_place_radius) & (db <= view[i]) & (
                w.flower_nectar >= pp.search_min_nectar
            )
            if np.any(ok):
                cand = np.flatnonzero(ok)
                best = int(cand[np.lexsort((cand, dp[cand]))[0]])
                c.mode[s] = COLLECT
                c.target[s] = best
                self._refresh_targets(np.array([s]), p[i : i + 1], np.zeros((1, 3)))
            elif arrived[i]:
                c.mode[s] = HOVER  # цветка с нектаром у места нет — «не вышло»

    # --------------------------------------------------------------- ожидание команд

    def _wait_snapshot(self, parsed: Parsed) -> dict[int, tuple[int, int, float, bool]]:
        """Ожидания слотов до команд тика и где была пчела: (seq, состояние, начало, в улье)."""
        c, b = self.control, self.bees
        return {
            slot: (int(c.wait_seq[slot]), int(c.wait_state[slot]), float(c.wait_since[slot]),
                   bool(b.state[slot] == IN_HIVE))
            for slot, _, _, _ in parsed.waits
        }

    def _register_waits(
        self, parsed: Parsed, prev: dict[int, tuple[int, int, float, bool]]
    ) -> None:
        """Любая команда движения снимает старое ожидание; ждущие команды ставят новое.

        Повтор той же команды (раннер не увидел подтверждения) не сбрасывает отсчёт
        таймаута. Во время автовозврата ждущая команда сразу «не вышло».
        """
        c = self.control
        if not parsed.moves and not parsed.waits:
            return
        for rows in parsed.moves.values():
            moved = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
            moved = moved[~c.auto_home[moved]]
            c.wait_seq[moved] = 0
            c.wait_state[moved] = RUNNING
        n_flowers = self.world.flower_pos.shape[0]
        flower_of = {r[0]: r[1] for r in parsed.moves.get("collect", [])}
        for slot, seq, op, valid in parsed.waits:
            old_seq, old_state, old_since, _ = prev[slot]
            c.wait_seq[slot] = seq
            c.wait_state[slot] = RUNNING
            c.wait_result[slot] = -1
            c.wait_since[slot] = (
                old_since if old_seq == seq and old_state == RUNNING else self.time
            )
            if not valid or c.auto_home[slot]:
                c.wait_state[slot] = FAILED
                continue
            c.wait_cond[slot] = WAIT_COND[op]
            if op == "collect" and not 0 <= flower_of.get(slot, -1) < n_flowers:
                c.wait_state[slot] = FAILED  # такого цветка нет
            if op == "refuel" and self.bees.state[slot] != IN_HIVE:
                c.wait_state[slot] = FAILED  # заправка — только дома

    def _check_waits(self) -> None:
        """Тик решений: какие ждущие команды выполнены, а какие вышли по таймауту.

        Условия (DECISIONS №61, №87): `fly_to` — ближе `arrive_tolerance` к цели
        автопилота и медленнее `arrive_max_speed`; `go_home` — в улье; `collect` —
        набор закончен (успех — груз полный); `search`/`explore` — увидела цветок
        (результат — его номер) или долетела (результат −1); `refuel` — дома и бак
        не ниже уровня.
        """
        c, b = self.control, self.bees
        w = np.flatnonzero((c.wait_seq > 0) & (c.wait_state == RUNNING))
        if w.size == 0:
            return
        p = self.params.program
        cond, state, mode = c.wait_cond[w], b.state[w], c.mode[w]
        air = (state == FLYING) | (state == FALLING)
        done = np.zeros(w.size, dtype=bool)
        failed = np.zeros(w.size, dtype=bool)
        done |= (cond == ENTER) & (state == IN_HIVE)
        collected = (cond == COLLECTED) & (mode != COLLECT) & (mode != COLLECT_AT)
        full = b.cargo[w] >= b.cargo_max[w] - 1e-9
        done |= collected & full
        failed |= collected & ~full
        done |= (cond == FOUND) & (c.wait_result[w] >= 0)
        refuel = cond == REFUELED
        done |= refuel & (state == IN_HIVE) & (
            self._energy_percent(w) >= c.refuel_level[w] - 1e-9
        )
        failed |= refuel & (state != IN_HIVE)
        check = ((cond == ARRIVE) | ((cond == FOUND) & (mode == SEARCH))) & air
        if np.any(check):
            slots = w[check]
            pos, vel = self.backend.body_state(slots)
            ap = self.autopilot
            goal = ap.target[slots].copy()
            agl = ap.target_agl[slots]
            follow = ~np.isnan(agl)
            if np.any(follow):
                goal[follow, 2] = self.world.ground_height(goal[follow, :2]) + agl[follow]
            near = np.linalg.norm(pos - goal, axis=1) <= p.arrive_tolerance
            slow = np.linalg.norm(vel, axis=1) <= p.arrive_max_speed
            done[np.flatnonzero(check)[near & slow]] = True
        c.wait_state[w[done]] = DONE
        late = ~done & (failed | (self.time - c.wait_since[w] > p.command_timeout_s + 1e-9))
        c.wait_state[w[late]] = FAILED

    def _attach_control(self, cache: dict[int, list[AgentSensors]]) -> None:
        """В сенсоры пчёл: автовозврат, `epoch`, статус ожидания `[seq, состояние, результат]`
        и найденный `search`/`explore` цветок `found = [id, x, y, z, нектар]`."""
        c, b, w = self.control, self.bees, self.world
        alive = b.alive
        rows = {
            uid: (bool(ah), int(ep), int(seq), int(st), int(res))
            for uid, ah, ep, seq, st, res in zip(
                b.uid[alive].tolist(), c.auto_home[alive].tolist(), c.epoch[alive].tolist(),
                c.wait_seq[alive].tolist(), c.wait_state[alive].tolist(),
                c.wait_result[alive].tolist(), strict=True,
            )
        }
        for agents in cache.values():
            for agent in agents:
                me = agent["me"]
                auto, epoch, seq, st, res = rows[me["id"]]
                me["auto_home"] = auto
                me["epoch"] = epoch
                if seq > 0:
                    me["wait"] = [seq, st, res]
                    if res >= 0 and st == DONE:
                        me["found"] = [res, *w.flower_pos[res].tolist(),
                                       float(w.flower_nectar[res])]

    # --------------------------------------------------------------- Module

    def physics(self) -> PhysicsBackend:
        return self.backend

    def agent_teams(self) -> list[TeamSpec]:
        return list(self.teams)

    def decide(self, tick: int) -> None:
        self._tick = tick
        b = self.bees

        # Улей за прошедший тик: сбор, заправка, переработка, выведение; вход и вылет.
        dt = self.time - self._economy_time
        self._economy_time = self.time
        a = b.airborne
        pos, vel = self.backend.body_state(a)
        if dt > 0:
            self._economy_tick(dt, a, pos, vel)

        # Погода (§6) и пауки (§7).
        prev = self.weather.state
        if tick > 0 and self.weather.update(self._decision_dt) is not None:
            self._emit({"type": "weather", "time": self.time, "state": self.weather.state,
                        "prev": prev, "wind": self.weather.w_ref, "rain": self.weather.rain})
        self.enemies.decide()

        a = b.airborne
        pos, vel = self.backend.body_state(a)
        self._enter_hives(a, pos)
        self._exit_hives()
        self._check_elimination()
        self._auto_home()

        a = b.airborne
        pos, vel = self.backend.body_state(a)
        self._refresh_targets(a, pos, vel)
        self._check_search(a, pos)
        self._check_collect_at(a, pos)
        self._check_waits()
        self.bee_grid.build(pos)
        self._decide_pos, self._decide_vel, self._decide_slots = pos, vel, a

        # Пары для автопилота на время до следующего тика (с запасом радиуса).
        r = b.radius[a]
        p = self.params.autopilot
        sep = self.bee_grid.within(
            pos, r + self._r_max + p.separation_margin + self._pair_slack, exclude_self=True
        )
        obs = self.sensors.obstacle_pairs(pos, r + p.avoid_margin + self._obstacle_slack)
        self._pairs_slots = (a[sep.query], a[sep.point], a[obs.query], obs.point)
        self._pairs_for = None
        self._refresh_environment(a, pos, vel)

        inside = np.flatnonzero(b.state == IN_HIVE)
        self._delivery = self.comms.deliver(
            self.bee_grid, a, b.hive[a], self.world.hive_entrance, inside, b.hive[inside]
        )
        self.pheromones.decay(self._decision_dt)
        self._sensor_cache = None

        full_pos = self.backend.poses()[0]
        full_vel = self.backend.velocities()[:, :3]
        self.pilot.decide(full_pos, full_vel, self._decision_dt)
        if self.swarm is not None:
            for h in range(self.world.n_hives):
                self.swarm.decide(self.hive_sensors(h), self.time, self._decision_dt)

    def _refresh_environment(self, slots: np.ndarray, pos: np.ndarray, vel: np.ndarray) -> None:
        """Ветер в точках пчёл и рельеф впереди по курсу — на тике решений."""
        ground = self.world.ground_height(pos[:, :2])
        self._wind[slots] = self.weather.wind_at(pos, ground, self.time)
        lookahead = self.params.autopilot.terrain_lookahead_s
        self._ground_ahead[slots] = self.world.ground_height(pos[:, :2] + vel[:, :2] * lookahead)

    def hive_sensors(self, hive: int) -> list[AgentSensors]:
        """Сенсоры летающих пчёл улья (в воздухе и в улье) на текущем тике (§5.1)."""
        if self._sensor_cache is None:
            self._sensor_cache = self.sensors.build(
                SensorInputs(
                    time=self.time,
                    airborne=self._decide_slots,
                    pos=self._decide_pos,
                    bee_grid=self.bee_grid,
                    rain=self.weather.rain,
                    messages=self._delivery,
                )
            )
            self._attach_control(self._sensor_cache)
        return self._sensor_cache[hive]

    def _counts(self, hive: int) -> dict[str, Any]:
        b = self.bees
        sl = b.hive_slots(hive)
        state, kind = b.state[sl], b.kind[sl]
        air = (state == FLYING) | (state == FALLING)
        out: dict[str, Any] = {
            k: {
                "in_hive": int(np.count_nonzero((state == IN_HIVE) & (kind == i))),
                "flying": int(np.count_nonzero(air & (kind == i))),
            }
            for i, k in enumerate(FLYING_KINDS)
        }
        out["house"] = self.economy.house_count(hive)
        return out

    def team_view(self, hive: int) -> dict[str, Any]:
        """Сенсоры улья (§5.3): мёд, численность, места, цены, сообщения у летка."""
        e, b = self.economy, self.bees
        d = self._delivery
        messages = [d.row(i) for i in d.hive_inbox[hive].tolist()
                    if int(d.sender_uid[i]) != HIVE_SENDER]  # своё же сообщение улью не нужно
        notes, self._notes[hive] = self._notes[hive], []
        flying = int(np.count_nonzero(b.state[b.hive_slots(hive)] != FREE))
        return {
            "time": self.time,
            "honey": float(e.honey[hive]),
            "nectar": float(e.nectar[hive]),
            "counts": self._counts(hive),
            "busy": e.alive_and_queued(hive, flying),
            "max_bees": e.max_bees,
            "costs": {k: v.cost for k, v in self.params.economy.breeding.items()},
            "messages": messages,
            "notes": notes,
        }

    def collect_sensors(self, team: TeamId) -> SensorBatch:
        view = self.team_view(team)
        return SensorBatch(
            tick=self._tick, team=team, budget_ms=self._budget_ms, team_view=view,
            agents=self.hive_sensors(team),
        )

    def apply_commands(self, team: TeamId, cmds: CommandBatch) -> None:
        b = self.bees
        sl = b.hive_slots(team)
        slots = np.arange(sl.start, sl.stop)
        alive = slots[b.state[sl] != FREE]
        parsed = parse(
            cmds.commands,
            cmds.team_command,
            flying=dict(zip(b.uid[alive].tolist(), alive.tolist(), strict=True)),
            flying_kind=b.kind,
            max_word=self.params.comms.max_word,
            max_say=self.params.comms.max_say,
            channels=self.params.pheromones.channels,
        )
        self.invalid_commands[team] += parsed.invalid
        prev = self._wait_snapshot(parsed)
        self._apply_moves(parsed)
        self._register_waits(parsed, prev)
        for slot, word, x, y in parsed.says:
            self.say(slot, word, (x, y))
        for slot, channel, amount in parsed.marks:
            if b.state[slot] in (FLYING, FALLING):
                self.mark(slot, channel, amount)
        self._apply_hive(team, parsed)

    def _apply_hive(self, team: TeamId, parsed: Parsed) -> None:
        e, b = self.economy, self.bees
        for kind in parsed.hatch:
            sl = b.hive_slots(team)
            flying_alive = int(np.count_nonzero(b.state[sl] != FREE))
            err = e.breed(team, kind, flying_alive)
            if err is not None:
                self._notes[team].append(f"hatch({_KIND_CLASS[kind]}) не получилось: {err}")
        for word, x, y in parsed.hive_says:
            self.comms.post(-1, HIVE_SENDER, team, self.world.hive_entrance[team], word, (x, y))
        if parsed.home_energy is not None:
            self.home_energy[team] = parsed.home_energy
        if parsed.refuel_energy is not None:
            self.refuel_energy[team] = parsed.refuel_energy

    def _apply_moves(self, parsed: Parsed) -> None:
        """Команды движения: режимы, цели автопилота, вылет из улья.

        Пчёлы на автовозврате команды движения не слушают (DECISIONS №86).
        """
        b, c, ap = self.bees, self.control, self.autopilot
        changed: list[np.ndarray] = []
        for op, all_rows in parsed.moves.items():
            rows = [r for r in all_rows if not c.auto_home[r[0]]]
            if not rows:
                continue
            slots = np.array([r[0] for r in rows], dtype=np.int64)
            in_hive = b.state[slots] == IN_HIVE
            if op in ("stop", "refuel"):
                if op == "refuel":
                    c.refuel_level[slots] = [r[1] for r in rows]
                c.mode[slots] = HOVER
                c.exit_pending[slots] = False
                air = slots[~in_hive]
                if air.size:
                    ap.hover(air, self.backend.body_state(air)[0])
                continue
            speed = np.array([r[-1] for r in rows], dtype=np.float64)
            c.speed[slots] = speed
            ap.avoid[slots] = True
            if op == "go_home":
                c.mode[slots] = GO_HOME
                c.exit_pending[slots] = False  # в улье — остаться
                changed.append(slots[~in_hive])
                continue
            # Остальные команды из улья сначала выводят пчелу наружу.
            c.exit_pending[slots[in_hive]] = True
            if op in ("fly_to", "search", "explore", "collect_at"):
                if op == "explore":
                    xy = self._explore_points(slots)
                else:
                    xy = np.array([[r[1], r[2]] for r in rows], dtype=np.float64)
                c.mode[slots] = {"fly_to": FLY_TO, "collect_at": COLLECT_AT}.get(op, SEARCH)
                c.place[slots] = xy
                ap.fly_to(slots, xy, speed=speed)
            elif op == "collect":
                target = np.array([r[1] for r in rows], dtype=np.int64)
                ok = (target >= 0) & (target < self.world.flower_pos.shape[0])
                self.invalid_commands[int(b.hive[slots[0]])] += int(np.sum(~ok))
                slots, target = slots[ok], target[ok]
                c.mode[slots] = COLLECT
                c.target[slots] = target
                changed.append(slots[b.state[slots] != IN_HIVE])
        if changed:
            air = np.concatenate(changed)
            if air.size:
                pos, vel = self.backend.body_state(air)
                self._refresh_targets(air, pos, vel)

    def _explore_points(self, slots: np.ndarray) -> np.ndarray:
        """Случайные точки `explore` вокруг летка (поток `bees.explore`, по порядку слотов)."""
        r0, r1 = self.params.program.explore_radius
        n = slots.size
        angle = self._explore_rng.uniform(0.0, 2.0 * np.pi, n)
        radius = self._explore_rng.uniform(r0, r1, n)
        home = self.world.hive_entrance[self.bees.hive[slots], :2]
        return home + radius[:, None] * np.column_stack([np.cos(angle), np.sin(angle)])

    def _local(self, a: np.ndarray):
        """Пары тика решений в локальных индексах текущих слотов в воздухе."""
        if self._pairs_for is not a:
            local = np.full(self.bees.n, -1, dtype=np.int64)
            local[a] = np.arange(a.shape[0])
            si, sj, oi, ok = self._pairs_slots
            li, lj = local[si], local[sj]
            m = (li >= 0) & (lj >= 0)
            lo = local[oi]
            mo = lo >= 0
            self._local_pairs = ((li[m], lj[m]), (lo[mo], ok[mo]))
            self._pairs_for = a
        return self._local_pairs

    def pre_physics(self, dt: float) -> None:
        b = self.bees
        a = b.airborne
        if a.shape[0] == 0:
            return
        ph = self.params.physics
        pos, vel = self.backend.body_state(a)
        ground = self.world.ground_height(pos[:, :2])
        radius = b.radius[a]
        mass = b.mass[a]
        thrust_max = b.thrust_max[a]

        wind = self._wind[a]
        drag_coef = b.drag_coef[a]
        external = np.zeros((a.shape[0], 3))
        if self.weather.rain:
            drag_coef = drag_coef * ph.rain_drag_multiplier
            external += forces.rain_force(radius, ph.rain_force_coef)
        external += forces.drag(vel, wind, drag_coef)
        walls = 0.0
        half, ceiling = self.world.half_size, self.world.ceiling_agl
        if np.abs(pos[:, :2]).max() > half or (pos[:, 2] - ground).max() > ceiling:
            walls = forces.boundary_force(
                pos, ground, mass, half_size=half, ceiling_agl=ceiling,
                stiffness=ph.wall_stiffness,
            )
        # Крейсерская скорость при текущей массе (с грузом) и погоде: вертикальная
        # нагрузка — вес и дождь, сопротивление — с учётом дождя.
        load = mass * self.gravity
        if self.weather.rain:
            load = load + ph.rain_force_coef * radius**2
        cruise = forces.cruise_speed(load, thrust_max, drag_coef)

        neighbors, obstacles = self._local(a)
        thrust = self.autopilot.thrust(
            a, pos, vel,
            mass=mass,
            thrust_max=thrust_max,
            cruise=cruise,
            radius=radius,
            ground=ground,
            ground_ahead=self._ground_ahead[a],
            feedforward=-external,
            neighbors=neighbors,
            obstacles=obstacles,
        )
        thrust[b.state[a] == FALLING] = 0.0  # энергия кончилась — винты стоят
        b.thrust[a] = thrust
        self.backend.set_forces(a, thrust + external + walls)

    def post_physics(self, dt: float) -> None:
        self._steps += 1
        b = self.bees
        a = b.airborne
        if a.shape[0] == 0:
            return
        power = forces.power(b.thrust[a], b.power_idle[a], b.power_coef[a])
        energy = np.maximum(b.energy[a] - power * dt, 0.0)
        b.energy[a] = energy
        empty = a[(energy <= 0.0) & (b.state[a] == FLYING)]
        if empty.size:
            b.set_state(empty, FALLING)

        falling = a[b.state[a] == FALLING]
        if falling.size and self.params.energy.dead_on_ground:
            self._ground_deaths(falling)

    def _ground_deaths(self, falling: np.ndarray) -> None:
        """Падающая пчела, коснувшаяся рельефа или статики, погибает."""
        pos, _ = self.backend.body_state(falling)
        ground = self.world.ground_height(pos[:, :2])
        touched = pos[:, 2] - self.bees.radius[falling] - ground <= (
            self.params.energy.ground_contact_margin
        )
        ca, cb = self.backend.contact_pairs()
        if ca.size:
            on_static = np.concatenate([ca[cb == STATIC], cb[ca == STATIC]])
            touched |= np.isin(falling, on_static)
        if np.any(touched):
            self.kill(falling[touched], "energy")

    # --------------------------------------------------------------- выбывание (§8)

    def _check_elimination(self) -> None:
        """Улей со скриптом выбывает (DECISIONS №40).

        Нет живых пчёл, либо нет летающих пчёл и летающих личинок, а мёда меньше
        цены самой дешёвой летающей пчелы.
        """
        b, e = self.bees, self.economy
        for h in self._playing:
            if not np.isnan(self.eliminated_at[h]):
                continue
            flying = int(np.count_nonzero(b.state[b.hive_slots(h)] != FREE))
            alive = flying + e.house_count(h)
            flying_larvae = any(lv.kind != "house" for lv in e.queue[h])
            if alive == 0 or (
                flying == 0 and not flying_larvae and e.honey[h] < self._min_flying_cost
            ):
                self.eliminated_at[h] = self.time
                self._emit({"type": "eliminated", "time": self.time, "hive": h,
                            "honey": float(e.honey[h]), "alive": alive})

    # --------------------------------------------------------------- кадр и сцена

    def _pos_box(self) -> tuple[np.ndarray, np.ndarray]:
        """Рамка квантования позиций: карта с запасом, по высоте — до потолка."""
        w = self.world
        m = w.half_size + _POS_MARGIN
        lo = np.array([-m, -m, -_POS_MARGIN])
        hi = np.array([m, m, w.max_relief + w.ceiling_agl + 2 * _POS_MARGIN])
        return lo, hi

    def snapshot(self) -> Frame:
        """Кадр реплея и стрима (DECISIONS №39): только тела в воздухе, компактные типы.

        Позиции — `uint16` с фиксированной точкой в рамке `scene()["pos_lo"/"pos_hi"]`,
        скорости — `float16`, энергия, груз и нектар цветов — доли в `uint8` (0–255).
        Столбцы `hive_counts` — `scene()["hive_counts"]`: летающие по типам, домашние, в улье.
        """
        b, e = self.bees, self.economy
        lo, hi = self._pos_box()
        a = b.airborne
        pos, vel = self.backend.body_state(a)
        nk = len(FLYING_KINDS)
        counts = np.zeros((self.world.n_hives, nk + 2), dtype=np.uint16)
        for hv in range(self.world.n_hives):
            sl = b.hive_slots(hv)
            st, kd = b.state[sl], b.kind[sl]
            for k in range(nk):
                counts[hv, k] = np.count_nonzero((st != FREE) & (kd == k))
            counts[hv, nk] = e.house_count(hv)
            counts[hv, nk + 1] = np.count_nonzero(st == IN_HIVE)
        wind = self.weather.w_ref * self.weather.base_direction(self.time)
        nectar_max = max(self.params.world.flowers.nectar_max, 1e-9)
        frame = Frame(
            tick=self._steps,
            time=self.time,
            arrays={
                "bee_slot": a.astype(np.uint16),
                "bee_uid": b.uid[a].astype(np.int32),
                "bee_kind": b.kind[a].astype(np.uint8),
                "bee_state": b.state[a].astype(np.uint8),
                "bee_pos": quantize(pos, lo, hi),
                "bee_vel": vel.astype(np.float16),
                "bee_energy": _fraction_u8(b.energy[a], b.energy_max[a]),
                "bee_cargo": _fraction_u8(b.cargo[a], b.cargo_max[a]),
                "hive_honey": e.honey.astype(np.float32),
                "hive_nectar": e.nectar.astype(np.float32),
                "hive_counts": counts,
                "flower_nectar": _fraction_u8(
                    self.world.flower_nectar, np.full(self.world.flower_nectar.shape, nectar_max)
                ),
                "weather": np.array([_WEATHER_STATES.index(self.weather.state)], dtype=np.uint8),
                "wind": wind.astype(np.float16),
            },
            events=self.events,
        )
        self.events = []
        return frame

    def scene(self) -> dict[str, Any]:
        """Статическая сцена для заголовка реплея и вьюеров: мир, рамка квантования, справочники."""
        w = self.world
        lo, hi = self._pos_box()
        p = self.params
        return {
            "module": self.name,
            "engine": self.backend.engine_version,
            "pos_lo": lo,
            "pos_hi": hi,
            "bee_slots": self.bees.n,
            "per_hive": self.bees.per_hive,
            "kinds": list(FLYING_KINDS),
            "states": list(STATE_NAMES),
            "weather_states": list(_WEATHER_STATES),
            "hive_counts": [*FLYING_KINDS, "house", "in_hive"],
            "bee_radius": {k: p.bee_types.of(k).radius for k in FLYING_KINDS},
            "nectar_max": p.world.flowers.nectar_max,
            "hive_colors": list(self.hive_colors),
            "playing": list(self._playing),
            "world_digest": w.digest(),
            "world": {
                "map_size": w.map_size,
                "ceiling_agl": w.ceiling_agl,
                "max_relief": w.max_relief,
                "terrain": w.terrain.astype(np.float32),
                "tree_pos": w.tree_pos,
                "tree_trunk_radius": w.tree_trunk_radius,
                "tree_trunk_height": w.tree_trunk_height,
                "tree_crown_radius": w.tree_crown_radius,
                "rock_pos": w.rock_pos,
                "rock_half": w.rock_half,
                "rock_yaw": w.rock_yaw,
                "hive_pos": w.hive_pos,
                "hive_half": w.hive_half,
                "hive_entrance": w.hive_entrance,
                "flower_pos": w.flower_pos,
                "flower_spider": w.flower_spider,
            },
        }

    def apply_frame(self, frame: Frame, nxt: Frame | None = None, alpha: float = 0.0) -> None:
        """Показать кадр реплея в физической модели (без шага физики) — для `--mj-viewer`.

        Если задан следующий кадр, позиции тел, которые есть в обоих, интерполируются
        с долей `alpha` (0 — `frame`, 1 — `nxt`).
        """
        lo, hi = self._pos_box()
        be = self.backend
        be.teleport(np.arange(len(self._park_pos)), self._park_pos)

        def lerp(prefix: str) -> tuple[np.ndarray, np.ndarray]:
            ar = frame.arrays
            ids = ar[f"{prefix}_slot"].astype(np.int64)
            pos = dequantize(ar[f"{prefix}_pos"], lo, hi)
            if nxt is not None and alpha > 0 and ids.size:
                na = nxt.arrays
                same = na[f"{prefix}_uid"][:, None] == ar[f"{prefix}_uid"][None, :]
                j, i = np.nonzero(same)
                n_pos = dequantize(na[f"{prefix}_pos"], lo, hi)
                pos[i] += alpha * (n_pos[j] - pos[i])
            return ids, pos

        ids, pos = lerp("bee")
        if ids.size:
            radius = np.array([self.params.bee_types.of(k).radius for k in FLYING_KINDS])
            be.place(ids, pos, radius[frame.arrays["bee_kind"].astype(np.int64)])
        be.forward()

    # --------------------------------------------------------------- счёт (§8)

    def score(self) -> ScoreBoard:
        """Склад, численность и места.

        Места и победитель — только у ульев со скриптом: больше мёда → больше
        доставлено нектара → больше живых; выбывшие ниже всех (кто продержался
        дольше — выше).
        """
        b, e = self.bees, self.economy
        teams: dict[TeamId, dict[str, float]] = {}
        for h in range(self.world.n_hives):
            sl = b.hive_slots(h)
            alive = b.state[sl] != FREE
            row = {
                "place": 0.0,
                "honey": float(e.honey[h]),
                "nectar": float(e.nectar[h]),
                "delivered": float(e.delivered[h]),
                "processed": float(e.processed[h]),
            }
            row.update(
                {k: float(np.sum(alive & (b.kind[sl] == i))) for i, k in enumerate(FLYING_KINDS)}
            )
            row["house"] = float(e.house_count(h))
            row["alive"] = float(alive.sum()) + row["house"]
            row["eliminated"] = float(not np.isnan(self.eliminated_at[h]))
            for cause, counts in self.deaths.items():
                row[f"deaths_{cause}"] = float(counts[h])
            teams[h] = row

        def rank(h: int) -> tuple[float, ...]:
            r = teams[h]
            out = float(self.eliminated_at[h])
            if np.isnan(out):
                return (0.0, -r["honey"], -r["delivered"], -r["alive"], h)
            return (1.0, -out, -r["honey"], -r["delivered"], h)

        order = sorted(self._playing, key=rank)
        for place, h in enumerate(order, start=1):
            teams[h]["place"] = float(place)
        return ScoreBoard(teams=teams, winner=order[0] if order else None)

    def score_columns(self) -> list[ScoreColumn]:
        """Колонки таблицы серии (DECISIONS №66): худший матч — по месту, потом по мёду."""
        return [
            ScoreColumn("place", "место", worst="max"),
            ScoreColumn("honey", "мёд", worst="min"),
            ScoreColumn("delivered", "доставлено нектара"),
            ScoreColumn("alive", "живых пчёл"),
            ScoreColumn("deaths_energy", "гибели: энергия"),
            ScoreColumn("deaths_spider", "гибели: паук"),
        ]

    def is_finished(self) -> bool:
        """Досрочный конец: из ≥ 2 ульев остался один, или выбыл единственный (DECISIONS №40)."""
        if not self._playing:
            return False
        left = sum(1 for h in self._playing if np.isnan(self.eliminated_at[h]))
        return left <= 1 if len(self._playing) >= 2 else left == 0

    def describe(self) -> list[str]:
        """Какие эффекты включены (переключатели BEES_SPEC §6–7, DECISIONS №38)."""
        p = self.params
        w, sp = p.weather, p.enemies.spiders

        def on(flag: bool) -> str:
            return "вкл" if flag else "выкл"

        weather = (
            f"погода: {on(w.enabled)}"
            + (f" (ветер {on(w.wind)}, дождь {on(w.rain)}, старт {self.weather.state})"
               if w.enabled else "")
        )
        spiders = f"пауки: {on(sp.enabled)}" + (
            f" ({self.enemies.spider_flower.size} цветков из {self.world.flower_pos.shape[0]})"
            if sp.enabled else ""
        )
        return [weather, spiders]

    # --------------------------------------------------------------- DebugViewable

    def open_debug_viewer(self) -> DebugViewer:
        from swarmlab.bees.physics.viewer import MujocoDebugViewer

        a = self.bees.airborne
        return MujocoDebugViewer(self.backend, track_body=int(a[0]) if a.size else None)


def _resolve_script(script: str, source: Path | None) -> Path:
    """Путь к скрипту игрока: абсолютный, от текущей папки или от корня проекта.

    Корень проекта — папка над `configs/` (файл матча лежит в `configs/matches/`).
    """
    path = Path(script)
    if path.is_absolute() or path.exists() or source is None:
        return path.resolve()
    root = Path(source).resolve().parent.parent.parent
    candidate = root / path
    return candidate if candidate.exists() else path.resolve()


def quantize(pos: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Позиции `(K,3)` → `uint16` с фиксированной точкой в рамке `[lo, hi]` (DECISIONS №39)."""
    q = np.rint((np.asarray(pos).reshape(-1, 3) - lo) / (hi - lo) * _U16)
    return np.clip(q, 0, _U16).astype(np.uint16)


def dequantize(q: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Обратно к метрам `(K,3)` (ошибка ≤ половины шага рамки)."""
    return lo + np.asarray(q, dtype=np.float64).reshape(-1, 3) / _U16 * (hi - lo)


def _fraction_u8(value: np.ndarray, full: np.ndarray) -> np.ndarray:
    """Доля `value / full` в `uint8` 0–255 (при `full = 0` — 0)."""
    full = np.asarray(full, dtype=np.float64)
    f = np.divide(value, full, out=np.zeros_like(full), where=full > 0)
    return np.rint(np.clip(f, 0.0, 1.0) * 255).astype(np.uint8)
