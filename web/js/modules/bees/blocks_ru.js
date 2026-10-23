// Русские подписи, подсказки и раскладка блоков пчёл (M7b, DECISIONS №52) — пишутся вручную.
// Структура блоков (параметры, типы, кто какой блок может использовать) — в blocks_api.js,
// он генерируется из api.py. Здесь — только текст для человека.
//
// Подпись блока: `{имя_параметра}` — место для значения, `{obj}` — объект, у которого берём поле
// (цветок, враг, точка…). Команды, которые можно ждать, сами получают галочку «ждать».
// `full` — подпись варианта со всеми необязательными параметрами (он — в «Продвинутых»).
// `beginner: true` — блок в стартовом наборе; остальные — в категории «Продвинутые».

/**
 * Категории панели блоков: ключ → [название, цвет (оттенок Blockly 0–360), иконка, справка].
 * Иконка — символ Юникода (без внешних шрифтов); справка видна при наведении на категорию (M7c).
 */
export const CATEGORIES = {
  programs: ["Программы", 45, "▶", "С этого начинается всё: перетащите «Программу пчелы» и вложите в неё команды."],
  move: ["Движение", 200, "✈", "Куда лететь: к цветку, домой, к точке, зависнуть на месте."],
  sense: ["Пчела видит", 170, "👁", "Что пчела знает о себе и вокруг: энергия, груз, цветы рядом, погода."],
  objects: ["Цветы, враги, точки", 140, "✿", "Свойства того, что пчела видит: где цветок, сколько в нём нектара, кто враг."],
  house: ["Домашняя пчела", 20, "⌂", "Работа внутри улья: переработка нектара в мёд и уход за личинками."],
  hive: ["Улей", 30, "⬢", "Решения улья: каких пчёл выводить, какие сообщения слать."],
  logic: ["Логика", 210, "⑂", "«Если … то …», сравнения, «и», «или», «не»."],
  loops: ["Циклы", 120, "↻", "Повторить несколько раз, «пока», перебрать все цветы."],
  math: ["Математика", 230, "±", "Числа, арифметика, случайное число."],
  text: ["Текст", 160, "✎", "Слова и печать в лог улья — удобно, чтобы понять, что делает пчела."],
  lists: ["Списки", 260, "☰", "Списки и словари: сохранить несколько значений вместе."],
  variables: ["Переменные", 330, "𝑥", "Запомнить значение под именем — на время одной программы."],
  procedures: ["Процедуры", 290, "ƒ", "Свои команды: собрать несколько блоков под одним именем."],
  python: ["Python", 0, "🐍", "Строка или выражение на Python — для тех, кто уже знает язык."],
  advanced: ["Продвинутые", 0, "⚙", "Все остальные блоки: полные варианты команд, «удалось ли», редкие свойства."],
};

/** Тексты поиска и подсказок новичку в блоках (M7c). */
export const SEARCH_RU = {
  placeholder: "Найти блок…",
  category: "Найдено",
  nothing: "Ничего не найдено — попробуйте другое слово.",
  emptyProgram: "⇣ перетащи сюда команду",
};

/** Категория по умолчанию для блоков API — по классу. */
export const CLASS_CATEGORY = {
  Bee: "move", Forager: "move", Guard: "move", "": "move",
  Sensors: "sense", Me: "sense", Home: "sense",
  Flower: "objects", Enemy: "objects", BeeInfo: "objects", Obstacle: "objects", Message: "objects",
  Pheromones: "objects", Vec: "objects", Counts: "objects", Larva: "objects",
  HouseBee: "house", HouseSensors: "house", HouseMe: "house",
  Hive: "hive",
};

/** Значения `Literal` из api.py для выпадающих списков. */
export const LITERALS = {
  Kind: { scout: "разведчик", forager: "сборщик", guard: "охранник", house: "домашняя пчела" },
  Weather: { clear: "ясно", windy: "ветер", rain: "дождь" },
  Task: { rest: "отдых", process: "переработка", nurse: "уход за личинками" },
};

/** Подписи блоков API: ключ — `Класс.член` из api.py (или имя глобальной функции). */
export const API_RU = {
  // ------------------------------------------------------------ команды летающих пчёл
  "Bee.fly_to": {
    label: "лететь к x {x} y {y}", full: "лететь к x {x} y {y} высота {z} скорость {speed} облетать {avoid}",
    tip: "Лететь к точке на карте. Высота не задана — 5 м над землёй.", beginner: true,
  },
  "Bee.fly_dir": {
    label: "лететь в направлении dx {dx} dy {dy}", full: "лететь в направлении dx {dx} dy {dy} dz {dz} скорость {speed}",
    tip: "Лететь в сторону (dx, dy), пока не скажут другое.",
  },
  "Bee.hover": { label: "зависнуть", tip: "Висеть на месте.", beginner: true },
  "Bee.go_home": { label: "лететь домой", tip: "К летку и внутрь улья: там заправка и выгрузка.", beginner: true },
  "Bee.leave_hive": { label: "вылететь из улья", tip: "Выйти из улья наружу.", beginner: true },
  "Bee.thrust": {
    label: "тяга fx {fx} fy {fy} fz {fz}",
    tip: "Прямая сила тяги, Н; автопилот выключается. Только в матче с advanced_control.",
  },
  "Bee.signal": { label: "сообщить своим {values}", tip: "Отправить список до 8 чисел пчёлам своего улья рядом (15 м)." },
  "Bee.mark": {
    label: "оставить запах канала {channel}", full: "оставить запах канала {channel} силой {amount}",
    tip: "Феромон (канал 0–3) в клетке под пчелой; его чувствуют только свои.",
  },
  "Forager.collect": {
    label: "собирать нектар с {flower}",
    tip: "Подлететь к цветку и набирать нектар, пока груз не полный или цветок не пуст. Только сборщик.",
    beginner: true,
  },
  "Forager.unload": { label: "выгрузить нектар", tip: "Сдать нектар на склад. Только в улье.", beginner: true },
  "Guard.intercept": {
    label: "перехватить {target}", tip: "Преследовать врага с упреждением. Только охранник.", beginner: true,
  },

  // ------------------------------------------------------------ ожидание
  wait: {
    label: "ждать {seconds} с", shadows: { seconds: 1 },
    tip: "Подождать столько секунд игрового времени (пусто или 0 — один тик).", beginner: true,
  },
  HIVE_ID: { label: "номер «сам улей»", tip: "from_id сообщения, которое отправил сам улей (-1)." },

  // ------------------------------------------------------------ сенсоры летающей пчелы
  "Sensors.tick": { label: "номер тика", tip: "10 тиков в секунду." },
  "Sensors.time": { label: "время матча, с", tip: "Сколько секунд прошло с начала матча.", beginner: true },
  "Sensors.me": { label: "я", tip: "Всё о себе: позиция, энергия, груз." },
  "Sensors.home": { label: "мой улей", tip: "Леток своего улья: где он, в какую сторону, как далеко." },
  "Sensors.ground_z": { label: "высота земли подо мной", tip: "Метры." },
  "Sensors.airspeed": { label: "ветер здесь", tip: "Скорость ветра в точке пчелы (точка-вектор), м/с." },
  "Sensors.weather": { label: "погода", tip: "\"clear\", \"windy\" или \"rain\"." },
  "Sensors.flowers": { label: "цветы рядом", tip: "Список видимых цветов, ближние — первыми.", beginner: true },
  "Sensors.bees": { label: "пчёлы рядом", tip: "Список видимых пчёл (свои и чужие)." },
  "Sensors.enemies": { label: "враги рядом", tip: "Список видимых врагов.", beginner: true },
  "Sensors.obstacles": { label: "препятствия рядом", tip: "Деревья и камни рядом." },
  "Sensors.messages": { label: "сообщения", tip: "Сообщения от своих пчёл с прошлого тика." },
  "Sensors.pheromones": { label: "запахи", tip: "Феромоны своего улья вокруг меня." },
  "Sensors.nearest_flower": {
    label: "ближайший цветок", full: "ближайший цветок, где нектара не меньше {min_nectar}",
    tip: "Ближайший видимый цветок; «ничего», если цветов не видно.", beginner: true,
  },
  "Sensors.nearest_enemy": {
    label: "ближайший враг", tip: "Ближайший видимый враг; «ничего», если врагов нет.", beginner: true,
  },

  "Me.id": { label: "мой номер", tip: "У каждой пчелы свой номер." },
  "Me.kind": { label: "мой тип", tip: "\"scout\", \"forager\" или \"guard\"." },
  "Me.pos": { label: "где я", tip: "Моя позиция (точка)." },
  "Me.vel": { label: "моя скорость", tip: "Скорость (вектор), м/с." },
  "Me.energy": { label: "моя энергия, Дж", tip: "Сколько энергии осталось." },
  "Me.energy_max": { label: "полный запас энергии, Дж", tip: "Сколько энергии вмещает пчела." },
  "Me.energy_percent": { label: "моя энергия, %", tip: "0–100. На нуле пчела падает.", beginner: true },
  "Me.cargo": { label: "мой груз", tip: "Сколько нектара несу.", beginner: true },
  "Me.cargo_max": { label: "сколько влезает груза", tip: "У сборщика 1.5, у остальных 0." },
  "Me.is_full": { label: "груз полный", tip: "Да, если больше не влезет.", beginner: true },
  "Me.in_hive": { label: "я в улье", tip: "Да, если пчела внутри улья.", beginner: true },
  "Me.alive": { label: "я жива", tip: "Жива ли пчела." },

  "Home.pos": { label: "где леток", tip: "Точка входа в улей." },
  "Home.dir": { label: "направление на леток", tip: "Вектор длиной 1." },
  "Home.dist": { label: "расстояние до дома", tip: "Метры до летка.", beginner: true },

  // ------------------------------------------------------------ объекты
  "Flower.id": { label: "номер цветка {obj}", tip: "Номер — его можно передать в «собирать нектар»." },
  "Flower.pos": { label: "где цветок {obj}", tip: "Точка цветка." },
  "Flower.rel_pos": { label: "где цветок {obj} от меня", tip: "Точка относительно меня." },
  "Flower.dist": { label: "расстояние до цветка {obj}", tip: "Метры.", beginner: true },
  "Flower.nectar": { label: "нектар в цветке {obj}", tip: "Сколько нектара (максимум 3).", beginner: true },
  "Flower.spider": { label: "паук на цветке {obj}", tip: "Да / нет / «ничего» — не знаю (видит только разведчик вблизи)." },

  "Enemy.id": { label: "номер врага {obj}", tip: "Его передают в «перехватить»." },
  "Enemy.kind": { label: "вид врага {obj}", tip: "\"hornet\" — шершень." },
  "Enemy.pos": { label: "где враг {obj}", tip: "Точка врага." },
  "Enemy.rel_pos": { label: "где враг {obj} от меня", tip: "Точка относительно меня." },
  "Enemy.dist": { label: "расстояние до врага {obj}", tip: "Метры.", beginner: true },
  "Enemy.vel": { label: "скорость врага {obj}", tip: "Вектор, м/с." },

  "BeeInfo.id": { label: "номер пчелы {obj}", tip: "Номер другой пчелы." },
  "BeeInfo.kind": { label: "тип пчелы {obj}", tip: "\"scout\", \"forager\", \"guard\"." },
  "BeeInfo.team": { label: "улей пчелы {obj}", tip: "Номер улья." },
  "BeeInfo.friend": { label: "своя пчела {obj}", tip: "Да, если из моего улья." },
  "BeeInfo.pos": { label: "где пчела {obj}", tip: "Точка пчелы." },
  "BeeInfo.rel_pos": { label: "где пчела {obj} от меня", tip: "Точка относительно меня." },
  "BeeInfo.dist": { label: "расстояние до пчелы {obj}", tip: "Метры." },
  "BeeInfo.vel": { label: "скорость пчелы {obj}", tip: "Вектор, м/с." },

  "Obstacle.pos": { label: "где препятствие {obj}", tip: "Ближайшая точка оси препятствия." },
  "Obstacle.rel_pos": { label: "где препятствие {obj} от меня", tip: "Точка относительно меня." },
  "Obstacle.dist": { label: "расстояние до препятствия {obj}", tip: "До оси; до поверхности — минус радиус." },
  "Obstacle.radius": { label: "радиус препятствия {obj}", tip: "Метры." },

  "Message.from_id": { label: "от кого сообщение {obj}", tip: "Номер пчелы; -1 — сам улей." },
  "Message.pos": { label: "откуда сообщение {obj}", tip: "Точка, где его отправили." },
  "Message.rel_pos": { label: "откуда сообщение {obj} от меня", tip: "Точка относительно меня." },
  "Message.values": { label: "числа сообщения {obj}", tip: "Список до 8 чисел." },

  "Pheromones.values": { label: "запахи по клеткам {obj}", tip: "values[i][j][канал] в клетках 3×3 вокруг." },
  "Pheromones.gradient": { label: "куда усиливаются запахи {obj}", tip: "gradient[канал] = [gx, gy]." },
  "Pheromones.strength": { label: "сила запаха канала {channel} в {obj}", tip: "Сила запаха прямо под пчелой." },
  "Pheromones.direction": { label: "куда сильнее запах канала {channel} в {obj}", tip: "Направление длиной 1." },

  "Vec.x": { label: "x точки {obj}", tip: "Координата x, м.", beginner: true },
  "Vec.y": { label: "y точки {obj}", tip: "Координата y, м.", beginner: true },
  "Vec.z": { label: "z точки {obj}", tip: "Высота, м." },
  "Vec.length": { label: "длина вектора {obj}", tip: "Длина." },
  "Vec.length_xy": { label: "длина по горизонтали {obj}", tip: "Длина без высоты." },
  "Vec.normalized": { label: "направление {obj} длиной 1", tip: "Нулевой остаётся нулевым." },
  "Vec.dist": { label: "расстояние от {obj} до {other}", tip: "Метры." },
  "Vec.dist_xy": { label: "расстояние по горизонтали от {obj} до {other}", tip: "Метры, без высоты." },

  "Counts.scout": { label: "разведчиков в {obj}", tip: "Все живые разведчики." },
  "Counts.forager": { label: "сборщиков в {obj}", tip: "Все живые сборщики.", beginner: true },
  "Counts.guard": { label: "охранников в {obj}", tip: "Все живые охранники." },
  "Counts.house": { label: "домашних пчёл в {obj}", tip: "Все живые домашние пчёлы." },
  "Counts.total": { label: "всего пчёл в {obj}", tip: "Все живые пчёлы.", beginner: true },
  "Counts.in_hive": { label: "сидят в улье (по типам) {obj}", tip: "Словарь: тип → сколько в улье." },
  "Counts.flying": { label: "в полёте (по типам) {obj}", tip: "Словарь: тип → сколько летает." },

  "Larva.kind": { label: "тип личинки {obj}", tip: "Кто из неё выведется." },
  "Larva.left_s": { label: "сколько расти личинке {obj}", tip: "Секунды при одной няньке." },

  // ------------------------------------------------------------ домашняя пчела
  "HouseBee.process": { label: "перерабатывать нектар", tip: "Нектар → мёд.", beginner: true },
  "HouseBee.nurse": { label: "нянчить личинки", tip: "Чем больше нянек, тем быстрее выведение.", beginner: true },
  "HouseBee.rest": { label: "отдыхать", tip: "Мёд всё равно ест.", beginner: true },
  "HouseSensors.tick": { label: "номер тика (дома)", tip: "10 тиков в секунду." },
  "HouseSensors.time": { label: "время матча, с (дома)", tip: "Сколько секунд прошло." },
  "HouseSensors.me": { label: "я (домашняя)", tip: "Номер, тип и занятие." },
  "HouseSensors.hive_nectar": { label: "нектар на складе", tip: "Ещё не переработан.", beginner: true },
  "HouseSensors.hive_honey": { label: "мёд на складе", tip: "Единицы мёда.", beginner: true },
  "HouseSensors.breeding_queue": { label: "очередь личинок", tip: "Список личинок.", beginner: true },
  "HouseSensors.counts": { label: "сколько пчёл (дома)", tip: "Счётчики по типам." },
  "HouseMe.id": { label: "мой номер (дома)", tip: "Номер домашней пчелы." },
  "HouseMe.kind": { label: "мой тип (дома)", tip: "Всегда \"house\"." },
  "HouseMe.task": { label: "чем я занята", tip: "\"rest\", \"process\" или \"nurse\"." },

  // ------------------------------------------------------------ улей
  "Hive.breed": {
    label: "вывести {kind}", full: "вывести {kind} штук {n}",
    tip: "Мёд списывается сразу. Не хватает мёда или улей полон — личинки не будет.", beginner: true,
  },
  "Hive.cancel_breeding": { label: "отменить личинку {kind}", tip: "Последняя такая личинка; мёд вернётся." },
  "Hive.signal": { label: "улей сообщает {values}", tip: "Список до 8 чисел пчёлам у летка (15 м)." },
  "Hive.tick": { label: "номер тика (улей)", tip: "10 тиков в секунду." },
  "Hive.time": { label: "время матча, с (улей)", tip: "Сколько секунд прошло.", beginner: true },
  "Hive.honey": { label: "мёд в улье", tip: "Единицы мёда.", beginner: true },
  "Hive.nectar": { label: "нектар в улье", tip: "Ещё не переработан.", beginner: true },
  "Hive.counts": { label: "сколько пчёл", tip: "Счётчики по типам.", beginner: true },
  "Hive.queue": { label: "очередь выведения", tip: "Список личинок." },
  "Hive.max_bees": { label: "предел пчёл", tip: "Больше пчёл (с личинками) быть не может." },
  "Hive.costs": { label: "цены выведения", tip: "Словарь: тип → цена в мёде." },
  "Hive.messages": { label: "сообщения улью", tip: "От своих пчёл у летка." },
  "Hive.memory": { label: "память улья", tip: "Словарь — всё, что в нём, сохранится." },
};

/** Блоки, которых нет в api.py: программы, Python, словари, значения списков. */
export const CUSTOM_RU = {
  bees_program_bee: { label: "Программа пчелы {kind}", tip: "Что делает каждая пчела этого типа. Выполняется раз в тик; с «ждать» — по шагам, как рецепт." },
  bees_program_hive: { label: "Программа улья", tip: "Решения улья: выведение, сообщения. Выполняется раз в тик." },
  bees_python_line: { label: "строка Python: {code}", tip: "Одна строка кода Python как есть." },
  bees_python_expr: { label: "выражение Python {code}", tip: "Выражение Python как есть." },
  bees_dict_get: { label: "из словаря {dict} взять {key}", tip: "Значение по ключу (нет ключа — «ничего»)." },
  bees_dict_set: { label: "в словаре {dict} записать {key} = {value}", tip: "Запомнить значение по ключу." },
  bees_literal_Kind: { label: "тип {value}", tip: "Тип пчелы." },
  bees_literal_Weather: { label: "погода {value}", tip: "Значение погоды для сравнения." },
  bees_literal_Task: { label: "занятие {value}", tip: "Занятие домашней пчелы." },
};

/** Поправки к русскому словарю Blockly: имена по умолчанию — сразу годные имена Python. */
export const BLOCKLY_MSG = {
  PROCEDURES_DEFNORETURN_PROCEDURE: "действие",
  PROCEDURES_DEFRETURN_PROCEDURE: "вычислить",
};

/** Встроенные блоки Blockly в стартовом наборе (подписи — из русского словаря Blockly). */
export const BUILTIN_BEGINNER = {
  logic: ["controls_if", "logic_compare", "logic_operation", "logic_negate", "logic_boolean", "logic_null"],
  loops: ["controls_repeat_ext", "controls_whileUntil", "controls_forEach"],
  math: ["math_number", "math_arithmetic", "math_random_int"],
  text: ["text", "text_print"],
};
/** Остальные встроенные блоки — в «Продвинутых». */
export const BUILTIN_ADVANCED = {
  logic: ["logic_ternary"],
  loops: ["controls_for", "controls_flow_statements"],
  math: ["math_single", "math_trig", "math_constant", "math_round", "math_modulo", "math_constrain",
    "math_random_float"],
  text: ["text_join"],
  lists: ["lists_create_empty", "lists_create_with", "lists_length", "lists_isEmpty", "lists_getIndex",
    "lists_setIndex"],
};

/** Тексты генератора и проверок. `{x}` — подстановки. */
export const MESSAGES = {
  waitField: "ждать",
  askPrefix: "удалось:",
  fullSuffix: "(всё)",
  header: "Сгенерировано из блоков ({file}). Не правьте этот файл вручную:",
  header2: "пока скрипт в режиме «Блоки», редактор перезаписывает его при каждом сохранении.",
  header3: "Чтобы писать на Python, нажмите в редакторе «Перейти на Python».",
  duplicate: "Программа для типа «{kind}» уже есть выше — эта не попадёт в код.",
  wrongSubject: "Этот блок не для программы «{where}».",
  procWrongSubject: "Процедура «{name}» использует блоки, которых нет у программы «{where}».",
  procMixed: "В одной процедуре блоки для разных программ: «{a}» и «{b}».",
  emptyInput: "Не заполнено: {input}.",
  badName: "Имя «{name}» не подходит: нужны буквы, цифры и _, не с цифры и не слово Python.",
  reservedName: "Имя «{name}» уже занято в программе — выберите другое.",
  nameClash: "Имя «{name}» есть и у переменной, и у процедуры.",
  recursion: "Процедура «{name}» вызывает сама себя ({path}). Так можно, но вызовы должны когда-то закончиться — иначе пчела зависнет.",
  unknownProc: "Нет процедуры «{name}».",
  returnOutside: "«Вернуть» работает только внутри процедуры.",
  flowOutside: "«Прервать цикл» работает только внутри цикла.",
  unsetVariable: "Переменная «{name}» здесь ещё не задана.",
  unknownBlock: "Неизвестный блок {type}.",
  emptyCode: "Пустая строка Python.",
  programWhere: { scout: "разведчик", forager: "сборщик", guard: "охранник", house: "домашняя пчела", hive: "улей" },
  inputNames: { obj: "объект", other: "точка", CONDITION: "условие", IF0: "условие", TIMES: "сколько раз", BOOL: "условие",
    LIST: "список", A: "левая часть", B: "правая часть", VALUE: "значение", NUM: "число", FROM: "от", TO: "до",
    dict: "словарь", key: "ключ", value: "значение", DIVIDEND: "делимое", DIVISOR: "делитель", LOW: "от", HIGH: "до" },
};
