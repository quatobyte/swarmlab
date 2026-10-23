// Сгенерировано tools/gen_blocks_api.py из src/swarmlab/bees/api.py — не править руками.
// Обновить: .venv\Scripts\python tools\gen_blocks_api.py
export const BLOCKS_API = {
 "literals": {
  "Kind": [
   "scout",
   "forager",
   "guard",
   "house"
  ],
  "Weather": [
   "clear",
   "windy",
   "rain"
  ],
  "Task": [
   "rest",
   "process",
   "nurse"
  ]
 },
 "classes": {
  "Bee": {
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ]
  },
  "Forager": {
   "target": "self",
   "subjects": [
    "forager"
   ]
  },
  "Guard": {
   "target": "self",
   "subjects": [
    "guard"
   ]
  },
  "HouseBee": {
   "target": "self",
   "subjects": [
    "house"
   ]
  },
  "Hive": {
   "target": "hive",
   "subjects": [
    "hive"
   ]
  },
  "Sensors": {
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ]
  },
  "Me": {
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ]
  },
  "Home": {
   "target": "s.home",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ]
  },
  "HouseSensors": {
   "target": "s",
   "subjects": [
    "house"
   ]
  },
  "HouseMe": {
   "target": "s.me",
   "subjects": [
    "house"
   ]
  },
  "Flower": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Enemy": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "BeeInfo": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Obstacle": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Message": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Pheromones": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Vec": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Counts": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  },
  "Larva": {
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ]
  }
 },
 "blocks": [
  {
   "type": "bees_Bee_fly_dir",
   "api": "Bee.fly_dir",
   "cls": "Bee",
   "name": "fly_dir",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "dx",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "dy",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "dz",
     "type": "float",
     "required": false,
     "default": "0.0",
     "vararg": false,
     "options": null,
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
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Лететь в направлении `(dx, dy, dz)` (длина неважна), пока не скажут другое."
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
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "x",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "y",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "z",
     "type": "float | None",
     "required": false,
     "default": "None",
     "vararg": false,
     "options": null,
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
     "check": [
      "Number"
     ]
    },
    {
     "name": "avoid",
     "type": "bool",
     "required": false,
     "default": "True",
     "vararg": false,
     "options": null,
     "check": [
      "Boolean"
     ]
    }
   ],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Лететь к точке `(x, y)`."
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
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Лететь к летку и войти в улей (там заправка и выгрузка нектара)."
  },
  {
   "type": "bees_Bee_hover",
   "api": "Bee.hover",
   "cls": "Bee",
   "name": "hover",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Зависнуть на месте."
  },
  {
   "type": "bees_Bee_leave_hive",
   "api": "Bee.leave_hive",
   "cls": "Bee",
   "name": "leave_hive",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Вылететь из улья (если пчела внутри)."
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
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "channel",
     "type": "int",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "amount",
     "type": "float",
     "required": false,
     "default": "1.0",
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "waitable": false,
   "doc": "Оставить запах (феромон) канала `channel` (0–3) в клетке под пчелой."
  },
  {
   "type": "bees_Bee_signal",
   "api": "Bee.signal",
   "cls": "Bee",
   "name": "signal",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "values",
     "type": "float",
     "required": false,
     "default": null,
     "vararg": true,
     "options": null,
     "check": [
      "Array"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "waitable": false,
   "doc": "Сообщение до 8 чисел своим пчёлам в радиусе 15 м (дойдёт на следующем тике)."
  },
  {
   "type": "bees_Bee_thrust",
   "api": "Bee.thrust",
   "cls": "Bee",
   "name": "thrust",
   "member": "method",
   "target": "self",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "fx",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "fy",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    },
    {
     "name": "fz",
     "type": "float",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Продвинутый режим: прямая сила тяги, Н. Автопилот выключается."
  },
  {
   "type": "bees_Forager_collect",
   "api": "Forager.collect",
   "cls": "Forager",
   "name": "collect",
   "member": "method",
   "target": "self",
   "subjects": [
    "forager"
   ],
   "params": [
    {
     "name": "flower",
     "type": "Flower | int",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Flower",
      "Number"
     ]
    }
   ],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Подлететь к цветку, зависнуть над ним и набирать нектар (0.25 ед./с)."
  },
  {
   "type": "bees_Forager_unload",
   "api": "Forager.unload",
   "cls": "Forager",
   "name": "unload",
   "member": "method",
   "target": "self",
   "subjects": [
    "forager"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Выгрузить весь нектар на склад. Работает, только когда сборщик в улье."
  },
  {
   "type": "bees_Guard_intercept",
   "api": "Guard.intercept",
   "cls": "Guard",
   "name": "intercept",
   "member": "method",
   "target": "self",
   "subjects": [
    "guard"
   ],
   "params": [
    {
     "name": "target",
     "type": "Enemy | BeeInfo | int",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Enemy",
      "BeeInfo",
      "Number"
     ]
    }
   ],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Преследовать цель с упреждением (лететь туда, где она будет)."
  },
  {
   "type": "bees_HouseBee_nurse",
   "api": "HouseBee.nurse",
   "cls": "HouseBee",
   "name": "nurse",
   "member": "method",
   "target": "self",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Ухаживать за личинками: чем больше нянек, тем быстрее выведение."
  },
  {
   "type": "bees_HouseBee_process",
   "api": "HouseBee.process",
   "cls": "HouseBee",
   "name": "process",
   "member": "method",
   "target": "self",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Перерабатывать нектар в мёд (1 ед. нектара → 0.5 ед. мёда)."
  },
  {
   "type": "bees_HouseBee_rest",
   "api": "HouseBee.rest",
   "cls": "HouseBee",
   "name": "rest",
   "member": "method",
   "target": "self",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Order",
   "output": null,
   "waitable": true,
   "doc": "Отдыхать (мёд всё равно ест)."
  },
  {
   "type": "bees_Hive_breed",
   "api": "Hive.breed",
   "cls": "Hive",
   "name": "breed",
   "member": "method",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "kind",
     "type": "Kind",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "scout",
      "forager",
      "guard",
      "house"
     ],
     "check": [
      "String"
     ]
    },
    {
     "name": "n",
     "type": "int",
     "required": false,
     "default": "1",
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "waitable": false,
   "doc": "Вывести `n` пчёл типа `kind` (\"scout\", \"forager\", \"guard\", \"house\")."
  },
  {
   "type": "bees_Hive_cancel_breeding",
   "api": "Hive.cancel_breeding",
   "cls": "Hive",
   "name": "cancel_breeding",
   "member": "method",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "kind",
     "type": "Kind",
     "required": true,
     "default": null,
     "vararg": false,
     "options": [
      "scout",
      "forager",
      "guard",
      "house"
     ],
     "check": [
      "String"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "waitable": false,
   "doc": "Отменить последнюю личинку типа `kind` в очереди (мёд вернётся)."
  },
  {
   "type": "bees_Hive_costs",
   "api": "Hive.costs",
   "cls": "Hive",
   "name": "costs",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "dict[str, float]",
   "output": [],
   "waitable": false,
   "doc": "Цена выведения в мёде: `costs[\"forager\"]`."
  },
  {
   "type": "bees_Hive_counts",
   "api": "Hive.counts",
   "cls": "Hive",
   "name": "counts",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "Counts",
   "output": [
    "Counts"
   ],
   "waitable": false,
   "doc": "сколько пчёл"
  },
  {
   "type": "bees_Hive_honey",
   "api": "Hive.honey",
   "cls": "Hive",
   "name": "honey",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "мёд на складе, ед."
  },
  {
   "type": "bees_Hive_max_bees",
   "api": "Hive.max_bees",
   "cls": "Hive",
   "name": "max_bees",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "больше этого пчёл (с личинками) быть не может"
  },
  {
   "type": "bees_Hive_memory",
   "api": "Hive.memory",
   "cls": "Hive",
   "name": "memory",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "dict[str, Any]",
   "output": [],
   "waitable": false,
   "doc": "Память улья: кладите сюда что угодно, оно сохранится."
  },
  {
   "type": "bees_Hive_messages",
   "api": "Hive.messages",
   "cls": "Hive",
   "name": "messages",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "list[Message]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "Сообщения от своих пчёл рядом с летком (с прошлого тика)."
  },
  {
   "type": "bees_Hive_nectar",
   "api": "Hive.nectar",
   "cls": "Hive",
   "name": "nectar",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "нектар на складе (ещё не переработан), ед."
  },
  {
   "type": "bees_Hive_queue",
   "api": "Hive.queue",
   "cls": "Hive",
   "name": "queue",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "list[Larva]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "очередь выведения"
  },
  {
   "type": "bees_Hive_signal",
   "api": "Hive.signal",
   "cls": "Hive",
   "name": "signal",
   "member": "method",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [
    {
     "name": "values",
     "type": "float",
     "required": false,
     "default": null,
     "vararg": true,
     "options": null,
     "check": [
      "Array"
     ]
    }
   ],
   "returns": "None",
   "output": null,
   "waitable": false,
   "doc": "Сообщение до 8 чисел всем своим пчёлам в радиусе 15 м от летка."
  },
  {
   "type": "bees_Hive_tick",
   "api": "Hive.tick",
   "cls": "Hive",
   "name": "tick",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер тика"
  },
  {
   "type": "bees_Hive_time",
   "api": "Hive.time",
   "cls": "Hive",
   "name": "time",
   "member": "field",
   "target": "hive",
   "subjects": [
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "время матча, с"
  },
  {
   "type": "bees_Sensors_airspeed",
   "api": "Sensors.airspeed",
   "cls": "Sensors",
   "name": "airspeed",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "ветер в моей точке, м/с"
  },
  {
   "type": "bees_Sensors_bees",
   "api": "Sensors.bees",
   "cls": "Sensors",
   "name": "bees",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "list[BeeInfo]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "пчёлы рядом"
  },
  {
   "type": "bees_Sensors_enemies",
   "api": "Sensors.enemies",
   "cls": "Sensors",
   "name": "enemies",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "list[Enemy]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "враги рядом"
  },
  {
   "type": "bees_Sensors_flowers",
   "api": "Sensors.flowers",
   "cls": "Sensors",
   "name": "flowers",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "list[Flower]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "цветы рядом (ближние — первыми)"
  },
  {
   "type": "bees_Sensors_ground_z",
   "api": "Sensors.ground_z",
   "cls": "Sensors",
   "name": "ground_z",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "высота земли подо мной, м"
  },
  {
   "type": "bees_Sensors_home",
   "api": "Sensors.home",
   "cls": "Sensors",
   "name": "home",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Home",
   "output": [
    "Home"
   ],
   "waitable": false,
   "doc": "мой улей"
  },
  {
   "type": "bees_Sensors_me",
   "api": "Sensors.me",
   "cls": "Sensors",
   "name": "me",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Me",
   "output": [
    "Me"
   ],
   "waitable": false,
   "doc": "я сама"
  },
  {
   "type": "bees_Sensors_messages",
   "api": "Sensors.messages",
   "cls": "Sensors",
   "name": "messages",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "list[Message]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "сообщения от своих"
  },
  {
   "type": "bees_Sensors_nearest_enemy",
   "api": "Sensors.nearest_enemy",
   "cls": "Sensors",
   "name": "nearest_enemy",
   "member": "method",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Enemy | None",
   "output": [
    "Enemy"
   ],
   "waitable": false,
   "doc": "Ближайший видимый враг; `None` — врагов не видно."
  },
  {
   "type": "bees_Sensors_nearest_flower",
   "api": "Sensors.nearest_flower",
   "cls": "Sensors",
   "name": "nearest_flower",
   "member": "method",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [
    {
     "name": "min_nectar",
     "type": "float",
     "required": false,
     "default": "0.0",
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Flower | None",
   "output": [
    "Flower"
   ],
   "waitable": false,
   "doc": "Ближайший видимый цветок, где нектара не меньше `min_nectar`; `None` — нет такого."
  },
  {
   "type": "bees_Sensors_obstacles",
   "api": "Sensors.obstacles",
   "cls": "Sensors",
   "name": "obstacles",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "list[Obstacle]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "препятствия рядом"
  },
  {
   "type": "bees_Sensors_pheromones",
   "api": "Sensors.pheromones",
   "cls": "Sensors",
   "name": "pheromones",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Pheromones",
   "output": [
    "Pheromones"
   ],
   "waitable": false,
   "doc": "запахи своего улья"
  },
  {
   "type": "bees_Sensors_tick",
   "api": "Sensors.tick",
   "cls": "Sensors",
   "name": "tick",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер тика (10 тиков в секунду)"
  },
  {
   "type": "bees_Sensors_time",
   "api": "Sensors.time",
   "cls": "Sensors",
   "name": "time",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "время матча, с"
  },
  {
   "type": "bees_Sensors_weather",
   "api": "Sensors.weather",
   "cls": "Sensors",
   "name": "weather",
   "member": "field",
   "target": "s",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Weather",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": "погода: \"clear\", \"windy\", \"rain\""
  },
  {
   "type": "bees_Me_alive",
   "api": "Me.alive",
   "cls": "Me",
   "name": "alive",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "waitable": false,
   "doc": "жива ли пчела"
  },
  {
   "type": "bees_Me_cargo",
   "api": "Me.cargo",
   "cls": "Me",
   "name": "cargo",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "сколько нектара несу, ед."
  },
  {
   "type": "bees_Me_cargo_max",
   "api": "Me.cargo_max",
   "cls": "Me",
   "name": "cargo_max",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "сколько нектара влезает, ед. (у сборщика 1.5, у остальных 0)"
  },
  {
   "type": "bees_Me_energy",
   "api": "Me.energy",
   "cls": "Me",
   "name": "energy",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "сколько энергии осталось, Дж (0 — пчела падает)"
  },
  {
   "type": "bees_Me_energy_max",
   "api": "Me.energy_max",
   "cls": "Me",
   "name": "energy_max",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "полный запас энергии, Дж"
  },
  {
   "type": "bees_Me_energy_percent",
   "api": "Me.energy_percent",
   "cls": "Me",
   "name": "energy_percent",
   "member": "property",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Запас энергии в процентах: 100 — полный, 0 — пустой."
  },
  {
   "type": "bees_Me_id",
   "api": "Me.id",
   "cls": "Me",
   "name": "id",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер пчелы (у каждой свой, не меняется)"
  },
  {
   "type": "bees_Me_in_hive",
   "api": "Me.in_hive",
   "cls": "Me",
   "name": "in_hive",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "waitable": false,
   "doc": "я внутри улья (там заправляюсь и выгружаю нектар)"
  },
  {
   "type": "bees_Me_is_full",
   "api": "Me.is_full",
   "cls": "Me",
   "name": "is_full",
   "member": "property",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "waitable": false,
   "doc": "Груз полный — пора домой."
  },
  {
   "type": "bees_Me_kind",
   "api": "Me.kind",
   "cls": "Me",
   "name": "kind",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Kind",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": "тип: \"scout\", \"forager\", \"guard\""
  },
  {
   "type": "bees_Me_pos",
   "api": "Me.pos",
   "cls": "Me",
   "name": "pos",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "где я, м"
  },
  {
   "type": "bees_Me_vel",
   "api": "Me.vel",
   "cls": "Me",
   "name": "vel",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "моя скорость, м/с"
  },
  {
   "type": "bees_Home_dir",
   "api": "Home.dir",
   "cls": "Home",
   "name": "dir",
   "member": "field",
   "target": "s.home",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "направление на леток (длина 1)"
  },
  {
   "type": "bees_Home_dist",
   "api": "Home.dist",
   "cls": "Home",
   "name": "dist",
   "member": "field",
   "target": "s.home",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "расстояние до летка, м"
  },
  {
   "type": "bees_Home_pos",
   "api": "Home.pos",
   "cls": "Home",
   "name": "pos",
   "member": "field",
   "target": "s.home",
   "subjects": [
    "scout",
    "forager",
    "guard"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "леток — вход в улей"
  },
  {
   "type": "bees_HouseSensors_breeding_queue",
   "api": "HouseSensors.breeding_queue",
   "cls": "HouseSensors",
   "name": "breeding_queue",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "list[Larva]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "очередь выведения"
  },
  {
   "type": "bees_HouseSensors_counts",
   "api": "HouseSensors.counts",
   "cls": "HouseSensors",
   "name": "counts",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Counts",
   "output": [
    "Counts"
   ],
   "waitable": false,
   "doc": "сколько пчёл в улье"
  },
  {
   "type": "bees_HouseSensors_hive_honey",
   "api": "HouseSensors.hive_honey",
   "cls": "HouseSensors",
   "name": "hive_honey",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "мёда на складе, ед."
  },
  {
   "type": "bees_HouseSensors_hive_nectar",
   "api": "HouseSensors.hive_nectar",
   "cls": "HouseSensors",
   "name": "hive_nectar",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "нектара на складе, ед."
  },
  {
   "type": "bees_HouseSensors_me",
   "api": "HouseSensors.me",
   "cls": "HouseSensors",
   "name": "me",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "HouseMe",
   "output": [
    "HouseMe"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_HouseSensors_tick",
   "api": "HouseSensors.tick",
   "cls": "HouseSensors",
   "name": "tick",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_HouseSensors_time",
   "api": "HouseSensors.time",
   "cls": "HouseSensors",
   "name": "time",
   "member": "field",
   "target": "s",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_HouseMe_id",
   "api": "HouseMe.id",
   "cls": "HouseMe",
   "name": "id",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_HouseMe_kind",
   "api": "HouseMe.kind",
   "cls": "HouseMe",
   "name": "kind",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Kind",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": "всегда \"house\""
  },
  {
   "type": "bees_HouseMe_task",
   "api": "HouseMe.task",
   "cls": "HouseMe",
   "name": "task",
   "member": "field",
   "target": "s.me",
   "subjects": [
    "house"
   ],
   "params": [],
   "returns": "Task",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": "чем занята сейчас: \"rest\", \"process\", \"nurse\""
  },
  {
   "type": "bees_Flower_dist",
   "api": "Flower.dist",
   "cls": "Flower",
   "name": "dist",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "расстояние до цветка, м"
  },
  {
   "type": "bees_Flower_id",
   "api": "Flower.id",
   "cls": "Flower",
   "name": "id",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер цветка — его передают в `collect()`"
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
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "сколько в нём нектара, ед. (максимум 3)"
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
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "где цветок"
  },
  {
   "type": "bees_Flower_rel_pos",
   "api": "Flower.rel_pos",
   "cls": "Flower",
   "name": "rel_pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "где цветок относительно меня"
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
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "bool | None",
   "output": [
    "Boolean"
   ],
   "waitable": false,
   "doc": "у остальных и издалека — `None` («не знаю»)."
  },
  {
   "type": "bees_Enemy_dist",
   "api": "Enemy.dist",
   "cls": "Enemy",
   "name": "dist",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Enemy_id",
   "api": "Enemy.id",
   "cls": "Enemy",
   "name": "id",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер врага — его передают в `intercept()`"
  },
  {
   "type": "bees_Enemy_kind",
   "api": "Enemy.kind",
   "cls": "Enemy",
   "name": "kind",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "str",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": "\"hornet\""
  },
  {
   "type": "bees_Enemy_pos",
   "api": "Enemy.pos",
   "cls": "Enemy",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Enemy_rel_pos",
   "api": "Enemy.rel_pos",
   "cls": "Enemy",
   "name": "rel_pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Enemy_vel",
   "api": "Enemy.vel",
   "cls": "Enemy",
   "name": "vel",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_dist",
   "api": "BeeInfo.dist",
   "cls": "BeeInfo",
   "name": "dist",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_friend",
   "api": "BeeInfo.friend",
   "cls": "BeeInfo",
   "name": "friend",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "bool",
   "output": [
    "Boolean"
   ],
   "waitable": false,
   "doc": "из моего улья"
  },
  {
   "type": "bees_BeeInfo_id",
   "api": "BeeInfo.id",
   "cls": "BeeInfo",
   "name": "id",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_kind",
   "api": "BeeInfo.kind",
   "cls": "BeeInfo",
   "name": "kind",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Kind",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_pos",
   "api": "BeeInfo.pos",
   "cls": "BeeInfo",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_rel_pos",
   "api": "BeeInfo.rel_pos",
   "cls": "BeeInfo",
   "name": "rel_pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_BeeInfo_team",
   "api": "BeeInfo.team",
   "cls": "BeeInfo",
   "name": "team",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "номер улья пчелы"
  },
  {
   "type": "bees_BeeInfo_vel",
   "api": "BeeInfo.vel",
   "cls": "BeeInfo",
   "name": "vel",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Obstacle_dist",
   "api": "Obstacle.dist",
   "cls": "Obstacle",
   "name": "dist",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "расстояние до оси (до поверхности — `dist - radius`)"
  },
  {
   "type": "bees_Obstacle_pos",
   "api": "Obstacle.pos",
   "cls": "Obstacle",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "ближайшая к пчеле точка оси препятствия"
  },
  {
   "type": "bees_Obstacle_radius",
   "api": "Obstacle.radius",
   "cls": "Obstacle",
   "name": "radius",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Obstacle_rel_pos",
   "api": "Obstacle.rel_pos",
   "cls": "Obstacle",
   "name": "rel_pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Message_from_id",
   "api": "Message.from_id",
   "cls": "Message",
   "name": "from_id",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "кто отправил (`HIVE_ID` = -1 — сам улей)"
  },
  {
   "type": "bees_Message_pos",
   "api": "Message.pos",
   "cls": "Message",
   "name": "pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "откуда отправили"
  },
  {
   "type": "bees_Message_rel_pos",
   "api": "Message.rel_pos",
   "cls": "Message",
   "name": "rel_pos",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Message_values",
   "api": "Message.values",
   "cls": "Message",
   "name": "values",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "tuple[float, ...]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": "до 8 чисел — что в них значит, решаете вы"
  },
  {
   "type": "bees_Pheromones_direction",
   "api": "Pheromones.direction",
   "cls": "Pheromones",
   "name": "direction",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [
    {
     "name": "channel",
     "type": "int",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "Направление, где запах канала `channel` сильнее (по горизонтали, длина 1)."
  },
  {
   "type": "bees_Pheromones_gradient",
   "api": "Pheromones.gradient",
   "cls": "Pheromones",
   "name": "gradient",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "list[list[float]]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Pheromones_strength",
   "api": "Pheromones.strength",
   "cls": "Pheromones",
   "name": "strength",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [
    {
     "name": "channel",
     "type": "int",
     "required": true,
     "default": null,
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Сила запаха канала `channel` прямо под пчелой."
  },
  {
   "type": "bees_Pheromones_values",
   "api": "Pheromones.values",
   "cls": "Pheromones",
   "name": "values",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "list[list[list[float]]]",
   "output": [
    "Array"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Vec_dist",
   "api": "Vec.dist",
   "cls": "Vec",
   "name": "dist",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
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
     "check": null
    }
   ],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Расстояние до точки `other`."
  },
  {
   "type": "bees_Vec_dist_xy",
   "api": "Vec.dist_xy",
   "cls": "Vec",
   "name": "dist_xy",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
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
     "check": null
    }
   ],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Расстояние до точки `other` по горизонтали."
  },
  {
   "type": "bees_Vec_length",
   "api": "Vec.length",
   "cls": "Vec",
   "name": "length",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Длина вектора."
  },
  {
   "type": "bees_Vec_length_xy",
   "api": "Vec.length_xy",
   "cls": "Vec",
   "name": "length_xy",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Длина по горизонтали (без высоты)."
  },
  {
   "type": "bees_Vec_normalized",
   "api": "Vec.normalized",
   "cls": "Vec",
   "name": "normalized",
   "member": "method",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Vec",
   "output": [
    "Vec"
   ],
   "waitable": false,
   "doc": "Вектор той же направленности длиной 1 (нулевой остаётся нулевым)."
  },
  {
   "type": "bees_Vec_x",
   "api": "Vec.x",
   "cls": "Vec",
   "name": "x",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Vec_y",
   "api": "Vec.y",
   "cls": "Vec",
   "name": "y",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Vec_z",
   "api": "Vec.z",
   "cls": "Vec",
   "name": "z",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Counts_flying",
   "api": "Counts.flying",
   "cls": "Counts",
   "name": "flying",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "dict[str, int]",
   "output": [],
   "waitable": false,
   "doc": "Сколько каждого типа в полёте: `flying[\"scout\"]`."
  },
  {
   "type": "bees_Counts_forager",
   "api": "Counts.forager",
   "cls": "Counts",
   "name": "forager",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Counts_guard",
   "api": "Counts.guard",
   "cls": "Counts",
   "name": "guard",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Counts_house",
   "api": "Counts.house",
   "cls": "Counts",
   "name": "house",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Counts_in_hive",
   "api": "Counts.in_hive",
   "cls": "Counts",
   "name": "in_hive",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "dict[str, int]",
   "output": [],
   "waitable": false,
   "doc": "Сколько каждого типа сидит в улье: `in_hive[\"forager\"]`."
  },
  {
   "type": "bees_Counts_scout",
   "api": "Counts.scout",
   "cls": "Counts",
   "name": "scout",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Counts_total",
   "api": "Counts.total",
   "cls": "Counts",
   "name": "total",
   "member": "property",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "Всего живых пчёл."
  },
  {
   "type": "bees_Larva_kind",
   "api": "Larva.kind",
   "cls": "Larva",
   "name": "kind",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "Kind",
   "output": [
    "String"
   ],
   "waitable": false,
   "doc": ""
  },
  {
   "type": "bees_Larva_left_s",
   "api": "Larva.left_s",
   "cls": "Larva",
   "name": "left_s",
   "member": "field",
   "target": "obj",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "float",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "сколько ещё расти (в секундах при одной няньке)"
  },
  {
   "type": "bees_HIVE_ID",
   "api": "HIVE_ID",
   "cls": "",
   "name": "HIVE_ID",
   "member": "const",
   "target": "",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [],
   "returns": "int",
   "output": [
    "Number"
   ],
   "waitable": false,
   "doc": "`from_id` сообщений, которые отправил сам улей (`hive.signal`)."
  },
  {
   "type": "bees_wait",
   "api": "wait",
   "cls": "",
   "name": "wait",
   "member": "function",
   "target": "",
   "subjects": [
    "scout",
    "forager",
    "guard",
    "house",
    "hive"
   ],
   "params": [
    {
     "name": "seconds",
     "type": "float",
     "required": false,
     "default": "0.0",
     "vararg": false,
     "options": null,
     "check": [
      "Number"
     ]
    }
   ],
   "returns": "Wait",
   "output": null,
   "waitable": false,
   "yields": true,
   "doc": "Подождать: `yield wait()` — один тик, `yield wait(5)` — 5 секунд игрового времени."
  }
 ]
};
