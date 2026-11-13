"""API пчёлок: всё, что нужно, чтобы написать свой рой.

Как это устроено
----------------
* У каждой пчелы есть метод `loop()`. Игра вызывает его снова и снова, по кругу.
  Внутри пчела смотрит вокруг и даёт команды: `self.fly_to(...)`,
  `self.collect(...)`, `self.go_home()`.
* Команды движения **ждут**, пока пчела их выполнит: строка
  `self.fly_to(flower)` закончится, когда пчела долетит. Поэтому код читается
  как рассказ: «найди цветок, собери нектар, лети домой».
* Всё о пчеле — через `self`: `self.pos` (где я), `self.energy` (сколько энергии,
  %), `self.flowers` (цветы рядом). Эти данные можно только читать.
* Свою память храни в `self` под своими именами: `self.my_flower = flower`.
* Пчёлы договариваются: `self.say("цветы", flower)` — сообщение соседям,
  `self.heard` — что я услышала; `self.mark("red")` — запах на месте,
  `self.smell("red")` — чую ли запах. Общей карты и командира нет.
* Улей — класс `Hive` с тем же `loop()`: выводит пчёл (`hatch`), следит за
  мёдом и решает, когда пчёлам возвращаться домой (`set_home_energy`).

Файл игрока
-----------
```python
from swarmlab.bees.api import Collector, Hive, Scout


class MyScout(Scout):
    def loop(self):
        flower = self.explore()
        if flower:
            self.go_home()
            self.say("flowers", flower)


class MyCollector(Collector):
    def loop(self):
        ...


class MyHive(Hive):  # необязательно
    def loop(self):
        ...
```

Если не написать свой класс какого-то типа, пчёлы этого типа ведут себя «по
умолчанию» — просто и не очень умно.

Единицы: метры, секунды, энергия — проценты бака.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple, get_args

from swarmlab.core.program import Order, Wait, request

__all__ = ["Collector", "Flower", "Hive", "Message", "OtherBee", "Point", "Scout", "Worker"]

#: Цвет запаха (каналы феромонов 0–3).
_Color = Literal["red", "blue", "green", "yellow"]
_COLORS: tuple[str, ...] = get_args(_Color)
#: Тип пчелы для улья: класс `Scout`, `Collector` или `Worker` (или подкласс игрока).
_BeeType = type
#: `smell_way`: на столько метров вперёд точка в сторону запаха.
_SMELL_STEP = 5.0
#: Правила матча (`comms` в конфиге); хост заполняет их перед загрузкой скрипта игрока.
_RULES: dict[str, int] = {"max_word": 20, "max_say": 4}


# ===================================================================== точка


class Point(NamedTuple):
    """Точка на карте: `x`, `y` (и высота `z`), в метрах.

    Точки можно складывать и вычитать (`a + b`, `a - b`), умножать на число
    (`p * 2`), узнавать расстояние (`a.distance(b)`).
    """

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: Any) -> Point:  # type: ignore[override]
        o = _point("+", other)
        return Point(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, other: Any) -> Point:
        o = _point("-", other)
        return Point(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k: Any) -> Point:  # type: ignore[override]
        k = _num("*", k)
        return Point(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__  # type: ignore[assignment]

    def distance(self, other: Any) -> float:
        """Расстояние до точки, цветка или пчелы по карте (без высоты), м."""
        o = _point("distance", other)
        return math.hypot(self.x - o.x, self.y - o.y)


# ===================================================================== что видно


@dataclass(slots=True, eq=False)
class Flower:
    """Цветок, который видит пчела."""

    pos: Point  #: где цветок
    nectar: float  #: сколько в нём нектара (от 0 до 3)
    #: Сидит ли на цветке паук. Это видит только разведчик ближе 4 м;
    #: у остальных и издалека — `None` («не знаю»).
    spider: bool | None
    distance: float  #: как далеко от меня, м
    _id: int = field(default=-1, repr=False)


@dataclass(slots=True, eq=False)
class OtherBee:
    """Другая пчела, которую я вижу (своя или чужая)."""

    pos: Point  #: где она
    friend: bool  #: из моего улья
    distance: float  #: как далеко от меня, м
    _id: int = field(default=-1, repr=False)


@dataclass(slots=True, eq=False)
class Message:
    """Сообщение, которое я услышала от своей пчелы или улья."""

    word: str  #: слово
    where: Point | None  #: место, которое назвали (или `None`)
    from_where: Point  #: откуда сказали
    _from: int = field(default=-1, repr=False)


# ===================================================================== проверки


def _num(name: str, value: Any) -> float:
    """Проверить, что `value` — обычное число (не None, не NaN, не бесконечность)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}: нужно число, а получено {value!r}")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name}: нужно обычное число, а получено {value!r}")
    return v


def _point(name: str, target: Any, y: Any = None) -> Point:
    """Цель команды → точка: цветок, пчела, сообщение, точка или `x, y`."""
    if isinstance(target, (int, float)) and not isinstance(target, bool):
        if y is None:
            raise TypeError(f"{name}: после x нужен y — например, {name}(10, 20)")
        return Point(_num(name, target), _num(name, y))
    if y is not None:
        raise TypeError(f"{name}: y пишут только после числа x, а цель — {target!r}")
    if isinstance(target, Message):
        return target.where if target.where is not None else target.from_where
    if isinstance(target, (Flower, OtherBee)):
        return target.pos
    if isinstance(target, tuple) and len(target) in (2, 3):
        return Point(*(_num(name, v) for v in target))
    raise TypeError(
        f"{name}: куда? Нужна цель — цветок, пчела, сообщение, точка или x, y; "
        f"а получено {target!r}"
    )


def _speed(speed: Any) -> float | None:
    if speed is None:
        return None
    v = _num("speed", speed)
    if v <= 0:
        raise ValueError(f"speed: скорость больше нуля, а получено {speed!r}")
    return v


def _color(name: str, color: Any) -> int:
    if color not in _COLORS:
        raise ValueError(
            f"{name}: цвет запаха — {', '.join(repr(c) for c in _COLORS)}, а получено {color!r}"
        )
    return _COLORS.index(color)


def _percent(name: str, value: Any, top: float) -> float:
    v = _num(name, value)
    if not 0.0 <= v <= top:
        raise ValueError(f"{name}: от 0 до {top:g} (%), а получено {value!r}")
    return v


def _say(view: _View, word: Any, place: Any) -> None:
    if not isinstance(word, str) or not word.strip():
        raise TypeError(f"say: первым идёт слово в кавычках, например say(\"flowers\"), "
                        f"а получено {word!r}")
    word = word.strip()
    limit = _RULES["max_word"]
    if len(word) > limit:
        raise ValueError(f"say: слово не длиннее {limit} букв, а в {word!r} — {len(word)}")
    msg: list[Any] = [word]
    if place is not None:
        p = _point("say", place)
        msg += [p.x, p.y]
    said = view.cmd.setdefault("say", [])
    if len(said) >= _RULES["max_say"]:
        raise ValueError(f"say: не больше {_RULES['max_say']} сообщений за тик")
    said.append(msg)


def _wait(seconds: Any) -> None:
    s = _num("wait", seconds)
    if s < 0:
        raise ValueError("wait: секунды не могут быть отрицательными")
    request(Wait(s))


# ===================================================================== данные агента


class _View:
    """Что агент знает на этом тике. Заполняет хост раннера; игрок читает через свойства."""

    __slots__ = ("cache", "cmd", "heard", "raw", "team")

    def __init__(self, team: int = 0) -> None:
        self.raw: dict[str, Any] = {}
        self.team = team
        #: Команды без ожидания текущего прохода: `stop`, `say`, `mark`, `hatch`…
        self.cmd: dict[str, Any] = {}
        #: Услышанное (собирает хост, DECISIONS №87).
        self.heard: list[Message] = []
        self.cache: dict[str, Any] = {}

    def update(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.cache.clear()


_READONLY: dict[type, frozenset[str]] = {}


def _readonly_names(cls: type) -> frozenset[str]:
    """Имена данных и команд API у класса (их нельзя перезаписать через `self.имя = …`)."""
    names = _READONLY.get(cls)
    if names is None:
        names = _READONLY[cls] = frozenset(
            n for c in cls.__mro__ if c.__module__ == __name__
            for n in vars(c) if not n.startswith("_")
        )
    return names


class _Agent:
    """Общая часть пчёл и улья: данные только для чтения, `loop()`."""

    _swarmlab_view: _View
    _WHO = "пчелы"

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _readonly_names(type(self)):
            raise AttributeError(
                f"self.{name} — это данные {self._WHO}, их можно только читать. "
                f"Свои значения храни под своим именем, например self.my_{name} = …"
            )
        object.__setattr__(self, name, value)

    @property
    def _v(self) -> _View:
        try:
            return object.__getattribute__(self, "_swarmlab_view")
        except AttributeError:
            raise RuntimeError("Данные появятся, когда игра запустит пчелу") from None

    def loop(self) -> None:
        """Что делать. Игра вызывает `loop()` снова и снова. Переопредели в своём классе."""

    def wait(self, seconds: float = 0) -> None:
        """Подождать: `wait(5)` — 5 секунд, `wait()` — до следующего тика."""
        _wait(seconds)

    @property
    def time(self) -> float:
        """Сколько секунд идёт матч."""
        return float(self._v.raw["time"])

    @property
    def heard(self) -> list[Message]:
        """Что я услышала с прошлого прохода `loop()`: от каждого — последнее по каждому слову."""
        return list(self._v.heard)

    def say(self, word: str, place: Any = None) -> None:
        """Сказать своим в 15 м слово и (необязательно) место: `say("flowers", flower)`."""
        _say(self._v, word, place)


# ===================================================================== пчёлы


class _Flyer(_Agent):
    """Летающая пчела: общие данные и команды разведчика и сборщика."""

    # ----------------------------------------------------------------- я сама

    @property
    def pos(self) -> Point:
        """Где я."""
        return Point(*self._v.raw["me"]["pos"])

    @property
    def energy(self) -> float:
        """Сколько энергии осталось: 100 — полный бак, 0 — пчела падает."""
        me = self._v.raw["me"]
        return 100.0 * me["energy"] / me["energy_max"] if me["energy_max"] > 0 else 0.0

    @property
    def max_energy(self) -> float:
        """Размер моего бака, Дж (у каждой пчелы свой)."""
        return float(self._v.raw["me"]["energy_max"])

    @property
    def nectar(self) -> float:
        """Сколько нектара я несу (сборщик — до 1.5)."""
        return float(self._v.raw["me"]["cargo"])

    @property
    def is_full(self) -> bool:
        """Груз полный — пора домой."""
        me = self._v.raw["me"]
        return me["cargo_max"] > 0 and me["cargo"] >= me["cargo_max"] - 1e-6

    @property
    def at_home(self) -> bool:
        """Я дома, в улье (там нектар выгружается, а бак заправляется)."""
        return bool(self._v.raw["me"]["in_hive"])

    @property
    def home(self) -> Point:
        """Где вход в мой улей."""
        return Point(*self._v.raw["home"])

    # ----------------------------------------------------------------- вокруг

    @property
    def flowers(self) -> list[Flower]:
        """Цветы, которые я вижу (ближние — первыми)."""
        v = self._v
        got = v.cache.get("flowers")
        if got is None:
            px, py, _ = v.raw["me"]["pos"]
            got = v.cache["flowers"] = sorted(
                (Flower(Point(*f["pos"]), float(f["nectar"]), f.get("spider"),
                        math.hypot(f["pos"][0] - px, f["pos"][1] - py), int(f["id"]))
                 for f in v.raw["flowers"]),
                key=lambda f: f.distance,
            )
        return list(got)

    def nearest_flower(self, min_nectar: float = 0.0) -> Flower | None:
        """Ближайший цветок, где нектара не меньше `min_nectar`; `None` — такого не видно."""
        m = _num("min_nectar", min_nectar)
        return next((f for f in self.flowers if f.nectar >= m), None)

    @property
    def bees(self) -> list[OtherBee]:
        """Пчёлы, которых я вижу (ближние — первыми)."""
        v = self._v
        px, py, _ = v.raw["me"]["pos"]
        out = [
            OtherBee(Point(*b["pos"]), b["team"] == v.team,
                     math.hypot(b["pos"][0] - px, b["pos"][1] - py), int(b["id"]))
            for b in v.raw["bees"]
        ]
        out.sort(key=lambda b: b.distance)
        return out

    def smell(self, color: _Color) -> float:
        """Как сильно пахнет запахом цвета `color` прямо подо мной (0 — не пахнет)."""
        return float(self._v.raw["smell"][_color("smell", color)])

    def smell_way(self, color: _Color) -> Point | None:
        """Точка в 5 м от меня, где запах `color` сильнее; `None` — запаха рядом нет."""
        gx, gy = self._v.raw["smell_way"][_color("smell_way", color)]
        n = math.hypot(gx, gy)
        if n < 1e-9:
            return None
        p = self.pos
        return Point(p.x + gx / n * _SMELL_STEP, p.y + gy / n * _SMELL_STEP)

    # ----------------------------------------------------------------- команды

    def _go(self, *move: Any) -> Order:
        return Order(list(move))

    def _wait_move(self, *move: Any) -> Any:
        if self._v.raw["me"].get("auto_home"):
            return None  # пчела сама летит домой заправляться — команды не выполняются
        return request(self._go(*move))

    def fly_to(self, target: Any, y: float | None = None, *, speed: float | None = None) -> bool:
        """Лететь к цели и ждать, пока долечу. `True` — долетела, `False` — не вышло за 60 с.

        Цель — цветок, пчела, сообщение (его место), точка или `x, y`:
        `self.fly_to(flower)`, `self.fly_to(10, 20)`. Из улья пчела сначала вылетает.
        """
        p = _point("fly_to", target, y)
        out = self._wait_move("fly_to", p.x, p.y, _speed(speed))
        return bool(out and out.ok)

    def search(self, target: Any, y: float | None = None, *,
               speed: float | None = None) -> Flower | None:
        """Лететь к цели, но остановиться у первого цветка с нектаром, который увижу.

        Вернёт этот цветок или `None`, если по дороге цветов не было.
        """
        p = _point("search", target, y)
        return self._found(self._wait_move("search", p.x, p.y, _speed(speed)))

    def explore(self, *, speed: float | None = None) -> Flower | None:
        """Искать цветы: `search` к случайной точке вокруг дома. Цветок или `None`."""
        return self._found(self._wait_move("explore", _speed(speed)))

    def _found(self, out: Any) -> Flower | None:
        if not out or not out.ok or out.result < 0:
            return None
        found = self._v.raw["me"].get("found")
        if found is None:
            return None
        fid, x, y, z, nectar = found
        for f in self.flowers:
            if f._id == fid:
                return f
        return Flower(Point(x, y, z), float(nectar), None, self.pos.distance((x, y)), int(fid))

    def go_home(self, *, speed: float | None = None) -> bool:
        """Лететь домой и войти в улей: нектар выгрузится сам. `True` — я дома."""
        if self.at_home:
            return True
        out = self._wait_move("go_home", _speed(speed))
        return bool(out and out.ok)

    def refuel(self, level: float = 100) -> bool:
        """Заправиться дома до `level` % и только потом продолжать. Не дома — сначала домой."""
        level = _percent("refuel", level, 100.0)
        if not self.at_home and not self.go_home():
            return False
        if self.energy >= level - 1e-9:
            return True
        out = self._wait_move("refuel", level)
        return bool(out and out.ok)

    def stop(self) -> None:
        """Остановиться и висеть на месте (дома — остаться в улье). Не ждёт."""
        self._v.cmd["move"] = ["stop"]

    def mark(self, color: _Color) -> None:
        """Оставить запах цвета `color` на месте: "red", "blue", "green" или "yellow".

        Запах слабеет вдвое за минуту. Его чуют только пчёлы моего улья.
        """
        self._v.cmd.setdefault("marks", []).append([_color("mark", color), 1.0])


class Scout(_Flyer):
    """Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут.

    Ищет цветы и замечает пауков (ближе 4 м). Нектар не носит.

    Поведение по умолчанию: ищет цветы, нашёл — летит домой и рассказывает.
    """

    def loop(self) -> None:
        flower = self.explore()
        if flower:
            self.go_home()
            self.say("flowers", flower)


class Collector(_Flyer):
    """Сборщик: носит нектар (до 1.5), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта.

    Дома нектар выгружается сам. С грузом сборщик тяжелее и медленнее.

    Поведение по умолчанию: летит туда, где разведчик нашёл цветы (или ищет сам),
    собирает нектар, полный — домой.
    """

    def collect(self, target: Any, y: float | None = None, *,
                speed: float | None = None) -> bool:
        """Собирать нектар: с цветка или с ближайшего цветка у места. `True` — груз полный.

        `self.collect(flower)` — с этого цветка; `self.collect(message)` или
        `self.collect(10, 20)` — долететь и собирать с ближайшего цветка с нектаром
        у этого места (нет цветка — `False`).
        """
        if isinstance(target, Flower) and y is None:
            out = self._wait_move("collect", target._id, _speed(speed))
        else:
            p = _point("collect", target, y)
            out = self._wait_move("collect_at", p.x, p.y, _speed(speed))
        return bool(out and out.ok)

    def loop(self) -> None:
        news = [m for m in self.heard if m.word == "flowers" and m.where is not None]
        if news:
            self.collect(news[-1])
        else:
            flower = self.nearest_flower(min_nectar=0.3) or self.explore()
            if flower:
                self.collect(flower)
        if self.is_full:
            self.go_home()


class Worker:
    """Домашняя пчела: живёт в улье и работает сама — делает мёд из нектара и
    растит личинки. Кода у неё нет; её можно только вывести (`hatch(Worker)`)
    и посчитать (`count(Worker)`)."""


# ===================================================================== улей


def _kind(name: str, kind: Any) -> str:
    if isinstance(kind, type):
        if issubclass(kind, Scout):
            return "scout"
        if issubclass(kind, Collector):
            return "forager"
        if issubclass(kind, Worker):
            return "house"
    raise TypeError(f"{name}: тип пчелы — Scout, Collector или Worker, а получено {kind!r}")


class Hive(_Agent):
    """Улей: мёд, выведение пчёл, общие правила для пчёл.

    Домашние пчёлы (`Worker`) работают сами: есть нектар — делают мёд,
    иначе растят личинки.
    """

    _WHO = "улья"

    @property
    def honey(self) -> float:
        """Сколько мёда на складе (выведение в этом проходе уже вычтено)."""
        v = self._v
        return float(v.cache.get("honey", v.raw["honey"]))

    def count(self, kind: _BeeType) -> int:
        """Сколько живых пчёл типа `kind` (Scout, Collector или Worker)."""
        k = _kind("count", kind)
        c = self._v.raw["counts"]
        if k == "house":
            return int(c["house"])
        return int(c[k]["in_hive"]) + int(c[k]["flying"])

    def hatch(self, kind: _BeeType) -> bool:
        """Вывести пчелу типа `kind` за мёд. `True` — личинка в улье, `False` — мёда или места нет.

        Мёд списывается сразу, пчела родится через полминуты.
        """
        k = _kind("hatch", kind)
        v = self._v
        cost = float(v.raw["costs"][k])
        honey = v.cache.get("honey", float(v.raw["honey"]))
        busy = v.cache.get("busy", int(v.raw["busy"]))
        if honey < cost or busy >= int(v.raw["max_bees"]):
            return False
        v.cache["honey"], v.cache["busy"] = honey - cost, busy + 1
        v.cmd.setdefault("hatch", []).append(k)
        return True

    def set_home_energy(self, percent: float) -> None:
        """Ниже скольких % энергии пчела сама летит домой (0–90, сначала 30; 0 — никогда)."""
        self._v.cmd["home_energy"] = _percent("set_home_energy", percent, 90.0)

    def set_refuel_energy(self, percent: float) -> None:
        """До скольких % заправляется пчела, которая вернулась сама (сначала 100)."""
        self._v.cmd["refuel_energy"] = _percent("set_refuel_energy", percent, 100.0)
