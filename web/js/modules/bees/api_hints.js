// Сгенерировано tools/gen_api_hints.py из src/swarmlab/bees/api.py — не править руками.
// Обновить: .venv\Scripts\python tools\gen_api_hints.py
export const API_HINTS = {
 "classes": {
  "Point": {
   "doc": "Точка на карте: `x`, `y` (и высота `z`), в метрах.",
   "bases": [
    "NamedTuple"
   ],
   "members": [
    {
     "name": "distance",
     "kind": "method",
     "sig": "(other)",
     "type": "float",
     "doc": "Расстояние до точки, цветка или пчелы по карте (без высоты), м."
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
  "Flower": {
   "doc": "Цветок, который видит пчела.",
   "bases": [],
   "members": [
    {
     "name": "distance",
     "kind": "field",
     "type": "float",
     "doc": "как далеко от меня, м"
    },
    {
     "name": "nectar",
     "kind": "field",
     "type": "float",
     "doc": "сколько в нём нектара (от 0 до 3)"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Point",
     "doc": "где цветок"
    },
    {
     "name": "spider",
     "kind": "field",
     "type": "bool | None",
     "doc": "у остальных и издалека — `None` («не знаю»)."
    }
   ]
  },
  "OtherBee": {
   "doc": "Другая пчела, которую я вижу (своя или чужая).",
   "bases": [],
   "members": [
    {
     "name": "distance",
     "kind": "field",
     "type": "float",
     "doc": "как далеко от меня, м"
    },
    {
     "name": "friend",
     "kind": "field",
     "type": "bool",
     "doc": "из моего улья"
    },
    {
     "name": "pos",
     "kind": "field",
     "type": "Point",
     "doc": "где она"
    }
   ]
  },
  "Message": {
   "doc": "Сообщение, которое я услышала от своей пчелы или улья.",
   "bases": [],
   "members": [
    {
     "name": "from_where",
     "kind": "field",
     "type": "Point",
     "doc": "откуда сказали"
    },
    {
     "name": "where",
     "kind": "field",
     "type": "Point | None",
     "doc": "место, которое назвали (или `None`)"
    },
    {
     "name": "word",
     "kind": "field",
     "type": "str",
     "doc": "слово"
    }
   ]
  },
  "Scout": {
   "doc": "Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут.",
   "bases": [],
   "members": [
    {
     "name": "at_home",
     "kind": "property",
     "type": "bool",
     "doc": "Я дома, в улье (там нектар выгружается, а бак заправляется)."
    },
    {
     "name": "bees",
     "kind": "property",
     "type": "list[OtherBee]",
     "doc": "Пчёлы, которых я вижу (ближние — первыми)."
    },
    {
     "name": "energy",
     "kind": "property",
     "type": "float",
     "doc": "Сколько энергии осталось: 100 — полный бак, 0 — пчела падает."
    },
    {
     "name": "explore",
     "kind": "method",
     "sig": "(speed=None)",
     "type": "Flower | None",
     "doc": "Искать цветы: `search` к случайной точке вокруг дома. Цветок или `None`."
    },
    {
     "name": "flowers",
     "kind": "property",
     "type": "list[Flower]",
     "doc": "Цветы, которые я вижу (ближние — первыми)."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(target, y=None, speed=None)",
     "type": "bool",
     "doc": "Лететь к цели и ждать, пока долечу. `True` — долетела, `False` — не вышло за 60 с."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "(speed=None)",
     "type": "bool",
     "doc": "Лететь домой и войти в улей: нектар выгрузится сам. `True` — я дома."
    },
    {
     "name": "heard",
     "kind": "property",
     "type": "list[Message]",
     "doc": "Что я услышала с прошлого прохода `loop()`: от каждого — последнее по каждому слову."
    },
    {
     "name": "home",
     "kind": "property",
     "type": "Point",
     "doc": "Где вход в мой улей."
    },
    {
     "name": "is_full",
     "kind": "property",
     "type": "bool",
     "doc": "Груз полный — пора домой."
    },
    {
     "name": "mark",
     "kind": "method",
     "sig": "(color)",
     "type": "None",
     "doc": "Оставить запах цвета `color` на месте: \"red\", \"blue\", \"green\" или \"yellow\"."
    },
    {
     "name": "max_energy",
     "kind": "property",
     "type": "float",
     "doc": "Размер моего бака, Дж (у каждой пчелы свой)."
    },
    {
     "name": "nearest_flower",
     "kind": "method",
     "sig": "(min_nectar=0.0)",
     "type": "Flower | None",
     "doc": "Ближайший цветок, где нектара не меньше `min_nectar`; `None` — такого не видно."
    },
    {
     "name": "nectar",
     "kind": "property",
     "type": "float",
     "doc": "Сколько нектара я несу (сборщик — до 1.5)."
    },
    {
     "name": "pos",
     "kind": "property",
     "type": "Point",
     "doc": "Где я."
    },
    {
     "name": "refuel",
     "kind": "method",
     "sig": "(level=100)",
     "type": "bool",
     "doc": "Заправиться дома до `level` % и только потом продолжать. Не дома — сначала домой."
    },
    {
     "name": "say",
     "kind": "method",
     "sig": "(word, place=None)",
     "type": "None",
     "doc": "Сказать своим в 15 м слово и (необязательно) место: `say(\"flowers\", flower)`."
    },
    {
     "name": "search",
     "kind": "method",
     "sig": "(target, y=None, speed=None)",
     "type": "Flower | None",
     "doc": "Лететь к цели, но остановиться у первого цветка с нектаром, который увижу."
    },
    {
     "name": "smell",
     "kind": "method",
     "sig": "(color)",
     "type": "float",
     "doc": "Как сильно пахнет запахом цвета `color` прямо подо мной (0 — не пахнет)."
    },
    {
     "name": "smell_way",
     "kind": "method",
     "sig": "(color)",
     "type": "Point | None",
     "doc": "Точка в 5 м от меня, где запах `color` сильнее; `None` — запаха рядом нет."
    },
    {
     "name": "stop",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Остановиться и висеть на месте (дома — остаться в улье). Не ждёт."
    },
    {
     "name": "time",
     "kind": "property",
     "type": "float",
     "doc": "Сколько секунд идёт матч."
    },
    {
     "name": "wait",
     "kind": "method",
     "sig": "(seconds=0)",
     "type": "None",
     "doc": "Подождать: `wait(5)` — 5 секунд, `wait()` — до следующего тика."
    },
    {
     "name": "loop",
     "kind": "override",
     "sig": "()",
     "type": "None",
     "doc": "Что делать. Игра вызывает `loop()` снова и снова. Переопредели в своём классе."
    }
   ]
  },
  "Collector": {
   "doc": "Сборщик: носит нектар (до 1.5), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта.",
   "bases": [],
   "members": [
    {
     "name": "at_home",
     "kind": "property",
     "type": "bool",
     "doc": "Я дома, в улье (там нектар выгружается, а бак заправляется)."
    },
    {
     "name": "bees",
     "kind": "property",
     "type": "list[OtherBee]",
     "doc": "Пчёлы, которых я вижу (ближние — первыми)."
    },
    {
     "name": "collect",
     "kind": "method",
     "sig": "(target, y=None, speed=None)",
     "type": "bool",
     "doc": "Собирать нектар: с цветка или с ближайшего цветка у места. `True` — груз полный."
    },
    {
     "name": "energy",
     "kind": "property",
     "type": "float",
     "doc": "Сколько энергии осталось: 100 — полный бак, 0 — пчела падает."
    },
    {
     "name": "explore",
     "kind": "method",
     "sig": "(speed=None)",
     "type": "Flower | None",
     "doc": "Искать цветы: `search` к случайной точке вокруг дома. Цветок или `None`."
    },
    {
     "name": "flowers",
     "kind": "property",
     "type": "list[Flower]",
     "doc": "Цветы, которые я вижу (ближние — первыми)."
    },
    {
     "name": "fly_to",
     "kind": "method",
     "sig": "(target, y=None, speed=None)",
     "type": "bool",
     "doc": "Лететь к цели и ждать, пока долечу. `True` — долетела, `False` — не вышло за 60 с."
    },
    {
     "name": "go_home",
     "kind": "method",
     "sig": "(speed=None)",
     "type": "bool",
     "doc": "Лететь домой и войти в улей: нектар выгрузится сам. `True` — я дома."
    },
    {
     "name": "heard",
     "kind": "property",
     "type": "list[Message]",
     "doc": "Что я услышала с прошлого прохода `loop()`: от каждого — последнее по каждому слову."
    },
    {
     "name": "home",
     "kind": "property",
     "type": "Point",
     "doc": "Где вход в мой улей."
    },
    {
     "name": "is_full",
     "kind": "property",
     "type": "bool",
     "doc": "Груз полный — пора домой."
    },
    {
     "name": "mark",
     "kind": "method",
     "sig": "(color)",
     "type": "None",
     "doc": "Оставить запах цвета `color` на месте: \"red\", \"blue\", \"green\" или \"yellow\"."
    },
    {
     "name": "max_energy",
     "kind": "property",
     "type": "float",
     "doc": "Размер моего бака, Дж (у каждой пчелы свой)."
    },
    {
     "name": "nearest_flower",
     "kind": "method",
     "sig": "(min_nectar=0.0)",
     "type": "Flower | None",
     "doc": "Ближайший цветок, где нектара не меньше `min_nectar`; `None` — такого не видно."
    },
    {
     "name": "nectar",
     "kind": "property",
     "type": "float",
     "doc": "Сколько нектара я несу (сборщик — до 1.5)."
    },
    {
     "name": "pos",
     "kind": "property",
     "type": "Point",
     "doc": "Где я."
    },
    {
     "name": "refuel",
     "kind": "method",
     "sig": "(level=100)",
     "type": "bool",
     "doc": "Заправиться дома до `level` % и только потом продолжать. Не дома — сначала домой."
    },
    {
     "name": "say",
     "kind": "method",
     "sig": "(word, place=None)",
     "type": "None",
     "doc": "Сказать своим в 15 м слово и (необязательно) место: `say(\"flowers\", flower)`."
    },
    {
     "name": "search",
     "kind": "method",
     "sig": "(target, y=None, speed=None)",
     "type": "Flower | None",
     "doc": "Лететь к цели, но остановиться у первого цветка с нектаром, который увижу."
    },
    {
     "name": "smell",
     "kind": "method",
     "sig": "(color)",
     "type": "float",
     "doc": "Как сильно пахнет запахом цвета `color` прямо подо мной (0 — не пахнет)."
    },
    {
     "name": "smell_way",
     "kind": "method",
     "sig": "(color)",
     "type": "Point | None",
     "doc": "Точка в 5 м от меня, где запах `color` сильнее; `None` — запаха рядом нет."
    },
    {
     "name": "stop",
     "kind": "method",
     "sig": "()",
     "type": "None",
     "doc": "Остановиться и висеть на месте (дома — остаться в улье). Не ждёт."
    },
    {
     "name": "time",
     "kind": "property",
     "type": "float",
     "doc": "Сколько секунд идёт матч."
    },
    {
     "name": "wait",
     "kind": "method",
     "sig": "(seconds=0)",
     "type": "None",
     "doc": "Подождать: `wait(5)` — 5 секунд, `wait()` — до следующего тика."
    },
    {
     "name": "loop",
     "kind": "override",
     "sig": "()",
     "type": "None",
     "doc": "Что делать. Игра вызывает `loop()` снова и снова. Переопредели в своём классе."
    }
   ]
  },
  "Worker": {
   "doc": "Домашняя пчела: живёт в улье и работает сама — делает мёд из нектара и растит личинки. Кода у неё нет; её можно только вывести (`hatch(Worker)`) и посчитать (`count(Worker)`).",
   "bases": [],
   "members": []
  },
  "Hive": {
   "doc": "Улей: мёд, выведение пчёл, общие правила для пчёл.",
   "bases": [],
   "members": [
    {
     "name": "count",
     "kind": "method",
     "sig": "(kind)",
     "type": "int",
     "doc": "Сколько живых пчёл типа `kind` (Scout, Collector или Worker)."
    },
    {
     "name": "hatch",
     "kind": "method",
     "sig": "(kind)",
     "type": "bool",
     "doc": "Вывести пчелу типа `kind` за мёд. `True` — личинка в улье, `False` — мёда или места нет."
    },
    {
     "name": "heard",
     "kind": "property",
     "type": "list[Message]",
     "doc": "Что я услышала с прошлого прохода `loop()`: от каждого — последнее по каждому слову."
    },
    {
     "name": "honey",
     "kind": "property",
     "type": "float",
     "doc": "Сколько мёда на складе (выведение в этом проходе уже вычтено)."
    },
    {
     "name": "say",
     "kind": "method",
     "sig": "(word, place=None)",
     "type": "None",
     "doc": "Сказать своим в 15 м слово и (необязательно) место: `say(\"flowers\", flower)`."
    },
    {
     "name": "set_home_energy",
     "kind": "method",
     "sig": "(percent)",
     "type": "None",
     "doc": "Ниже скольких % энергии пчела сама летит домой (0–90, сначала 30; 0 — никогда)."
    },
    {
     "name": "set_refuel_energy",
     "kind": "method",
     "sig": "(percent)",
     "type": "None",
     "doc": "До скольких % заправляется пчела, которая вернулась сама (сначала 100)."
    },
    {
     "name": "time",
     "kind": "property",
     "type": "float",
     "doc": "Сколько секунд идёт матч."
    },
    {
     "name": "wait",
     "kind": "method",
     "sig": "(seconds=0)",
     "type": "None",
     "doc": "Подождать: `wait(5)` — 5 секунд, `wait()` — до следующего тика."
    },
    {
     "name": "loop",
     "kind": "override",
     "sig": "()",
     "type": "None",
     "doc": "Что делать. Игра вызывает `loop()` снова и снова. Переопредели в своём классе."
    }
   ]
  }
 },
 "globals": [
  {
   "name": "Point",
   "kind": "class",
   "doc": "Точка на карте: `x`, `y` (и высота `z`), в метрах."
  },
  {
   "name": "Flower",
   "kind": "class",
   "doc": "Цветок, который видит пчела."
  },
  {
   "name": "OtherBee",
   "kind": "class",
   "doc": "Другая пчела, которую я вижу (своя или чужая)."
  },
  {
   "name": "Message",
   "kind": "class",
   "doc": "Сообщение, которое я услышала от своей пчелы или улья."
  },
  {
   "name": "Scout",
   "kind": "class",
   "doc": "Разведчик: быстрый (≈8 м/с), видит далеко (25 м), летает ≈5 минут."
  },
  {
   "name": "Collector",
   "kind": "class",
   "doc": "Сборщик: носит нектар (до 1.5), летает ≈5 м/с, видит 8 м, ≈4 минуты полёта."
  },
  {
   "name": "Worker",
   "kind": "class",
   "doc": "Домашняя пчела: живёт в улье и работает сама — делает мёд из нектара и растит личинки. Кода у неё нет; её можно только вывести (`hatch(Worker)`) и посчитать (`count(Worker)`)."
  },
  {
   "name": "Hive",
   "kind": "class",
   "doc": "Улей: мёд, выведение пчёл, общие правила для пчёл."
  }
 ]
};
