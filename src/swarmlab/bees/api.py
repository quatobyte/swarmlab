"""API пчёлок: всё, что нужно, чтобы написать свой рой.

Как это устроено
----------------
* Мир живёт **тиками**: 10 раз в секунду каждая пчела получает свежие сенсоры
  (`Sensors`) и решает, что делать. Для этого у пчелы вызывается метод `step()`.
* Внутри `step()` пчела **вызывает команды**: `self.fly_to(...)`, `self.collect(...)`,
  `self.go_home()`… Если команд движения несколько — побеждает последняя.
  Если пчела ничего не вызвала — она продолжает прошлую команду.
* Пчела видит только то, что рядом (радиус обзора), а не всю карту.
* Пчёлы — обычные объекты Python: можно хранить память в `self`
  (`self.my_flower = ...`), она доживёт до следующего тика.
* Улей может принимать решения в функции `hive_step(hive)`: выводить новых
  пчёл, следить за мёдом.

Файл игрока
-----------
```python
from swarmlab.bees.api import Scout, Forager, Guard, HouseBee, Hive, Sensors


class MyForager(Forager):
    def step(self, s: Sensors):
        ...


def hive_step(hive: Hive):  # необязательно
    ...
```

Если не написать свой класс какого-то типа (или не переопределить `step()`),
пчёлы этого типа ведут себя «по умолчанию» — просто и не очень умно.

Единицы: метры, секунды, джоули. Ось `z` смотрит вверх.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple

#: Тип пчелы.
Kind = Literal["scout", "forager", "guard", "house"]
#: Погода.
Weather = Literal["clear", "windy", "rain"]
#: Задача домашней пчелы.
Task = Literal["rest", "process", "nurse"]

#: `from_id` сообщений, которые отправил сам улей (`hive.signal`).
HIVE_ID = -1

# Правила матча; раннер заполняет их перед загрузкой скрипта игрока.
_RULES: dict[str, Any] = {"advanced_control": False, "channels": 4, "max_values": 8}


# ===================================================================== векторы


class Vec(NamedTuple):
    """Точка или направление в пространстве: `x`, `y`, `z` (метры).

    Векторы можно складывать и вычитать (`a + b`, `a - b`), умножать на число
    (`v * 2`), узнавать длину (`v.length()`) и расстояние (`a.dist(b)`).
    """

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: Any) -> Vec:  # type: ignore[override]
        return Vec(self.x + other[0], self.y + other[1], self.z + other[2])

    def __sub__(self, other: Any) -> Vec:
        return Vec(self.x - other[0], self.y - other[1], self.z - other[2])

    def __mul__(self, k: Any) -> Vec:  # type: ignore[override]
        return Vec(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__  # type: ignore[assignment]

    def __truediv__(self, k: float) -> Vec:
        return Vec(self.x / k, self.y / k, self.z / k)

    def __neg__(self) -> Vec:
        return Vec(-self.x, -self.y, -self.z)

    def length(self) -> float:
        """Длина вектора."""
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def length_xy(self) -> float:
        """Длина по горизонтали (без высоты)."""
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vec:
        """Вектор той же направленности длиной 1 (нулевой остаётся нулевым)."""
        n = self.length()
        return self / n if n > 1e-12 else Vec(0.0, 0.0, 0.0)

    def dist(self, other: Any) -> float:
        """Расстояние до точки `other`."""
        return (self - other).length()

    def dist_xy(self, other: Any) -> float:
        """Расстояние до точки `other` по горизонтали."""
        return math.hypot(self.x - other[0], self.y - other[1])


# ===================================================================== сенсоры


@dataclass(slots=True)
class Me:
    """Что пчела знает о себе."""

    id: int  #: номер пчелы (у каждой свой, не меняется)
    kind: Kind  #: тип: "scout", "forager", "guard"
    pos: Vec  #: где я, м
    vel: Vec  #: моя скорость, м/с
    energy: float  #: сколько энергии осталось, Дж (0 — пчела падает)
    energy_max: float  #: полный запас энергии, Дж
    cargo: float  #: сколько нектара несу, ед.
    cargo_max: float  #: сколько нектара влезает, ед. (у сборщика 1.5, у остальных 0)
    in_hive: bool  #: я внутри улья (там заправляюсь и выгружаю нектар)
    alive: bool  #: жива ли пчела

    @property
    def energy_percent(self) -> float:
        """Запас энергии в процентах: 100 — полный, 0 — пустой."""
        return 100.0 * self.energy / self.energy_max if self.energy_max > 0 else 0.0

    @property
    def is_full(self) -> bool:
        """Груз полный — пора домой."""
        return self.cargo_max > 0 and self.cargo >= self.cargo_max - 1e-6


@dataclass(slots=True)
class Home:
    """Где мой улей. Пчела всегда знает дорогу домой."""

    pos: Vec  #: леток — вход в улей
    dir: Vec  #: направление на леток (длина 1)
    dist: float  #: расстояние до летка, м


@dataclass(slots=True)
class Flower:
    """Цветок, который видит пчела."""

    id: int  #: номер цветка — его передают в `collect()`
    pos: Vec  #: где цветок
    rel_pos: Vec  #: где цветок относительно меня
    dist: float  #: расстояние до цветка, м
    nectar: float  #: сколько в нём нектара, ед. (максимум 3)
    #: Сидит ли на цветке паук. Это видит только разведчик ближе 4 м;
    #: у остальных и издалека — `None` («не знаю»).
    spider: bool | None = None


@dataclass(slots=True)
class BeeInfo:
    """Другая пчела, которую я вижу (своя или чужая)."""

    id: int
    kind: Kind
    team: int  #: номер улья пчелы
    friend: bool  #: из моего улья
    pos: Vec
    rel_pos: Vec
    dist: float
    vel: Vec


@dataclass(slots=True)
class Enemy:
    """Враг рядом (шершень)."""

    id: int  #: номер врага — его передают в `intercept()`
    kind: str  #: "hornet"
    pos: Vec
    rel_pos: Vec
    dist: float
    vel: Vec


@dataclass(slots=True)
class Obstacle:
    """Препятствие рядом: дерево, камень, улей."""

    pos: Vec  #: ближайшая к пчеле точка оси препятствия
    rel_pos: Vec
    dist: float  #: расстояние до оси (до поверхности — `dist - radius`)
    radius: float


@dataclass(slots=True)
class Message:
    """Сообщение от своей пчелы (или улья), отправленное на прошлом тике."""

    from_id: int  #: кто отправил (`HIVE_ID` = -1 — сам улей)
    pos: Vec  #: откуда отправили
    rel_pos: Vec
    values: tuple[float, ...]  #: до 8 чисел — что в них значит, решаете вы


@dataclass(slots=True)
class Pheromones:
    """Запахи своего улья вокруг пчелы: 4 канала (0, 1, 2, 3).

    `values[i][j][c]` — сила запаха канала `c` в клетке 3×3 вокруг пчелы
    (`[1][1]` — клетка под пчелой); `gradient[c]` — куда запах усиливается.
    """

    values: list[list[list[float]]]
    gradient: list[list[float]]

    def strength(self, channel: int) -> float:
        """Сила запаха канала `channel` прямо под пчелой."""
        return self.values[1][1][channel]

    def direction(self, channel: int) -> Vec:
        """Направление, где запах канала `channel` сильнее (по горизонтали, длина 1)."""
        gx, gy = self.gradient[channel]
        return Vec(gx, gy, 0.0).normalized()


@dataclass(slots=True)
class Sensors:
    """Всё, что пчела знает на этом тике. Приходит в `step(self, s)`."""

    tick: int  #: номер тика (10 тиков в секунду)
    time: float  #: время матча, с
    me: Me  #: я сама
    home: Home  #: мой улей
    ground_z: float  #: высота земли подо мной, м
    airspeed: Vec  #: ветер в моей точке, м/с
    weather: Weather  #: погода: "clear", "windy", "rain"
    flowers: list[Flower]  #: цветы рядом (ближние — первыми)
    bees: list[BeeInfo]  #: пчёлы рядом
    enemies: list[Enemy]  #: враги рядом
    obstacles: list[Obstacle]  #: препятствия рядом
    messages: list[Message]  #: сообщения от своих
    pheromones: Pheromones  #: запахи своего улья

    def nearest_flower(self, min_nectar: float = 0.0) -> Flower | None:
        """Ближайший видимый цветок, где нектара не меньше `min_nectar`; `None` — нет такого."""
        best = None
        for f in self.flowers:
            if f.nectar >= min_nectar and (best is None or f.dist < best.dist):
                best = f
        return best

    def nearest_enemy(self) -> Enemy | None:
        """Ближайший видимый враг; `None` — врагов не видно."""
        return min(self.enemies, key=lambda e: e.dist, default=None)


@dataclass(slots=True)
class HornetMe:
    """Что шершень знает о себе."""

    id: int  #: номер шершня (пчёлы видят его в `enemies`)
    kind: str  #: всегда "hornet"
    pos: Vec
    vel: Vec
    hp: float  #: здоровье (0 — шершень погиб)
    hp_max: float
    #: Здоровья мало (меньше порога) — шершень больше не нападает и должен улетать за край.
    fleeing: bool


@dataclass(slots=True)
class HiveInfo:
    """Улей на карте (шершни знают, где ульи)."""

    team: int  #: номер улья
    pos: Vec  #: леток
    rel_pos: Vec
    dist: float


@dataclass(slots=True)
class HornetSensors:
    """Сенсоры шершня. Приходят в `step(self, s)` класса `Hornet`."""

    tick: int
    time: float
    me: HornetMe
    ground_z: float  #: высота земли подо мной, м
    bees: list[BeeInfo]  #: пчёлы рядом (ближние — первыми); `friend` всегда False
    hives: list[HiveInfo]  #: все ульи карты
    map_half_size: float  #: карта — квадрат от -map_half_size до +map_half_size по x и y

    def nearest_bee(self) -> BeeInfo | None:
        """Ближайшая видимая пчела; `None` — пчёл не видно."""
        return min(self.bees, key=lambda b: b.dist, default=None)


@dataclass(slots=True)
class SpiderMe:
    """Что паук знает о себе: он сидит на цветке и не двигается."""

    id: int
    kind: str  #: всегда "spider"
    flower_id: int  #: цветок, на котором сидит паук
    pos: Vec


@dataclass(slots=True)
class SpiderSensors:
    """Сенсоры паука. Приходят в `step(self, s)` класса `Spider`."""

    tick: int
    time: float
    me: SpiderMe
    #: Сборщики, которые прямо сейчас собирают нектар на моём цветке.
    prey: list[BeeInfo]


@dataclass(slots=True)
class Counts:
    """Сколько пчёл в улье. `counts.forager` — все живые сборщики."""

    scout: int = 0
    forager: int = 0
    guard: int = 0
    house: int = 0
    #: Сколько каждого типа сидит в улье: `in_hive["forager"]`.
    in_hive: dict[str, int] = field(default_factory=dict)
    #: Сколько каждого типа в полёте: `flying["scout"]`.
    flying: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Всего живых пчёл."""
        return self.scout + self.forager + self.guard + self.house


@dataclass(slots=True)
class Larva:
    """Личинка в очереди выведения."""

    kind: Kind
    left_s: float  #: сколько ещё расти (в секундах при одной няньке)


@dataclass(slots=True)
class HouseMe:
    """Что домашняя пчела знает о себе."""

    id: int
    kind: Kind  #: всегда "house"
    task: Task  #: чем занята сейчас: "rest", "process", "nurse"


@dataclass(slots=True)
class HouseSensors:
    """Сенсоры домашней пчелы: она живёт в улье и видит его склад."""

    tick: int
    time: float
    me: HouseMe
    hive_nectar: float  #: нектара на складе, ед.
    hive_honey: float  #: мёда на складе, ед.
    breeding_queue: list[Larva]  #: очередь выведения
    counts: Counts  #: сколько пчёл в улье


# ===================================================================== пчёлы


def _num(name: str, value: Any) -> float:
    """Проверить, что `value` — обычное число (не None, не NaN, не бесконечность)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} должно быть числом, а получено {value!r}")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name} должно быть обычным числом, а получено {value!r}")
    return v


def _opt(name: str, value: Any) -> float | None:
    return None if value is None else _num(name, value)


def _id(name: str, value: Any) -> int:
    """Номер цветка или врага: можно передать сам объект или его `id`."""
    value = getattr(value, "id", value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}: нужен номер (id) или сам объект, а получено {value!r}")
    return value


class _Agent:
    """Общая часть всех пчёл: буфер команд текущего тика."""

    kind: Kind

    def _commands(self) -> dict[str, Any]:
        cmd = self.__dict__.get("_swarmlab_cmd")
        if cmd is None:
            cmd = self.__dict__["_swarmlab_cmd"] = {}
        return cmd

    def _move(self, *op: Any) -> None:
        self._commands()["move"] = list(op)


class _Flyer(_Agent):
    """Общие команды движения всех, кто летает: пчёл и шершней."""

    def fly_to(
        self,
        x: float,
        y: float,
        z: float | None = None,
        speed: float | None = None,
        avoid: bool = True,
    ) -> None:
        """Лететь к точке `(x, y)`.

        * `z` — высота (абсолютная, м). Не задана — держаться в 5 м над землёй.
        * `speed` — скорость, м/с. Не задана — крейсерская для этой пчелы.
        * `avoid=False` — не облетать деревья и соседей (для своей навигации).

        Можно передать точку целиком: `self.fly_to(*flower.pos)`.
        """
        self._move(
            "fly_to", _num("x", x), _num("y", y), _opt("z", z), _opt("speed", speed),
            bool(avoid),
        )

    def fly_dir(self, dx: float, dy: float, dz: float = 0.0, speed: float | None = None) -> None:
        """Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."""
        dx, dy, dz = _num("dx", dx), _num("dy", dy), _num("dz", dz)
        if dx == 0 and dy == 0 and dz == 0:
            raise ValueError("fly_dir: направление (0, 0, 0) — непонятно, куда лететь")
        self._move("fly_dir", dx, dy, dz, _opt("speed", speed))

    def hover(self) -> None:
        """Зависнуть на месте."""
        self._move("hover")


class Bee(_Flyer):
    """Летающая пчела. Общие команды разведчика, сборщика и охранника.

    Команды движения (действует последняя вызванная за тик):
    `fly_to`, `fly_dir`, `hover`, `go_home`, `leave_hive`.
    Дополнительно (можно вместе с движением): `signal`, `mark`.

    Если пчела в улье, `fly_to`, `fly_dir`, `collect`, `intercept` и `thrust`
    сначала выводят её наружу (как `leave_hive`), а потом выполняются.
    `hover` и `go_home` в улье оставляют пчелу внутри.
    """

    def step(self, s: Sensors) -> None:
        """Решение пчелы на этом тике. Переопределите в своём классе."""

    # ----------------------------------------------------------------- движение

    def go_home(self) -> None:
        """Лететь к летку и войти в улей (там заправка и выгрузка нектара)."""
        self._move("go_home")

    def leave_hive(self) -> None:
        """Вылететь из улья (если пчела внутри)."""
        self._move("leave_hive")

    def thrust(self, fx: float, fy: float, fz: float) -> None:
        """Продвинутый режим: прямая сила тяги, Н. Автопилот выключается.

        Работает, только если в матче `advanced_control: true`. Тяга вниз не бывает,
        а слишком большая обрезается до максимальной для этой пчелы.
        """
        if not _RULES["advanced_control"]:
            raise RuntimeError("thrust() разрешена только в матче с advanced_control: true")
        self._move("thrust", _num("fx", fx), _num("fy", fy), _num("fz", fz))

    # ----------------------------------------------------------------- связь

    def signal(self, *values: float) -> None:
        """Сообщение до 8 чисел своим пчёлам в радиусе 15 м (дойдёт на следующем тике).

        Пример: `self.signal(1, flower.pos.x, flower.pos.y)`.
        """
        limit = _RULES["max_values"]
        if len(values) > limit:
            raise ValueError(f"signal(): не больше {limit} чисел, а передано {len(values)}")
        self._commands()["signal"] = [_num("signal", v) for v in values]

    def mark(self, channel: int, amount: float = 1.0) -> None:
        """Оставить запах (феромон) канала `channel` (0–3) в клетке под пчелой.

        Запах слабеет вдвое за минуту. Его чувствуют только пчёлы своего улья.
        """
        channels = _RULES["channels"]
        if isinstance(channel, bool) or not isinstance(channel, int) or not (
            0 <= channel < channels
        ):
            raise ValueError(f"mark(): канал от 0 до {channels - 1}, а получено {channel!r}")
        amount = _num("amount", amount)
        if amount < 0:
            raise ValueError("mark(): amount не может быть отрицательным")
        self._commands().setdefault("marks", []).append([channel, amount])


class Scout(Bee):
    """Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут.

    Ищет поляны с цветами и замечает пауков (ближе 4 м). Нектар не носит.

    Поведение по умолчанию: облетает случайные точки вокруг улья, при запасе
    энергии меньше 35% возвращается домой.
    """

    kind: Kind = "scout"

    def step(self, s: Sensors) -> None:
        _wander(self, s, radius=(15.0, 70.0), home_below=35.0)


class Forager(Bee):
    """Сборщик: носит нектар (до 1.5 ед.), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта.

    Дополнительные команды: `collect(flower)`, `unload()`. С грузом сборщик
    тяжелее и разгоняется медленнее.

    Поведение по умолчанию: летит к ближайшему цветку с нектаром и собирает,
    полный — домой, выгружает, заправляется и снова в путь. Если цветов не видно —
    ищет в случайных точках вокруг улья.
    """

    kind: Kind = "forager"

    def collect(self, flower: Flower | int) -> None:
        """Подлететь к цветку, зависнуть над ним и набирать нектар (0.25 ед./с).

        Набор идёт, пока груз не полный или цветок не пустой. Можно передать
        сам цветок или его номер: `self.collect(f)` или `self.collect(f.id)`.
        """
        self._move("collect", _id("collect", flower))

    def unload(self) -> None:
        """Выгрузить весь нектар на склад. Работает, только когда сборщик в улье."""
        self._move("unload")

    def step(self, s: Sensors) -> None:
        me = s.me
        mem = self.__dict__.setdefault("_base", {})
        if me.in_hive:
            if me.cargo > 0:
                self.unload()
            elif me.energy_percent > 80:
                self.leave_hive()
            return
        if me.is_full or me.energy_percent < 30:
            self.go_home()
            return
        flower = s.nearest_flower(min_nectar=0.3)
        if flower is not None:
            mem["field"] = flower.pos
            self.collect(flower)
            return
        field_pos = mem.get("field")
        if field_pos is not None:
            if me.pos.dist_xy(field_pos) > 3.0:
                self.fly_to(field_pos.x, field_pos.y)
                return
            mem.pop("field")  # поляна опустела — ищем другую
        _wander(self, s, radius=(15.0, 60.0), home_below=30.0)


class Guard(Bee):
    """Охранник: крупный и сильный (≈6 м/с), видит 12 м, летает ≈3 минуты.

    Дополнительная команда: `intercept(enemy)`. Против шершня охранники
    собираются по двое и больше — «тепловой шар».

    Поведение по умолчанию: патрулирует круг 8 м вокруг улья и бросается на
    ближайшего врага; энергии меньше 35% — домой.
    """

    kind: Kind = "guard"

    def intercept(self, target: Enemy | BeeInfo | int) -> None:
        """Преследовать цель с упреждением (лететь туда, где она будет)."""
        self._move("intercept", _id("intercept", target))

    def step(self, s: Sensors) -> None:
        me = s.me
        if me.in_hive:
            if me.energy_percent > 90:
                self.leave_hive()
            return
        if me.energy_percent < 35:
            self.go_home()
            return
        enemy = s.nearest_enemy()
        if enemy is not None:
            self.intercept(enemy)
            return
        mem = self.__dict__.setdefault("_base", {"angle": random.uniform(0, 2 * math.pi)})
        target = s.home.pos + Vec(math.cos(mem["angle"]), math.sin(mem["angle"]), 0.0) * 8.0
        if me.pos.dist_xy(target) < 2.0:
            mem["angle"] += 0.6
        self.fly_to(target.x, target.y)


class HouseBee(_Agent):
    """Домашняя пчела: не летает, живёт в улье.

    Команды: `process()` — перерабатывать нектар в мёд, `nurse()` — ухаживать
    за личинками (выведение быстрее), `rest()` — отдыхать.
    Каждая домашняя пчела ест 0.002 ед. мёда в секунду; без мёда не работает.

    Поведение по умолчанию: перерабатывает, если есть нектар; иначе нянчит
    личинки, если они есть; иначе отдыхает.
    """

    kind: Kind = "house"

    def step(self, s: HouseSensors) -> None:
        if s.hive_nectar > 0.05:
            self.process()
        elif s.breeding_queue:
            self.nurse()
        else:
            self.rest()

    def process(self) -> None:
        """Перерабатывать нектар в мёд (1 ед. нектара → 0.5 ед. мёда)."""
        self._move("process")

    def nurse(self) -> None:
        """Ухаживать за личинками: чем больше нянек, тем быстрее выведение."""
        self._move("nurse")

    def rest(self) -> None:
        """Отдыхать (мёд всё равно ест)."""
        self._move("rest")


# ===================================================================== враги


class Hornet(_Flyer):
    """Шершень: крупный (≈7 м/с), охотится на пчёл и грабит ульи.

    Так написаны встроенные боты (`swarmlab/bees/bots/hornet.py`). Команды:
    `fly_to`, `fly_dir`, `hover`, `intercept(bee)`. Укусы и грабёж происходят
    сами: шершень кусает пчелу, которой касается, и крадёт мёд у летка, если
    рядом нет охранников. Когда `s.me.fleeing`, он больше не нападает.

    Поведение по умолчанию: висит на месте.
    """

    kind: str = "hornet"

    def step(self, s: HornetSensors) -> None:
        """Решение шершня на этом тике. Переопределите в своём классе."""

    def intercept(self, target: BeeInfo | int) -> None:
        """Преследовать пчелу с упреждением (лететь туда, где она будет)."""
        self._move("intercept", _id("intercept", target))


class Spider(_Agent):
    """Паук: сидит на цветке и не двигается.

    Так написан встроенный бот (`swarmlab/bees/bots/spider.py`). Команда:
    `bite(bee)` — укусить сборщика из `s.prey`; укус смертелен не всегда
    (вероятность задаёт матч).

    Поведение по умолчанию: никого не кусает.
    """

    kind: str = "spider"

    def step(self, s: SpiderSensors) -> None:
        """Решение паука на этом тике. Переопределите в своём классе."""

    def bite(self, bee: BeeInfo | int) -> None:
        """Укусить сборщика, который собирает нектар на моём цветке."""
        self._commands().setdefault("bites", []).append(_id("bite", bee))


# ===================================================================== улей


class Hive:
    """Улей. Передаётся в `hive_step(hive)` каждый тик.

    Читать: `honey`, `nectar`, `counts`, `queue`, `max_bees`, `costs`, `messages`.
    Делать: `breed(kind)`, `cancel_breeding(kind)`, `signal(...)`.
    Помнить между тиками: словарь `memory`.
    """

    def __init__(self) -> None:
        self.tick: int = 0  #: номер тика
        self.time: float = 0.0  #: время матча, с
        self.honey: float = 0.0  #: мёд на складе, ед.
        self.nectar: float = 0.0  #: нектар на складе (ещё не переработан), ед.
        self.counts: Counts = Counts()  #: сколько пчёл
        self.queue: list[Larva] = []  #: очередь выведения
        self.max_bees: int = 0  #: больше этого пчёл (с личинками) быть не может
        #: Цена выведения в мёде: `costs["forager"]`.
        self.costs: dict[str, float] = {}
        #: Сообщения от своих пчёл рядом с летком (с прошлого тика).
        self.messages: list[Message] = []
        #: Память улья: кладите сюда что угодно, оно сохранится.
        self.memory: dict[str, Any] = {}
        self._swarmlab_cmd: dict[str, Any] = {}

    def breed(self, kind: Kind, n: int = 1) -> None:
        """Вывести `n` пчёл типа `kind` ("scout", "forager", "guard", "house").

        Мёд списывается сразу. Если мёда не хватает или улей полон — личинка
        не ставится (в лог придёт сообщение).
        """
        if kind not in ("scout", "forager", "guard", "house"):
            raise ValueError(
                f"breed(): тип пчелы — 'scout', 'forager', 'guard' или 'house', а не {kind!r}"
            )
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"breed(): n — целое число от 1, а получено {n!r}")
        self._swarmlab_cmd.setdefault("breed", []).append([kind, n])

    def cancel_breeding(self, kind: Kind) -> None:
        """Отменить последнюю личинку типа `kind` в очереди (мёд вернётся)."""
        if kind not in ("scout", "forager", "guard", "house"):
            raise ValueError(f"cancel_breeding(): нет такого типа пчелы: {kind!r}")
        self._swarmlab_cmd.setdefault("cancel", []).append(kind)

    def signal(self, *values: float) -> None:
        """Сообщение до 8 чисел всем своим пчёлам в радиусе 15 м от летка."""
        limit = _RULES["max_values"]
        if len(values) > limit:
            raise ValueError(f"signal(): не больше {limit} чисел, а передано {len(values)}")
        self._swarmlab_cmd["signal"] = [_num("signal", v) for v in values]


# ===================================================================== поведение по умолчанию


def _wander(bee: Bee, s: Sensors, radius: tuple[float, float], home_below: float) -> None:
    """Облёт случайных точек вокруг улья; мало энергии — домой."""
    me = s.me
    if me.in_hive:
        if me.energy_percent > 90:
            bee.leave_hive()
        return
    if me.energy_percent < home_below:
        bee.go_home()
        return
    mem = bee.__dict__.setdefault("_base", {})
    target = mem.get("wander")
    if target is None or me.pos.dist_xy(target) < 3.0:
        angle = random.uniform(0.0, 2.0 * math.pi)
        r = random.uniform(*radius)
        target = mem["wander"] = s.home.pos + Vec(math.cos(angle), math.sin(angle), 0.0) * r
    bee.fly_to(target.x, target.y)
