"""API пчёлок: всё, что нужно, чтобы написать свой рой.

Как это устроено
----------------
* Мир живёт **тиками**: 10 раз в секунду каждая пчела получает свежие сенсоры
  (`Sensors`) и решает, что делать. Для этого у пчелы вызывается метод `step()`.
* Внутри `step()` пчела **вызывает команды**: `self.fly_to(...)`, `self.collect(...)`,
  `self.go_home()`, `self.hover()`. Если команд движения несколько — побеждает последняя.
  Если пчела ничего не вызвала — она продолжает прошлую команду.
* Пчёлы договариваются между собой: `self.signal(...)` — сообщение соседям,
  `self.mark(...)` — запах на месте. Общей карты и общего командира нет.
* Пчела видит только то, что рядом (радиус обзора), а не всю карту.
* Пчёлы — обычные объекты Python: можно хранить память в `self`
  (`self.my_flower = ...`), она доживёт до следующего тика.
* Улей может принимать решения в функции `hive_step(hive)`: выводить новых
  пчёл, следить за мёдом. Домашние пчёлы работают сами: перерабатывают нектар
  и нянчат личинки.
* Ждать выполнения команды можно через `yield`: `ok = yield self.fly_to(x, y)` —
  пчела долетит (`True`) или не успеет за 60 с (`False`). `yield wait()` —
  подождать один тик, `yield wait(5)` — пять секунд. Процедуру с ожиданием
  вызывают так: `result = yield from self.my_trip(s)`.

Файл игрока
-----------
```python
from swarmlab.bees.api import Scout, Forager, Hive, Sensors


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

from swarmlab.core.program import Order, Wait

#: Тип пчелы.
Kind = Literal["scout", "forager", "house"]
#: Погода.
Weather = Literal["clear", "windy", "rain"]

#: `from_id` сообщений, которые отправил сам улей (`hive.signal`).
HIVE_ID = -1


# Правила матча; раннер заполняет их перед загрузкой скрипта игрока.
_RULES: dict[str, Any] = {"channels": 4, "max_values": 8}


# ===================================================================== ожидание


def wait(seconds: float = 0.0) -> Wait:
    """Подождать: `yield wait()` — один тик, `yield wait(5)` — 5 секунд игрового времени.

    Работает только с `yield` внутри `step()` или `hive_step()`. Пока пчела ждёт,
    она продолжает последнюю команду.
    """
    seconds = _num("seconds", seconds)
    if seconds < 0:
        raise ValueError("wait(): секунды не могут быть отрицательными")
    return Wait(seconds)


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
    kind: Kind  #: тип: "scout" или "forager"
    pos: Vec  #: где я, м
    vel: Vec  #: моя скорость, м/с
    energy: float  #: сколько энергии осталось, Дж (0 — пчела падает)
    energy_max: float  #: полный запас энергии, Дж
    cargo: float  #: сколько нектара несу, ед.
    cargo_max: float  #: сколько нектара влезает, ед. (у сборщика 1.5, у остальных 0)
    in_hive: bool  #: я внутри улья (там заправляюсь; нектар выгружается сам при входе)
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
    house: int = 0
    #: Сколько каждого типа сидит в улье: `in_hive["forager"]`.
    in_hive: dict[str, int] = field(default_factory=dict)
    #: Сколько каждого типа в полёте: `flying["scout"]`.
    flying: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Всего живых пчёл."""
        return self.scout + self.forager + self.house


@dataclass(slots=True)
class Larva:
    """Личинка в очереди выведения."""

    kind: Kind
    left_s: float  #: сколько ещё расти (в секундах при одной няньке)


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
    """Номер цветка или пчелы: можно передать сам объект или его `id`."""
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

    def _move(self, *op: Any, instant: bool = False) -> Order:
        move = list(op)
        self._commands()["move"] = move
        return Order(move, instant)


class Bee(_Agent):
    """Летающая пчела. Общие команды разведчика и сборщика.

    Команды движения (действует последняя вызванная за тик):
    `fly_to`, `hover`, `go_home`. Дополнительно (можно вместе с движением):
    `signal`, `mark`.

    Если пчела в улье, `fly_to` и `collect` сначала выводят её наружу, а потом
    выполняются. `hover` и `go_home` в улье оставляют пчелу внутри.
    """

    def step(self, s: Sensors) -> None:
        """Решение пчелы на этом тике. Переопределите в своём классе."""

    # ----------------------------------------------------------------- движение

    def fly_to(
        self,
        x: float,
        y: float,
        z: float | None = None,
        speed: float | None = None,
        avoid: bool = True,
    ) -> Order:
        """Лететь к точке `(x, y)`. Из улья пчела сначала вылетает.

        * `z` — высота (абсолютная, м). Не задана — держаться в 5 м над землёй.
        * `speed` — скорость, м/с. Не задана — крейсерская для этой пчелы.
        * `avoid=False` — не облетать деревья и соседей (для своей навигации).

        Можно передать точку целиком: `self.fly_to(*flower.pos)`.
        """
        return self._move(
            "fly_to", _num("x", x), _num("y", y), _opt("z", z), _opt("speed", speed),
            bool(avoid),
        )

    def hover(self) -> Order:
        """Зависнуть на месте (в улье — остаться внутри)."""
        return self._move("hover")

    def go_home(self) -> Order:
        """Лететь к летку и войти в улей: там нектар выгрузится сам, а пчела заправится."""
        return self._move("go_home")

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
        _wander(self, s, radius=(15.0, 70.0), home_below=35.0, leave_above=90.0)


class Forager(Bee):
    """Сборщик: носит нектар (до 1.5 ед.), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта.

    Дополнительная команда: `collect(flower)`. Нектар выгружается сам, когда
    сборщик входит в улей (`go_home`). С грузом сборщик тяжелее и разгоняется
    медленнее.

    Поведение по умолчанию: летит к ближайшему цветку с нектаром и собирает,
    полный — домой, заправляется и снова в путь. Если цветов не видно — ищет
    в случайных точках вокруг улья.
    """

    kind: Kind = "forager"

    def collect(self, flower: Flower | int) -> Order:
        """Подлететь к цветку, зависнуть над ним и набирать нектар (0.25 ед./с).

        Набор идёт, пока груз не полный или цветок не пустой. Из улья сборщик
        сначала вылетает. Можно передать сам цветок или его номер:
        `self.collect(f)` или `self.collect(f.id)`.
        """
        return self._move("collect", _id("collect", flower))

    def step(self, s: Sensors) -> None:
        me = s.me
        mem = self.__dict__.setdefault("_base", {})
        if me.in_hive:
            if me.energy_percent <= 80:
                return  # заправляется
        elif me.is_full or me.energy_percent < 30:
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
        _wander(self, s, radius=(15.0, 60.0), home_below=30.0, leave_above=80.0)


# ===================================================================== враги


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
    Делать: `breed(kind)`, `signal(...)`.
    Помнить между тиками: словарь `memory`.

    Домашние пчёлы работают сами: есть нектар — перерабатывают его в мёд,
    иначе нянчат личинки (выведение быстрее), иначе отдыхают.
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
        """Вывести `n` пчёл типа `kind` ("scout", "forager", "house").

        Мёд списывается сразу. Если мёда не хватает или улей полон — личинка
        не ставится (в лог придёт сообщение).
        """
        if kind not in ("scout", "forager", "house"):
            raise ValueError(
                f"breed(): тип пчелы — 'scout', 'forager' или 'house', а не {kind!r}"
            )
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"breed(): n — целое число от 1, а получено {n!r}")
        self._swarmlab_cmd.setdefault("breed", []).append([kind, n])

    def signal(self, *values: float) -> None:
        """Сообщение до 8 чисел всем своим пчёлам в радиусе 15 м от летка."""
        limit = _RULES["max_values"]
        if len(values) > limit:
            raise ValueError(f"signal(): не больше {limit} чисел, а передано {len(values)}")
        self._swarmlab_cmd["signal"] = [_num("signal", v) for v in values]


# ===================================================================== поведение по умолчанию


def _wander(
    bee: Bee, s: Sensors, radius: tuple[float, float], home_below: float, leave_above: float
) -> None:
    """Облёт случайных точек вокруг улья; мало энергии — домой."""
    me = s.me
    if me.in_hive:
        if me.energy_percent <= leave_above:
            return  # заправляется
    elif me.energy_percent < home_below:
        bee.go_home()
        return
    mem = bee.__dict__.setdefault("_base", {})
    target = mem.get("wander")
    if target is None or me.pos.dist_xy(target) < 3.0:
        angle = random.uniform(0.0, 2.0 * math.pi)
        r = random.uniform(*radius)
        target = mem["wander"] = s.home.pos + Vec(math.cos(angle), math.sin(angle), 0.0) * r
    bee.fly_to(target.x, target.y)
