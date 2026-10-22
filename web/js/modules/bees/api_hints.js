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
     "doc": "я внутри улья (там заправляюсь и выгружаю нектар)"
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
     "doc": "тип: \"scout\", \"forager\", \"guard\""
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
  "Enemy": {
   "doc": "Враг рядом (шершень).",
   "bases": [],
   "members": [
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": "номер врага — его передают в `intercept()`"
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "str",
     "doc": "\"hornet\""
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
     "name": "enemies",
     "kind": "field",
     "type": "list[Enemy]",
     "doc": "враги рядом"
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
     "name": "nearest_enemy",
     "kind": "method",
     "sig": "()",
     "type": "Enemy | None",
     "doc": "Ближайший видимый враг; `None` — врагов не видно."
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
  "HornetMe": {
   "doc": "Что шершень знает о себе.",
   "bases": [],
   "members": [
    {
     "name": "fleeing",
     "kind": "field",
     "type": "bool",
     "doc": "Здоровья мало (меньше порога) — шершень больше не нападает и должен улетать за край."
    },
    {
     "name": "hp",
     "kind": "field",
     "type": "float",
     "doc": "здоровье (0 — шершень погиб)"
    },
    {
     "name": "hp_max",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "id",
     "kind": "field",
     "type": "int",
     "doc": "номер шершня (пчёлы видят его в `enemies`)"
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "str",
     "doc": "всегда \"hornet\""
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    },
    {
     "name": "vel",
     "kind": "field",
     "type": "Vec",
     "doc": ""
    }
   ]
  },
  "HiveInfo": {
   "doc": "Улей на карте (шершни знают, где ульи).",
   "bases": [],
   "members": [
    {
     "name": "dist",
     "kind": "field",
     "type": "float",
     "doc": ""
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Vec",
     "doc": "леток"
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
     "doc": "номер улья"
    }
   ]
  },
  "HornetSensors": {
   "doc": "Сенсоры шершня. Приходят в `step(self, s)` класса `Hornet`.",
   "bases": [],
   "members": [
    {
     "name": "bees",
     "kind": "field",
     "type": "list[BeeInfo]",
     "doc": "пчёлы рядом (ближние — первыми); `friend` всегда False"
    },
    {
     "name": "ground_z",
     "kind": "field",
     "type": "float",
     "doc": "высота земли подо мной, м"
    },
    {
     "name": "hives",
     "kind": "field",
     "type": "list[HiveInfo]",
     "doc": "все ульи карты"
    },
    {
     "name": "map_half_size",
     "kind": "field",
     "type": "float",
     "doc": "карта — квадрат от -map_half_size до +map_half_size по x и y"
    },
    {
     "name": "me",
     "kind": "field",
     "type": "HornetMe",
     "doc": ""
    },
    {
     "name": "nearest_bee",
     "kind": "method",
     "sig": "()",
     "type": "BeeInfo | None",
     "doc": "Ближайшая видимая пчела; `None` — пчёл не видно."
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
     "name": "guard",
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
  "HouseMe": {
   "doc": "Что домашняя пчела знает о себе.",
   "bases": [],
   "members": [
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
     "doc": "всегда \"house\""
    },
    {
     "name": "task",
     "kind": "field",
     "type": "Task",
     "doc": "чем занята сейчас: \"rest\", \"process\", \"nurse\""
    }
   ]
  },
  "HouseSensors": {
   "doc": "Сенсоры домашней пчелы: она живёт в улье и видит его склад.",
   "bases": [],
   "members": [
    {
     "name": "breeding_queue",
     "kind": "field",
     "type": "list[Larva]",
     "doc": "очередь выведения"
    },
    {
     "name": "counts",
     "kind": "field",
     "type": "Counts",
     "doc": "сколько пчёл в улье"
    },
    {
     "name": "hive_honey",
     "kind": "field",
     "type": "float",
     "doc": "мёда на складе, ед."
    },
    {
     "name": "hive_nectar",
     "kind": "field",
     "type": "float",
     "doc": "нектара на складе, ед."
    },
    {
     "name": "me",
     "kind": "field",
     "type": "HouseMe",
     "doc": ""
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
  "Bee": {
   "doc": "Летающая пчела. Общие команды разведчика, сборщика и охранника.",
   "bases": [],
   "members": [
    {
     "name": "fly_dir",
     "kind": "method",
     "sig": "(dx, dy, dz=0.0, speed=None)",
     "type": "None",
     "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "None",
     "doc": "Лететь к точке `(x, y)`."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Лететь к летку и войти в улей (там заправка и выгрузка нектара)."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Зависнуть на месте."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "leave_hive",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Вылететь из улья (если пчела внутри)."
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
     "name": "thrust",
     "kind": "method",
     "sig": "(fx, fy, fz)",
     "type": "None",
     "doc": "Продвинутый режим: прямая сила тяги, Н. Автопилот выключается."
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
     "name": "fly_dir",
     "kind": "method",
     "sig": "(dx, dy, dz=0.0, speed=None)",
     "type": "None",
     "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "None",
     "doc": "Лететь к точке `(x, y)`."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Лететь к летку и войти в улей (там заправка и выгрузка нектара)."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Зависнуть на месте."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "leave_hive",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Вылететь из улья (если пчела внутри)."
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
     "name": "thrust",
     "kind": "method",
     "sig": "(fx, fy, fz)",
     "type": "None",
     "doc": "Продвинутый режим: прямая сила тяги, Н. Автопилот выключается."
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
     "type": "None",
     "doc": "Подлететь к цветку, зависнуть над ним и набирать нектар (0.25 ед./с)."
    },
    {
     "name": "fly_dir",
     "kind": "method",
     "sig": "(dx, dy, dz=0.0, speed=None)",
     "type": "None",
     "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "None",
     "doc": "Лететь к точке `(x, y)`."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Лететь к летку и войти в улей (там заправка и выгрузка нектара)."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Зависнуть на месте."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "leave_hive",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Вылететь из улья (если пчела внутри)."
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
     "name": "thrust",
     "kind": "method",
     "sig": "(fx, fy, fz)",
     "type": "None",
     "doc": "Продвинутый режим: прямая сила тяги, Н. Автопилот выключается."
    },
    {
     "name": "unload",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Выгрузить весь нектар на склад. Работает, только когда сборщик в улье."
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
  "Guard": {
   "doc": "Охранник: крупный и сильный (≈6 м/с), видит 12 м, летает ≈3 минуты.",
   "bases": [
    "Bee"
   ],
   "members": [
    {
     "name": "fly_dir",
     "kind": "method",
     "sig": "(dx, dy, dz=0.0, speed=None)",
     "type": "None",
     "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "None",
     "doc": "Лететь к точке `(x, y)`."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Лететь к летку и войти в улей (там заправка и выгрузка нектара)."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Зависнуть на месте."
    },
    {
     "name": "intercept",
     "kind": "method",
     "sig": "(target)",
     "type": "None",
     "doc": "Преследовать цель с упреждением (лететь туда, где она будет)."
    },
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "leave_hive",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Вылететь из улья (если пчела внутри)."
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
     "name": "thrust",
     "kind": "method",
     "sig": "(fx, fy, fz)",
     "type": "None",
     "doc": "Продвинутый режим: прямая сила тяги, Н. Автопилот выключается."
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
  "HouseBee": {
   "doc": "Домашняя пчела: не летает, живёт в улье.",
   "bases": [],
   "members": [
    {
     "name": "kind",
     "kind": "field",
     "type": "Kind",
     "doc": ""
    },
    {
     "name": "nurse",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Ухаживать за личинками: чем больше нянек, тем быстрее выведение."
    },
    {
     "name": "process",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Перерабатывать нектар в мёд (1 ед. нектара → 0.5 ед. мёда)."
    },
    {
     "name": "rest",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Отдыхать (мёд всё равно ест)."
    },
    {
     "name": "step",
     "kind": "override",
     "sig": "(s)",
     "type": "None",
     "doc": ""
    }
   ]
  },
  "Hornet": {
   "doc": "Шершень: крупный (≈7 м/с), охотится на пчёл и грабит ульи.",
   "bases": [],
   "members": [
    {
     "name": "fly_dir",
     "kind": "method",
     "sig": "(dx, dy, dz=0.0, speed=None)",
     "type": "None",
     "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(x, y, z=None, speed=None, avoid=True)",
     "type": "None",
     "doc": "Лететь к точке `(x, y)`."
    },
    {
     "name": "hover",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Зависнуть на месте."
    },
    {
     "name": "intercept",
     "kind": "method",
     "sig": "(target)",
     "type": "None",
     "doc": "Преследовать пчелу с упреждением (лететь туда, где она будет)."
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
     "doc": "Решение шершня на этом тике. Переопределите в своём классе."
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
     "doc": "Вывести `n` пчёл типа `kind` (\"scout\", \"forager\", \"guard\", \"house\")."
    },
    {
     "name": "cancel_breeding",
     "kind": "method",
     "sig": "(kind)",
     "type": "None",
     "doc": "Отменить последнюю личинку типа `kind` в очереди (мёд вернётся)."
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
   "name": "Task",
   "kind": "const",
   "doc": "Задача домашней пчелы."
  },
  {
   "name": "HIVE_ID",
   "kind": "const",
   "doc": "`from_id` сообщений, которые отправил сам улей (`hive.signal`)."
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
   "name": "Enemy",
   "kind": "class",
   "doc": "Враг рядом (шершень)."
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
   "name": "HornetMe",
   "kind": "class",
   "doc": "Что шершень знает о себе."
  },
  {
   "name": "HiveInfo",
   "kind": "class",
   "doc": "Улей на карте (шершни знают, где ульи)."
  },
  {
   "name": "HornetSensors",
   "kind": "class",
   "doc": "Сенсоры шершня. Приходят в `step(self, s)` класса `Hornet`."
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
   "name": "HouseMe",
   "kind": "class",
   "doc": "Что домашняя пчела знает о себе."
  },
  {
   "name": "HouseSensors",
   "kind": "class",
   "doc": "Сенсоры домашней пчелы: она живёт в улье и видит его склад."
  },
  {
   "name": "Bee",
   "kind": "class",
   "doc": "Летающая пчела. Общие команды разведчика, сборщика и охранника."
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
   "name": "Guard",
   "kind": "class",
   "doc": "Охранник: крупный и сильный (≈6 м/с), видит 12 м, летает ≈3 минуты."
  },
  {
   "name": "HouseBee",
   "kind": "class",
   "doc": "Домашняя пчела: не летает, живёт в улье."
  },
  {
   "name": "Hornet",
   "kind": "class",
   "doc": "Шершень: крупный (≈7 м/с), охотится на пчёл и грабит ульи."
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
