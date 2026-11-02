// Сгенерировано tools/gen_api_hints.py из src/swarmlab/bees/api.py — не править руками.
// Обновить: .venv\Scripts\python tools\gen_api_hints.py
export const API_HINTS = {
 "classes": {
  "Vec": {
   "doc": "Точка или направление в пространстве: `x`, `y`, `z` (метры).",
   "bases": [
    "NamedTuple"
   ],
   "members": [
    {
     "name": "dist",
     "kind": "method",
     "sig": "(other)",
     "type": "float",
     "doc": "Расстояние до точки `other`."
    },
    {
     "name": "dist_xy",
     "kind": "method",
     "sig": "(other)",
     "type": "float",
     "doc": "Расстояние до точки `other` по горизонтали."
    },
    {
     "name": "length",
     "kind": "method",
     "sig": "()",
     "type": "float",
     "doc": "Длина вектора."
    },
    {
     "name": "length_xy",
     "kind": "method",
     "sig": "()",
     "type": "float",
     "doc": "Длина по горизонтали (без высоты)."
    },
    {
     "name": "normalized",
     "kind": "method",
     "sig": "()",
     "type": "Vec",
     "doc": "Вектор той же направленности длиной 1 (нулевой остаётся нулевым)."
    },
    {
     "name": "x",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "y",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "z",
     "kind": "field",
     "type": "float",
     "doc": ""
    }
   ]
  },
  "Me": {
   "doc": "Что пчела знает о себе.",
   "bases": [],
   "members": [
    {
     "name": "alive",
     "kind": "field",
     "type": "bool",
     "doc": "жива ли пчела"
    },
    {
     "name": "cargo",
     "kind": "field",
     "type": "float",
     "doc": "сколько нектара несу, ед."
    },
    {
     "name": "cargo_max",
     "kind": "field",
     "type": "float",
     "doc": "сколько нектара влезает, ед. (у сборщика 1.5, у остальных 0)"
    },
    {
     "name": "energy",
     "kind": "field",
     "type": "float",
     "doc": "сколько энергии осталось, Дж (0 — пчела падает)"
    },
    {
     "name": "energy_max",
     "kind": "field",
     "type": "float",
     "doc": "полный запас энергии, Дж"
    },
    {
     "name": "energy_percent",
     "kind": "property",
     "type": "float",
     "doc": "Запас энергии в процентах: 100 — полный, 0 — пустой."
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": "номер пчелы (у каждой свой, не меняется)"
    },
    {
     "name": "in_hive",
     "kind": "field",
     "type": "bool",
     "doc": "я внутри улья (там заправляюсь; нектар выгружается сам при входе)"
    },
    {
     "name": "is_full",
     "kind": "property",
     "type": "bool",
     "doc": "Груз полный — пора домой."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": "тип: \"scout\" или \"forager\""
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "где я, м"
    },
    {
     "name": "vel",
     "kind": "field",
     "type": "Vec",
     "doc": "моя скорость, м/с"
    }
   ]
  },
  "Home": {
   "doc": "Где мой улей. Пчела всегда знает дорогу домой.",
   "bases": [],
   "members": [
    {
     "name": "dir",
     "kind": "field",
     "type": "Vec",
     "doc": "направление на леток (длина 1)"
    },
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": "расстояние до летка, м"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "леток — вход в улей"
    }
   ]
  },
  "Flower": {
   "doc": "Цветок, который видит пчела.",
   "bases": [],
   "members": [
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": "расстояние до цветка, м"
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": "номер цветка — его передают в `collect()`"
    },
    {
     "name": "nectar",
     "kind": "field",
     "type": "float",
     "doc": "сколько в нём нектара, ед. (максимум 3)"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "где цветок"
    },
    {
     "name": "rel_pos",
     "kind": "field",
     "type": "Vec",
     "doc": "где цветок относительно меня"
    },
    {
     "name": "spider",
     "kind": "field",
     "type": "bool | None",
     "doc": "у остальных и издалека — `None` («не знаю»)."
    }
   ]
  },
  "BeeInfo": {
   "doc": "Другая пчела, которую я вижу (своя или чужая).",
   "bases": [],
   "members": [
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "friend",
     "kind": "field",
     "type": "bool",
     "doc": "из моего улья"
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    },
    {
     "name": "rel_pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    },
    {
     "name": "team",
     "kind": "field",
     "type": "int",
     "doc": "номер улья пчелы"
    },
    {
     "name": "vel",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    }
   ]
  },
  "Obstacle": {
   "doc": "Препятствие рядом: дерево, камень, улей.",
   "bases": [],
   "members": [
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": "расстояние до оси (до поверхности — `dist - radius`)"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "ближайшая к пчеле точка оси препятствия"
    },
    {
     "name": "radius",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "rel_pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    }
   ]
  },
  "Message": {
   "doc": "Сообщение от своей пчелы (или улья), отправленное на прошлом тике.",
   "bases": [],
   "members": [
    {
     "name": "from_id",
     "kind": "field",
     "type": "int",
     "doc": "кто отправил (`HIVE_ID` = -1 — сам улей)"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "откуда отправили"
    },
    {
     "name": "rel_pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    },
    {
     "name": "values",
     "kind": "field",
     "type": "tuple[float, ...]",
     "doc": "до 8 чисел — что в них значит, решаете вы"
    }
   ]
  },
  "Pheromones": {
   "doc": "Запахи своего улья вокруг пчелы: 4 канала (0, 1, 2, 3).",
   "bases": [],
   "members": [
    {
     "name": "direction",
     "kind": "method",
     "sig": "(channel)",
     "type": "Vec",
     "doc": "Направление, где запах канала `channel` сильнее (по горизонтали, длина 1)."
    },
    {
     "name": "gradient",
     "kind": "field",
     "type": "list[list[float]]",
     "doc": ""
    },
    {
     "name": "strength",
     "kind": "method",
     "sig": "(channel)",
     "type": "float",
     "doc": "Сила запаха канала `channel` прямо под пчелой."
    },
    {
     "name": "values",
     "kind": "field",
     "type": "list[list[list[float]]]",
     "doc": ""
    }
   ]
  },
  "Sensors": {
   "doc": "Всё, что пчела знает на этом тике. Приходит в `step(self, s)`.",
   "bases": [],
   "members": [
    {
     "name": "airspeed",
     "kind": "field",
     "type": "Vec",
     "doc": "ветер в моей точке, м/с"
    },
    {
     "name": "bees",
     "kind": "field",
     "type": "list[BeeInfo]",
     "doc": "пчёлы рядом"
    },
    {
     "name": "flowers",
     "kind": "field",
     "type": "list[Flower]",
     "doc": "цветы рядом (ближние — первыми)"
    },
    {
     "name": "ground_z",
     "kind": "field",
     "type": "float",
     "doc": "высота земли подо мной, м"
    },
    {
     "name": "home",
     "kind": "field",
     "type": "Home",
     "doc": "мой улей"
    },
    {
     "name": "me",
     "kind": "field",
     "type": "Me",
     "doc": "я сама"
    },
    {
     "name": "messages",
     "kind": "field",
     "type": "list[Message]",
     "doc": "сообщения от своих"
    },
    {
     "name": "nearest_flower",
     "kind": "method",
     "sig": "(min_nectar=0.0)",
     "type": "Flower | None",
     "doc": "Ближайший видимый цветок, где нектара не меньше `min_nectar`; `None` — нет такого."
    },
    {
     "name": "obstacles",
     "kind": "field",
     "type": "list[Obstacle]",
     "doc": "препятствия рядом"
    },
    {
     "name": "pheromones",
     "kind": "field",
     "type": "Pheromones",
     "doc": "запахи своего улья"
    },
    {
     "name": "tick",
     "kind": "field",
     "type": "int",
     "doc": "номер тика (10 тиков в секунду)"
    },
    {
     "name": "time",
     "kind": "field",
     "type": "float",
     "doc": "время матча, с"
    },
    {
     "name": "weather",
     "kind": "field",
     "type": "Weather",
     "doc": "погода: \"clear\", \"windy\", \"rain\""
    }
   ]
  },
  "SpiderMe": {
   "doc": "Что паук знает о себе: он сидит на цветке и не двигается.",
   "bases": [],
   "members": [
    {
     "name": "flower_id",
     "kind": "field",
     "type": "int",
     "doc": "цветок, на котором сидит паук"
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "str",
     "doc": "всегда \"spider\""
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    }
   ]
  },
  "SpiderSensors": {
   "doc": "Сенсоры паука. Приходят в `step(self, s)` класса `Spider`.",
   "bases": [],
   "members": [
    {
     "name": "me",
     "kind": "field",
     "type": "SpiderMe",
     "doc": ""
    },
    {
     "name": "prey",
     "kind": "field",
     "type": "list[BeeInfo]",
     "doc": "Сборщики, которые прямо сейчас собирают нектар на моём цветке."
    },
    {
     "name": "tick",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "time",
     "kind": "field",
     "type": "float",
     "doc": ""
    }
   ]
  },
  "Counts": {
   "doc": "Сколько пчёл в улье. `counts.forager` — все живые сборщики.",
   "bases": [],
   "members": [
    {
     "name": "flying",
     "kind": "field",
     "type": "dict[str, int]",
     "doc": "Сколько каждого типа в полёте: `flying[\"scout\"]`."
    },
    {
     "name": "forager",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "house",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "in_hive",
     "kind": "field",
     "type": "dict[str, int]",
     "doc": "Сколько каждого типа сидит в улье: `in_hive[\"forager\"]`."
    },
    {
     "name": "scout",
     "kind": "field",
     "type": "int",
     "doc": ""
    },
    {
     "name": "total",
     "kind": "property",
     "type": "int",
     "doc": "Всего живых пчёл."
    }
   ]
  },
  "Larva": {
   "doc": "Личинка в очереди выведения.",
   "bases": [],
   "members": [
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "left_s",
     "kind": "field",
     "type": "float",
     "doc": "сколько ещё расти (в секундах при одной няньке)"
    }
   ]
  },
  "Bee": {
   "doc": "Летающая пчела. Общие команды разведчика и сборщика.",
   "bases": [],
   "members": [
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "Order",
     "doc": "Лететь к точке `(x, y)`. Из улья пчела сначала вылетает."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Лететь к летку и войти в улей: там нектар выгрузится сам, а пчела заправится."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Зависнуть на месте (в улье — остаться внутри)."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "mark",
     "kind": "method",
     "sig": "(channel, amount=1.0)",
     "type": "None",
     "doc": "Оставить запах (феромон) канала `channel` (0–3) в клетке под пчелой."
    },
    {
     "name": "signal",
     "kind": "method",
     "sig": "(*values)",
     "type": "None",
     "doc": "Сообщение до 8 чисел своим пчёлам в радиусе 15 м (дойдёт на следующем тике)."
    },
    {
     "name": "step",
     "kind": "override",
     "sig": "(s)",
     "type": "None",
     "doc": "Решение пчелы на этом тике. Переопределите в своём классе."
    }
   ]
  },
  "Scout": {
   "doc": "Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут.",
   "bases": [
    "Bee"
   ],
   "members": [
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "Order",
     "doc": "Лететь к точке `(x, y)`. Из улья пчела сначала вылетает."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Лететь к летку и войти в улей: там нектар выгрузится сам, а пчела заправится."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Зависнуть на месте (в улье — остаться внутри)."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "mark",
     "kind": "method",
     "sig": "(channel, amount=1.0)",
     "type": "None",
     "doc": "Оставить запах (феромон) канала `channel` (0–3) в клетке под пчелой."
    },
    {
     "name": "signal",
     "kind": "method",
     "sig": "(*values)",
     "type": "None",
     "doc": "Сообщение до 8 чисел своим пчёлам в радиусе 15 м (дойдёт на следующем тике)."
    },
    {
     "name": "step",
     "kind": "override",
     "sig": "(s)",
     "type": "None",
     "doc": "Решение пчелы на этом тике. Переопределите в своём классе."
    }
   ]
  },
  "Forager": {
   "doc": "Сборщик: носит нектар (до 1.5 ед.), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта.",
   "bases": [
    "Bee"
   ],
   "members": [
    {
     "name": "collect",
     "kind": "method",
     "sig": "(flower)",
     "type": "Order",
     "doc": "Подлететь к цветку, зависнуть над ним и набирать нектар (0.25 ед./с)."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "Order",
     "doc": "Лететь к точке `(x, y)`. Из улья пчела сначала вылетает."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Лететь к летку и войти в улей: там нектар выгрузится сам, а пчела заправится."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "Order",
     "doc": "Зависнуть на месте (в улье — остаться внутри)."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "mark",
     "kind": "method",
     "sig": "(channel, amount=1.0)",
     "type": "None",
     "doc": "Оставить запах (феромон) канала `channel` (0–3) в клетке под пчелой."
    },
    {
     "name": "signal",
     "kind": "method",
     "sig": "(*values)",
     "type": "None",
     "doc": "Сообщение до 8 чисел своим пчёлам в радиусе 15 м (дойдёт на следующем тике)."
    },
    {
     "name": "step",
     "kind": "override",
     "sig": "(s)",
     "type": "None",
     "doc": "Решение пчелы на этом тике. Переопределите в своём классе."
    }
   ]
  },
  "Spider": {
   "doc": "Паук: сидит на цветке и не двигается.",
   "bases": [],
   "members": [
    {
     "name": "bite",
     "kind": "method",
     "sig": "(bee)",
     "type": "None",
     "doc": "Укусить сборщика, который собирает нектар на моём цветке."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "step",
     "kind": "override",
     "sig": "(s)",
     "type": "None",
     "doc": "Решение паука на этом тике. Переопределите в своём классе."
    }
   ]
  },
  "Hive": {
   "doc": "Улей. Передаётся в `hive_step(hive)` каждый тик.",
   "bases": [],
   "members": [
    {
     "name": "breed",
     "kind": "method",
     "sig": "(kind, n=1)",
     "type": "None",
     "doc": "Вывести `n` пчёл типа `kind` (\"scout\", \"forager\", \"house\")."
    },
    {
     "name": "costs",
     "kind": "field",
     "type": "dict[str, float]",
     "doc": "Цена выведения в мёде: `costs[\"forager\"]`."
    },
    {
     "name": "counts",
     "kind": "field",
     "type": "Counts",
     "doc": "сколько пчёл"
    },
    {
     "name": "honey",
     "kind": "field",
     "type": "float",
     "doc": "мёд на складе, ед."
    },
    {
     "name": "max_bees",
     "kind": "field",
     "type": "int",
     "doc": "больше этого пчёл (с личинками) быть не может"
    },
    {
     "name": "memory",
     "kind": "field",
     "type": "dict[str, Any]",
     "doc": "Память улья: кладите сюда что угодно, оно сохранится."
    },
    {
     "name": "messages",
     "kind": "field",
     "type": "list[Message]",
     "doc": "Сообщения от своих пчёл рядом с летком (с прошлого тика)."
    },
    {
     "name": "nectar",
     "kind": "field",
     "type": "float",
     "doc": "нектар на складе (ещё не переработан), ед."
    },
    {
     "name": "queue",
     "kind": "field",
     "type": "list[Larva]",
     "doc": "очередь выведения"
    },
    {
     "name": "signal",
     "kind": "method",
     "sig": "(*values)",
     "type": "None",
     "doc": "Сообщение до 8 чисел всем своим пчёлам в радиусе 15 м от летка."
    },
    {
     "name": "tick",
     "kind": "field",
     "type": "int",
     "doc": "номер тика"
    },
    {
     "name": "time",
     "kind": "field",
     "type": "float",
     "doc": "время матча, с"
    }
   ]
  }
 },
 "globals": [
  {
   "name": "Kind",
   "kind": "const",
   "doc": "Тип пчелы."
  },
  {
   "name": "Weather",
   "kind": "const",
   "doc": "Погода."
  },
  {
   "name": "HIVE_ID",
   "kind": "const",
   "doc": "`from_id` сообщений, которые отправил сам улей (`hive.signal`)."
  },
  {
   "name": "wait",
   "kind": "function",
   "doc": "Подождать: `yield wait()` — один тик, `yield wait(5)` — 5 секунд игрового времени."
  },
  {
   "name": "Vec",
   "kind": "class",
   "doc": "Точка или направление в пространстве: `x`, `y`, `z` (метры)."
  },
  {
   "name": "Me",
   "kind": "class",
   "doc": "Что пчела знает о себе."
  },
  {
   "name": "Home",
   "kind": "class",
   "doc": "Где мой улей. Пчела всегда знает дорогу домой."
  },
  {
   "name": "Flower",
   "kind": "class",
   "doc": "Цветок, который видит пчела."
  },
  {
   "name": "BeeInfo",
   "kind": "class",
   "doc": "Другая пчела, которую я вижу (своя или чужая)."
  },
  {
   "name": "Obstacle",
   "kind": "class",
   "doc": "Препятствие рядом: дерево, камень, улей."
  },
  {
   "name": "Message",
   "kind": "class",
   "doc": "Сообщение от своей пчелы (или улья), отправленное на прошлом тике."
  },
  {
   "name": "Pheromones",
   "kind": "class",
   "doc": "Запахи своего улья вокруг пчелы: 4 канала (0, 1, 2, 3)."
  },
  {
   "name": "Sensors",
   "kind": "class",
   "doc": "Всё, что пчела знает на этом тике. Приходит в `step(self, s)`."
  },
  {
   "name": "SpiderMe",
   "kind": "class",
   "doc": "Что паук знает о себе: он сидит на цветке и не двигается."
  },
  {
   "name": "SpiderSensors",
   "kind": "class",
   "doc": "Сенсоры паука. Приходят в `step(self, s)` класса `Spider`."
  },
  {
   "name": "Counts",
   "kind": "class",
   "doc": "Сколько пчёл в улье. `counts.forager` — все живые сборщики."
  },
  {
   "name": "Larva",
   "kind": "class",
   "doc": "Личинка в очереди выведения."
  },
  {
   "name": "Bee",
   "kind": "class",
   "doc": "Летающая пчела. Общие команды разведчика и сборщика."
  },
  {
   "name": "Scout",
   "kind": "class",
   "doc": "Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут."
  },
  {
   "name": "Forager",
   "kind": "class",
   "doc": "Сборщик: носит нектар (до 1.5 ед.), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта."
  },
  {
   "name": "Spider",
   "kind": "class",
   "doc": "Паук: сидит на цветке и не двигается."
  },
  {
   "name": "Hive",
   "kind": "class",
   "doc": "Улей. Передаётся в `hive_step(hive)` каждый тик."
  }
 ]
};
