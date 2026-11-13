// Сгенерировано tools/gen_blocks_api.py из src/swarmlab/bees/api.py — не править руками.
// Обновить: .venv\Scripts\python tools\gen_blocks_api.py
export const BLOCKS_API = {
 "literals": {
  "Color": [
   "red",
   "blue",
   "green",
   "yellow"
  ],
  "BeeType": [
   "Scout",
   "Collector",
   "Worker"
  ]
 },
 "classes": {
  "Agent": {
   "target": "self",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ]
  },
  "Bee": {
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ]
  },
  "Collector": {
   "target": "self",
   "subjects": [
    "collector"
   ]
  },
  "Hive": {
   "target": "self",
   "subjects": [
    "hive"
   ]
  },
  "Flower": {
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ]
  },
  "OtherBee": {
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ]
  },
  "Message": {
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ]
  },
  "Point": {
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ]
  }
 },
 "blocks": [
  {
   "type": "bees_Agent_heard",
   "api": "Agent.heard",
   "cls": "Agent",
   "name": "heard",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "list[Message]",
   "output": [
    "Array"
   ],
   "result": null,
   "doc": "Что я услышала с прошлого прохода `loop()`: от каждого — последнее по каждому слову."
  },
  {
   "type": "bees_Agent_say",
   "api": "Agent.say",
   "cls": "Agent",
   "name": "say",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [
    {
     "name": "word",
     "type": "str",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "String"
     ]
    },
    {
     "name": "place",
     "type": "Any",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": null
    }
   ],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "Сказать своим в 15 м слово и (необязательно) место: `say(\"flowers\", flower)`."
  },
  {
   "type": "bees_Agent_time",
   "api": "Agent.time",
   "cls": "Agent",
   "name": "time",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Сколько секунд идёт матч."
  },
  {
   "type": "bees_Agent_wait",
   "api": "Agent.wait",
   "cls": "Agent",
   "name": "wait",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [
    {
     "name": "seconds",
     "type": "float",
     "required": false,
     "default": "0",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "Подождать: `wait(5)` — 5 секунд, `wait()` — до следующего тика."
  },
  {
   "type": "bees_Bee_at_home",
   "api": "Bee.at_home",
   "cls": "Bee",
   "name": "at_home",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "result": null,
   "doc": "Я дома, в улье (там нектар выгружается, а бак заправляется)."
  },
  {
   "type": "bees_Bee_bees",
   "api": "Bee.bees",
   "cls": "Bee",
   "name": "bees",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "list[OtherBee]",
   "output": [
    "Array"
   ],
   "result": null,
   "doc": "Пчёлы, которых я вижу (ближние — первыми)."
  },
  {
   "type": "bees_Bee_energy",
   "api": "Bee.energy",
   "cls": "Bee",
   "name": "energy",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Сколько энергии осталось: 100 — полный бак, 0 — пчела падает."
  },
  {
   "type": "bees_Bee_explore",
   "api": "Bee.explore",
   "cls": "Bee",
   "name": "explore",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "speed",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Flower | None",
   "output": null,
   "result": [
    "Flower"
   ],
   "doc": "Искать цветы: `search` к случайной точке вокруг дома. Цветок или `None`."
  },
  {
   "type": "bees_Bee_flowers",
   "api": "Bee.flowers",
   "cls": "Bee",
   "name": "flowers",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "list[Flower]",
   "output": [
    "Array"
   ],
   "result": null,
   "doc": "Цветы, которые я вижу (ближние — первыми)."
  },
  {
   "type": "bees_Bee_fly_to",
   "api": "Bee.fly_to",
   "cls": "Bee",
   "name": "fly_to",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "target",
     "type": "Any",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": null
    },
    {
     "name": "y",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    },
    {
     "name": "speed",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "bool",
   "output": null,
   "result": [
    "Boolean"
   ],
   "doc": "Лететь к цели и ждать, пока долечу. `True` — долетела, `False` — не вышло за 60 с."
  },
  {
   "type": "bees_Bee_go_home",
   "api": "Bee.go_home",
   "cls": "Bee",
   "name": "go_home",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "speed",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "bool",
   "output": null,
   "result": [
    "Boolean"
   ],
   "doc": "Лететь домой и войти в улей: нектар выгрузится сам. `True` — я дома."
  },
  {
   "type": "bees_Bee_home",
   "api": "Bee.home",
   "cls": "Bee",
   "name": "home",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "Point",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "Где вход в мой улей."
  },
  {
   "type": "bees_Bee_is_full",
   "api": "Bee.is_full",
   "cls": "Bee",
   "name": "is_full",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "result": null,
   "doc": "Груз полный — пора домой."
  },
  {
   "type": "bees_Bee_mark",
   "api": "Bee.mark",
   "cls": "Bee",
   "name": "mark",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "color",
     "type": "_Color",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "red",
      "blue",
      "green",
      "yellow"
     ],
     "ident": false,
     "check": [
      "String"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "Оставить запах цвета `color` на месте: \"red\", \"blue\", \"green\" или \"yellow\"."
  },
  {
   "type": "bees_Bee_max_energy",
   "api": "Bee.max_energy",
   "cls": "Bee",
   "name": "max_energy",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Размер моего бака, Дж (у каждой пчелы свой)."
  },
  {
   "type": "bees_Bee_nearest_flower",
   "api": "Bee.nearest_flower",
   "cls": "Bee",
   "name": "nearest_flower",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "min_nectar",
     "type": "float",
     "required": false,
     "default": "0.0",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Flower | None",
   "output": [
    "Flower"
   ],
   "result": null,
   "doc": "Ближайший цветок, где нектара не меньше `min_nectar`; `None` — такого не видно."
  },
  {
   "type": "bees_Bee_nectar",
   "api": "Bee.nectar",
   "cls": "Bee",
   "name": "nectar",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Сколько нектара я несу (сборщик — до 1.5)."
  },
  {
   "type": "bees_Bee_pos",
   "api": "Bee.pos",
   "cls": "Bee",
   "name": "pos",
   "member": "property",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "Point",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "Где я."
  },
  {
   "type": "bees_Bee_refuel",
   "api": "Bee.refuel",
   "cls": "Bee",
   "name": "refuel",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "level",
     "type": "float",
     "required": false,
     "default": "100",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "bool",
   "output": null,
   "result": [
    "Boolean"
   ],
   "doc": "Заправиться дома до `level` % и только потом продолжать. Не дома — сначала домой."
  },
  {
   "type": "bees_Bee_search",
   "api": "Bee.search",
   "cls": "Bee",
   "name": "search",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "target",
     "type": "Any",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": null
    },
    {
     "name": "y",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    },
    {
     "name": "speed",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Flower | None",
   "output": null,
   "result": [
    "Flower"
   ],
   "doc": "Лететь к цели, но остановиться у первого цветка с нектаром, который увижу."
  },
  {
   "type": "bees_Bee_smell",
   "api": "Bee.smell",
   "cls": "Bee",
   "name": "smell",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "color",
     "type": "_Color",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "red",
      "blue",
      "green",
      "yellow"
     ],
     "ident": false,
     "check": [
      "String"
     ]
    }
   ],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Как сильно пахнет запахом цвета `color` прямо подо мной (0 — не пахнет)."
  },
  {
   "type": "bees_Bee_smell_way",
   "api": "Bee.smell_way",
   "cls": "Bee",
   "name": "smell_way",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [
    {
     "name": "color",
     "type": "_Color",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "red",
      "blue",
      "green",
      "yellow"
     ],
     "ident": false,
     "check": [
      "String"
     ]
    }
   ],
   "returns": "Point | None",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "Точка в 5 м от меня, где запах `color` сильнее; `None` — запаха рядом нет."
  },
  {
   "type": "bees_Bee_stop",
   "api": "Bee.stop",
   "cls": "Bee",
   "name": "stop",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "collector"
   ],
   "params": [],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "Остановиться и висеть на месте (дома — остаться в улье). Не ждёт."
  },
  {
   "type": "bees_Collector_collect",
   "api": "Collector.collect",
   "cls": "Collector",
   "name": "collect",
   "member": "method",
   "target": "self",
   "subjects": [
    "collector"
   ],
   "params": [
    {
     "name": "target",
     "type": "Any",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": null
    },
    {
     "name": "y",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    },
    {
     "name": "speed",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "bool",
   "output": null,
   "result": [
    "Boolean"
   ],
   "doc": "Собирать нектар: с цветка или с ближайшего цветка у места. `True` — груз полный."
  },
  {
   "type": "bees_Hive_count",
   "api": "Hive.count",
   "cls": "Hive",
   "name": "count",
   "member": "method",
   "target": "self",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "kind",
     "type": "_BeeType",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "Scout",
      "Collector",
      "Worker"
     ],
     "ident": true,
     "check": null
    }
   ],
   "returns": "int",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Сколько живых пчёл типа `kind` (Scout, Collector или Worker)."
  },
  {
   "type": "bees_Hive_hatch",
   "api": "Hive.hatch",
   "cls": "Hive",
   "name": "hatch",
   "member": "method",
   "target": "self",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "kind",
     "type": "_BeeType",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "Scout",
      "Collector",
      "Worker"
     ],
     "ident": true,
     "check": null
    }
   ],
   "returns": "bool",
   "output": null,
   "result": [
    "Boolean"
   ],
   "doc": "Вывести пчелу типа `kind` за мёд. `True` — личинка в улье, `False` — мёда или места нет."
  },
  {
   "type": "bees_Hive_honey",
   "api": "Hive.honey",
   "cls": "Hive",
   "name": "honey",
   "member": "property",
   "target": "self",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Сколько мёда на складе (выведение в этом проходе уже вычтено)."
  },
  {
   "type": "bees_Hive_set_home_energy",
   "api": "Hive.set_home_energy",
   "cls": "Hive",
   "name": "set_home_energy",
   "member": "method",
   "target": "self",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "percent",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "Ниже скольких % энергии пчела сама летит домой (0–90, сначала 30; 0 — никогда)."
  },
  {
   "type": "bees_Hive_set_refuel_energy",
   "api": "Hive.set_refuel_energy",
   "cls": "Hive",
   "name": "set_refuel_energy",
   "member": "method",
   "target": "self",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "percent",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "result": null,
   "doc": "До скольких % заправляется пчела, которая вернулась сама (сначала 100)."
  },
  {
   "type": "bees_Flower_distance",
   "api": "Flower.distance",
   "cls": "Flower",
   "name": "distance",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "как далеко от меня, м"
  },
  {
   "type": "bees_Flower_nectar",
   "api": "Flower.nectar",
   "cls": "Flower",
   "name": "nectar",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "сколько в нём нектара (от 0 до 3)"
  },
  {
   "type": "bees_Flower_pos",
   "api": "Flower.pos",
   "cls": "Flower",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "Point",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "где цветок"
  },
  {
   "type": "bees_Flower_spider",
   "api": "Flower.spider",
   "cls": "Flower",
   "name": "spider",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "bool | None",
   "output": [
    "Boolean"
   ],
   "result": null,
   "doc": "у остальных и издалека — `None` («не знаю»)."
  },
  {
   "type": "bees_OtherBee_distance",
   "api": "OtherBee.distance",
   "cls": "OtherBee",
   "name": "distance",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "как далеко от меня, м"
  },
  {
   "type": "bees_OtherBee_friend",
   "api": "OtherBee.friend",
   "cls": "OtherBee",
   "name": "friend",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "result": null,
   "doc": "из моего улья"
  },
  {
   "type": "bees_OtherBee_pos",
   "api": "OtherBee.pos",
   "cls": "OtherBee",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "Point",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "где она"
  },
  {
   "type": "bees_Message_from_where",
   "api": "Message.from_where",
   "cls": "Message",
   "name": "from_where",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "Point",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "откуда сказали"
  },
  {
   "type": "bees_Message_where",
   "api": "Message.where",
   "cls": "Message",
   "name": "where",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "Point | None",
   "output": [
    "Point"
   ],
   "result": null,
   "doc": "место, которое назвали (или `None`)"
  },
  {
   "type": "bees_Message_word",
   "api": "Message.word",
   "cls": "Message",
   "name": "word",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "str",
   "output": [
    "String"
   ],
   "result": null,
   "doc": "слово"
  },
  {
   "type": "bees_Point_distance",
   "api": "Point.distance",
   "cls": "Point",
   "name": "distance",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [
    {
     "name": "other",
     "type": "Any",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "ident": false,
     "check": null
    }
   ],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": "Расстояние до точки, цветка или пчелы по карте (без высоты), м."
  },
  {
   "type": "bees_Point_x",
   "api": "Point.x",
   "cls": "Point",
   "name": "x",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": ""
  },
  {
   "type": "bees_Point_y",
   "api": "Point.y",
   "cls": "Point",
   "name": "y",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": ""
  },
  {
   "type": "bees_Point_z",
   "api": "Point.z",
   "cls": "Point",
   "name": "z",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "collector",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "result": null,
   "doc": ""
  }
 ]
};
