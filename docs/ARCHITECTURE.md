# Архитектура SwarmLab

## 1. Слои

```
┌────────────────────────────────────────────────────────────────────┐
│  Клиенты:  web/ (Three.js вьюер, редактор)   MuJoCo-вьюер (отладка) │
└───────────────▲───────────────────────────────▲────────────────────┘
                │ WebSocket / HTTP               │ in-process (debug)
┌───────────────┴────────────────────┐           │
│  swarmlab.server  (FastAPI)        │           │
│  матчи, стриминг кадров, реплеи    │           │
└───────────────▲────────────────────┘           │
                │ Python API                     │
┌───────────────┴────────────────────────────────┴────────────────────┐
│  swarmlab.core   — цикл симуляции, часы, конфиг, RNG, реплей,        │
│                    раннер-хост, контракты (Module, PhysicsBackend,   │
│                    AgentLink), бенчмарк                              │
└───────────────▲──────────────────────────────▲───────────────────────┘
                │ реализует контракты           │ протокол сенсоры→команды
┌───────────────┴─────────────────┐   ┌────────┴──────────────────────┐
│ swarmlab.bees  (модуль)          │   │ Раннер игрока (отд. процесс)   │
│  world, physics(MuJoCo), autopilot│   │  swarmlab.runner + код игрока │
│  sensors, comms, economy, enemies │   │  (позже: контейнер / робот)   │
│  scoring, api (для игроков)       │   └───────────────────────────────┘
└──────────────────────────────────┘
```

Правило зависимостей: `server → core ← bees`, `runner → core.protocol`, `bees.api` — единственное, что импортирует код игрока. `core` не импортирует ни `bees`, ни `server`, ни `mujoco`.

## 2. Структура репозитория

**Ветки (DECISIONS №98).** `master` — ядро и общие документы; `bees`, `city`, `quarry` — ядро + модуль. Ядро правится только в `master` и вливается в ветки модулей (`git merge master`), обратно — никогда. В `master` из дерева ниже есть общее: `src/swarmlab/{core,runner,server,cli.py}`, `web/js/core/`, `web/vendor/`, `web/js/modules/registry.js` (пустой), `tests/core/`, `tests/portal/`, `tests/web/`, общие документы и промты ядра `prompts/M9a.md`, `prompts/M9b.md`. Код и материалы модуля (`bees/`, `configs/`, `examples/`, `tools/`, `BEES_SPEC`, `PLAYER_API`, `CHEATSHEET`, `DEMO`) — в ветке `bees`; там же промты M0–M8 и M9c. Рабочие заготовки Dockerfile и `docker/` для M9b — в `master`.

Как ядро находит модуль без имени в коде:
- Python — entry points `swarmlab.modules` и `swarmlab.agent_hosts` в `pyproject.toml` ветки; `core.module.default_module()` — единственный установленный модуль (файл матча без `module:`, папка скриптов редактора `examples/<модуль>`);
- браузер — `web/js/modules/registry.js` ветки: `{<модуль>: {viewer, editor}}`; в `master` пусто, лобби пишет «в этой ветке нет модуля».

```
swarmlab/
  AGENTS.md  CLAUDE.md (указатель на AGENTS.md)  README.md  pyproject.toml
  docs/        PRD, ARCHITECTURE, BEES_SPEC, ROADMAP, DECISIONS, WORKFLOW, PLAYER_API (справочник игрока), CHEATSHEET (памятка школьника)
  prompts/     M9a.md, M9b.md — master; M0–M8, M9c — bees
  configs/
    profiles/  small.yaml medium.yaml large.yaml   # timing: + секция на модуль (bees: …)
    matches/   demo.yaml sandbox.yaml
    bench/     small.yaml medium.yaml large.yaml   # матчи `swarmlab bench` (нагрузка как в игре)
    bees/      defaults.yaml          # все параметры механик
  src/swarmlab/
    core/
      sim.py          # Simulation: цикл, три частоты
      clock.py        # фиксированный шаг, накопитель времени
      config.py       # загрузка/слияние YAML, валидация (pydantic)
      rng.py          # seed → независимые потоки RNG по подсистемам
      spatial.py      # равномерная сетка поиска соседей, O(N·k)
      module.py       # контракт Module
      physics.py      # контракт PhysicsBackend
      protocol.py     # сообщения раннера: SensorBatch / CommandBatch
      program.py      # loop() агента в потоке greenlet между тиками, Wait/Order (DECISIONS №84)
      runner_host.py  # запуск и обслуживание процессов-раннеров
      replay.py       # запись/чтение реплеев, хеш
      bench.py        # бенчмарк и рекомендация профиля
      series.py       # серии матчей: seed подряд, процесс на матч, series.json, results.csv (M7c)
    runner/
      main.py         # процесс-раннер: рукопожатие, цикл, перехват print
      __main__.py     # python -m swarmlab.runner
    bees/
      module.py       # BeesModule(Module)
      world.py        # генерация мира по seed, препятствия-капсулы
      state.py        # SoA-состояние пчёл по слотам пула тел
      physics/        # mjcf.py, backend.py (MuJoCo), forces.py (NumPy: сопротивление, энергия…)
      autopilot.py
      sensors.py  comms.py  pheromones.py
      control.py      # команды игрока: разбор CommandBatch, режимы движения (SoA)
      player_host.py  # AgentHost: код игрока в раннере (импорт скрипта, Sensors, исключения)
      demo.py         # доверенные демо-пилоты без раннера (M0, M1)
      economy.py  enemies.py  weather.py   # счёт и выбывание — в module.py
      api.py          # то, что видит игрок: Scout, Collector, Worker, Hive, Point… (DECISIONS №85)
    server/
      app.py          # FastAPI: REST, WS-стрим, статика web/
      scripts.py      # скрипты редактора: папка выбранного модуля, проверка имени, ast.parse, файл блоков X.blocks.json
      projects.py     # проекты .swarm: проверка формата, папка projects/, копия в редактор (M7c)
      worker.py       # процесс живого матча (python -m swarmlab.server.worker)
      public.py       # портал (serve --public, M9a): вход, охрана API и WS, CSRF, маршруты профиля
      accounts.py     # настройки портала, SQLite, argon2, сессии, лимиты частоты
      storage.py      # папки пользователей, свои скрипты поверх общих примеров, реплеи с квотой
      public.yaml     # умолчания настроек портала (квоты, лимиты, cookie, прокси)
    cli.py            # swarmlab run|series|bench|replay|serve
  web/                # фронтенд без сборки: index.html, js/core/, js/modules/<модуль>/, vendor/
  examples/bees/      # template.py, example_basic.py, example_smart.py, example_blocks.py (+ .blocks.json) — только чтение в редакторе; my_bees.py и свои скрипты
  projects/           # загруженные в меню проекты .swarm: <имя>.py, <имя>.blocks.json, <имя>.swarm (не видны в редакторе; в .gitignore)
  replays/            # реплеи матчей; replays/series/<YYYYMMDD-HHMMSS>-<проект>/ — серии (s<seed>.swr, series.json, results.csv, logs/)
  tools/              # calibrate.py, balance.py, gen_api_hints.py, gen_blocks_api.py, blocks_to_py.mjs — служебные скрипты разработчика
  tests/
    core/             # общие контракты и механизмы ядра
    portal/           # аккаунты, хранение и лимиты без настоящего модуля
    web/              # общие JS-форматы; запуск проверок через Node.js
```

## 3. Контракты ядра

### 3.1 Module

```python
class Module(Protocol):
    name: str

    def build(self, cfg: MatchConfig, rng: RngRegistry) -> None: ...  # мир, тела, команды
    def physics(self) -> PhysicsBackend: ...
    def agent_teams(self) -> list[TeamSpec]: ...  # какие раннеры запускать
    def decide(self, tick: int) -> None: ...  # доверенные агенты в процессе: боты, демо
    def collect_sensors(self, team: TeamId) -> SensorBatch: ...
    def apply_commands(self, team: TeamId, cmds: CommandBatch) -> None: ...
    def pre_physics(self, dt: float) -> None: ...  # силы, автопилот (векторно)
    def post_physics(self, dt: float) -> None: ...  # энергия, контакты, экономика, события
    def snapshot(self) -> Frame: ...  # для реплея и стрима
    def score(self) -> ScoreBoard: ...
    def is_finished(self) -> bool: ...
```

Необязательно: `ScoreColumns.score_columns()` — какие метрики счёта показывать таблицей серии (M7c); `DebugViewable.open_debug_viewer()` — отладочное окно движка (`--mj-viewer`); `Replayable.scene()` — статическая сцена для заголовка реплея и вьюеров, `Replayable.apply_frame(frame, nxt, alpha)` — выставить тела по кадру реплея (показ реплея в отладочном окне без шага физики); `Describable.describe()` — строки о правилах матча для CLI. Модули регистрируются в entry points `swarmlab.modules` и загружаются ядром по имени (`core.module.load_module`), без импорта в коде ядра.

### 3.2 PhysicsBackend

```python
class PhysicsBackend(Protocol):
    def step(self, n_substeps: int) -> None: ...
    def set_forces(self, body_ids: np.ndarray, forces: np.ndarray, torques: np.ndarray | None) -> None: ...
    def poses(self) -> tuple[np.ndarray, np.ndarray]: ...   # pos (N,3), quat (N,4)
    def velocities(self) -> np.ndarray: ...                  # (N,6)
    def contacts(self) -> ContactList: ...                   # пары тел + силы
    def set_active(self, body_ids, active) -> None: ...      # пул тел, см. 3.5
```

Пчёлки реализуют его на MuJoCo. Карьер позже — MuJoCo + Project Chrono (грунт). Город — свой упрощённый бэкенд без MuJoCo.

### 3.3 AgentLink и протокол раннера

`AgentLink` — канал «команда ↔ раннер». Реализации:
- `ProcessLink` — локальный процесс (до 20.10);
- в публичном режиме портала (M9b, DECISIONS №93) — тот же `ProcessLink`, процесс раннера запускается под nsjail; отдельного канала нет;
- `ContainerLink` — контейнер на сервере (арена, отложена, DECISIONS №90);
- `RobotLink` — мост к реальным роботам (позже).

Протокол один для всех (`core/protocol.py`, версия `v = 1`):
- Транспорт: stdin/stdout, кадр = 4 байта длины (uint32 LE) + msgpack, предел 16 МБ. Никакого pickle и ext-типов (небезопасно и непереносимо).
- Каждое сообщение — словарь с типом `t`:

| Направление | `t` | Поля |
|---|---|---|
| ядро → раннер | `hello` | `v, module, team, script, seed, budget_ms, options` (правила матча для API игрока) |
| раннер → ядро | `ready` | `v, ok, classes {kind: имя класса}, error` (трассировка, если скрипт не загрузился), `log` |
| ядро → раннер | `sensors` | `SensorBatch {tick, team, budget_ms, team_view, agents: [AgentSensors…]}` (у пчёлок `team_view` — улей) |
| раннер → ядро | `commands` | `CommandBatch {tick, commands: {agent_id: Command}, team_command \| None, cpu_ms, errors: [agent_id], log: [строки]}` (у пчёлок `team_command` — решения улья) |
| ядро → раннер | `stop` | — |

- В `commands` только агенты, которые что-то решили; остальные продолжают прошлую команду. `log` — вывод `print` игрока и трассировки.
- **Ожидание команды** (DECISIONS №61, №84). `loop()` каждого агента живёт только в раннере, в своём потоке `greenlet` (`core/program.py`, `Program`; без импорта модулей), ядро и модуль его не видят. Хост переключает потоки строго по порядку `uid` (улей — последним); конец прохода `loop()` — ожидание следующего тика. Команда, выполнения которой ждут, переключает поток обратно в хост и уходит модулю с полем `"wait": seq` (номер ожидания, > 0). Модуль хранит ожидание по слотам, сам проверяет условие и таймаут в игровом времени и кладёт статус в сенсоры агента: `"wait": [seq, состояние, результат]` (0 — идёт, 1 — выполнено, 2 — не вышло; результат — номер найденного цветка или −1). Хост продолжает поток, когда видит свой `seq` с состоянием 1 или 2; не видит своего `seq` (команда отброшена бюджетом или пропуском тика) — шлёт команду ещё раз, повтор не сбрасывает таймаут. `wait(секунды)` хост считает сам по времени из сенсоров. Агент пропал из пакета (погиб) или модуль увеличил `me["epoch"]` (конец автовозврата) — `greenlet.throw(GreenletExit)`, `finally` выполняется; `stop` — `AgentHost.close()`.
- Сторона модуля в раннере — `AgentHost` (`load(hello)`, `step(SensorBatch) → CommandBatch`), находится по имени модуля в entry points `swarmlab.agent_hosts` (у пчёлок — `bees/player_host.py`). Формат `Command` пчёлок — BEES_SPEC §3.3.

### 3.4 Раннер и бюджет

- Один процесс на команду (улей): `subprocess.Popen([sys.executable, "-m", "swarmlab.runner"])` с пайпами stdin/stdout/stderr — без `fork`, одинаково на Windows (spawn) и Linux. Окружение: `PYTHONHASHSEED=0`, `PYTHONIOENCODING=utf-8`; на Windows без окна консоли. Путь к скрипту приходит в `hello`; скрипт импортируется **внутри раннера** (`importlib` из файла, папка скрипта — в `sys.path`).
- Рукопожатие: все раннеры стартуют параллельно, ядро ждёт `ready` до `startup_timeout_s` (10 с). Раннер подменяет `sys.stdout` буфером (`print` уходит в `log`, протокол не ломается), `sys.stdin` — пустым; задаёт `random.seed(seed·1000 + team)` — один seed и одни скрипты дают одинаковые решения. Скрипт не загрузился (синтаксическая ошибка…) → `ready{ok: false}` с трассировкой и номером строки; команда отключается без перезапусков, её агенты держат прошлые команды.
- Раннер держит объекты пчёл и их потоки `loop()` между тиками (пчела может хранить своё состояние в `self`, §3.3). Время работы потока до следующего ожидания входит в бюджет; пока агент ждёт команду, его код не выполняется. Бесконечный цикл без команд не отдаёт управление — его ловит жёсткий таймаут (ниже).
- Бюджет — время кода игрока на всю команду за тик решений, по умолчанию 20 мс локально. Меряет хост в раннере `time.perf_counter()` только вокруг переключений в код игрока (потоки `loop()`, конструкторы, `finally`), без разбора сенсоров и сборки команд (DECISIONS №32: на Windows `process_time` шагает по 15.625 мс).
- Превышение бюджета: команды этого тика отбрасываются, агенты продолжают последнюю команду; счётчик нарушений в статистике (`RunnerStats.over_budget`) и строка в логе.
- Жёсткий таймаут ядра: нет ответа за `hard_timeout_ms` (по умолчанию 200 мс) → тик пропущен; пока не пришёл ответ на старый пакет, раннер «занят» и новых пакетов не получает (тики тоже пропущены, опоздавший ответ отбрасывается). `misses_before_restart` (3) пропуска подряд → процесс убивается и запускается заново (состояние `self` теряется, это видно в логе); пока новый раннер запускается, тики не считаются пропущенными. После `max_restarts` (20) команда отключается.
- Исключение в `loop()` одной пчелы → эта пчела делает `stop()`, трассировка по файлам игрока уходит в лог; одинаковые ошибки повторно — с подсчётом (1-й, 10-й, 100-й… раз); на следующем тике её `loop()` начинается сначала; остальные пчёлы работают.
- Отправка пакетов всем раннерам параллельно, ожидание с общим дедлайном — ядро ждёт самого медленного раннера, а не сумму. На Windows `select()` не работает с пайпами, поэтому у каждого `ProcessLink` свои потоки-демоны: писатель (очередь → stdin, отправка не блокирует цикл, даже если раннер завис и пайп полон), читатель stdout (кадры → очередь) и читатель stderr (→ лог). Часы стены (`time.monotonic`) — только для таймаутов в `runner_host.py`.
- Завершение: `stop` → 1 с на выход → `kill`. Раннер читает stdin в отдельном потоке: EOF (ядро закрылось или умерло) → `os._exit`, даже если код игрока завис в `while True` — сирот не остаётся. Обычный выход раннера — тоже `os._exit` (Python 3.13 падает на буфере stdin, который держит поток-читатель).
- Параметры — общая секция `runner:` профиля/матча (`budget_ms, hard_timeout_ms, misses_before_restart, startup_timeout_s, max_restarts`), как `timing:`. Логи команд — `logs/<матч>/<команда>.log` (`--log-dir`).
- `swarmlab.core` экспортирует имена лениво (PEP 562), чтобы раннер, импортируя только `core.protocol`, стартовал без pydantic и NumPy (~0.2 с вместо ~0.6 с).

### 3.5 Динамические тела

Пчёлы рождаются и гибнут, а модель MuJoCo фиксирована после компиляции. Решение — **пул тел**: модель компилируется с `max_bees` телами на улей (из профиля), неактивные «припаркованы» под картой с выключенными столкновениями (`contype=conaffinity=0` через `model.geom_*` на лету), вес уравновешен, сил от модуля нет. Рождение = активация слота: тип (радиус, масса) задаётся на лету, любой слот может стать любым типом (DECISIONS №25–26). Горячий цикл идёт только по слотам в воздухе.

## 4. Время и частоты

| Частота | По умолчанию | Что происходит |
|---|---|---|
| Физика | 200 Гц (dt = 5 мс) | `pre_physics` → `mj_step` → `post_physics` |
| Решения | 10 Гц (каждые 20 шагов физики) | сбор сенсоров → раннеры → применение команд |
| Кадр | 10 Гц в реплей, до 30 Гц в живой стрим | `snapshot()` |
| Рендер | 30–60 FPS в браузере | интерполяция между кадрами |

Между тиками решений действует последняя команда; автопилот работает на частоте физики.

Время симуляции отделено от реального: headless гонит максимально быстро, живой режим притормаживает до реального времени, если успевает. Если машина не успевает — симуляция идёт медленнее реального, шаг физики **не меняется**.

## 5. Детерминизм и реплеи

- `RngRegistry(seed)` выдаёт независимые `np.random.Generator` по именам подсистем (`world`, `weather`, `enemies`, `sensor_noise`…), чтобы добавление новой подсистемы не сдвигало остальные.
- MuJoCo однопоточный, порядок операций фиксирован. Детерминизм гарантируется **на одной машине и одной версии**; между платформами битовое совпадение не гарантируется, поэтому реплей хранит **состояния**, а не только входы.
- Формат реплея (`.swr`, `core/replay.py`, DECISIONS №39): `b"SWR1"` + один поток zstd (уровень 9) из записей «u32 LE длина + msgpack»:
  - `header` — версии пакетов и движка, платформа, полный слитый конфиг, seed, профиль, команды со скриптами (путь + sha256), `scene` модуля (мир, рамка квантования, справочники);
  - `frame` 10 Гц — `{tick, time, arrays, events}`; массивы NumPy в msgpack — `{"__nd__": [dtype, shape, bytes]}`, компактные типы выбирает модуль в `snapshot()`. У пчёлок в кадре только тела в воздухе: позиции `uint16` с фиксированной точкой в рамке карты (шаг ≈ 4.6 мм на 300 м), скорости `float16` (вместо кватерниона: ориентацию вьюер берёт по скорости), энергия/груз/HP/нектар — доли `uint8`;
  - `footer` — число кадров, хеш, итоговый счёт (нет, если матч оборвался — кадры всё равно читаются).
- Хеш реплея — sha256 несжатых байтов записей `frame` по порядку (без заголовка: в нём пути и версии). Если матч закончился досрочно, ядро пишет последний кадр сразу, чтобы не потерять события.
- `swarmlab run` пишет реплей по умолчанию (`replays/<матч>-s<seed>.swr`, `--replay`, `--no-replay`); `swarmlab replay <файл>` печатает счёт, сводку событий и проверяет хеш; `--mj-viewer` собирает мир заново по seed и конфигу из заголовка (без раннеров) и проигрывает кадры с интерполяцией.
- Тест детерминизма: два прогона → одинаковый хеш (при условии, что раннеры не пропускали тиков: пропуск зависит от часов стены).

## 6. Масштабирование

**По мощности машины (сейчас):**
- Профили `small / medium / large / custom` задают: число ульев, `max_bees` на улей, врагов, размер карты, плотность цветов и деревьев, частоту решений.
- `swarmlab bench` (`core/bench.py`, DECISIONS №41) — для каждого профиля матч `configs/bench/<профиль>.yaml` (раннеры, враги, ~80% пула пчёл), прогрев 3 с, замер `min(10 с симуляции, 10 с стены)` с записью реплея; таблица RTF и рекомендация самого тяжёлого профиля с RTF ≥ 1.2; результат — в `~/.swarmlab/bench.json` (`SWARMLAB_HOME`), `swarmlab bench --show` — без прогона.
- Горячий цикл векторизован (NumPy по всем телам); поиск соседей для сенсоров — равномерная пространственная сетка, O(N·k).
- Рендер масштабируется независимо: InstancedMesh, LOD, дальность прорисовки.

**По серверу (портал, M9b, DECISIONS №94):**
- Матч = процесс воркера, как в локальном режиме; не больше 4 живых матчей на сервер и одного на пользователя, остальные — в очереди. Лимиты — в YAML-конфиге сервера.
- Раннеры игроков под nsjail, тот же протокол (§3.3).
- Живой стрим — только владельцу матча; матч без зрителей 60 с останавливается.

**Огромный мир (только Город, позже):** пространственное разбиение на узлы. Сейчас лишь не мешаем этому: состояние в SoA-массивах, без глобальных синглтонов.

## 7. Сервер и вьюер

- `swarmlab serve [--host 127.0.0.1] [--port 8000] [--open] [--root .] [--max-matches 1]` поднимает FastAPI (`server/app.py`), отдаёт `web/`. Сервер импортирует только `core` (тест изоляции).
- REST:
  - `GET /api/configs` — матчи `configs/matches/*.yaml` (имя, описание из первой строки-комментария, профиль, длительность);
  - `POST /api/matches` `{match, seed?, overrides?[], speed?, scripts?[]}` → сведения о матче с `id`; ошибка конфига — 400; `scripts` — имена скриптов редактора, их синтаксис проверяется `ast.parse` до запуска (ошибка — 400 `{script, line, col, message}`, процесс не запускается);
  - `GET /api/matches`, `GET /api/matches/{id}` (состояние, время, скорость, RTF, счёт), `POST /api/matches/{id}/stop`;
  - `GET /api/replays` — `.swr` в `replays/` (кроме пишущихся), `GET /api/replays/{id}` — файл реплея;
  - редактор (M5, DECISIONS №47): `GET /api/scripts` (имя, путь, `readonly`, `mode`), `GET /api/scripts/{name}` (`text`, `blocks`), `PUT /api/scripts/{name}` `{text, blocks?}` → `{ok, errors[]}` — только в `examples/bees/`, проверка имени, `template.py` и `example_*.py` только для чтения; `POST /api/scripts/check` `{text}` → синтаксические ошибки `{line, col, end_line, end_col, message, block}`. Блоки (M7b, DECISIONS №62): `blocks` = `{format: 1, mode: "blocks" | "python", workspace}` пишется в `X.blocks.json` рядом с `X.py`; после `mode: "python"` запись блоков — 409; `block` — id из комментария `# block:<id>` на строке ошибки (и в 400 при запуске матча); `GET /api/profiles` — профили и их YAML; `GET /api/help` — памятка `docs/CHEATSHEET.md`.
  - проекты (M7c, DECISIONS №63–65): `POST /api/projects` (тело — файл `.swarm`) → `{name, title, mode, created, uploaded, path, sha256, status: new | same}`; `GET /api/projects`, `GET /api/projects/{name}` (`code`, `blocks`), `POST /api/projects/{name}/to-editor` `{name?}` → копия в `examples/bees/` под свободным именем. Формат `.swarm` проверяют и сервер (`server/projects.py`), и браузер (`js/core/project.js`): неизвестный `format`, нет `code`, битый JSON → 400 с понятным текстом. Другое содержимое под тем же именем — новый проект `<имя>-YYYYMMDD-HHMM`. В `POST /api/matches` и `POST /api/series` поле `projects[]` — проекты, синтаксис которых проверить (ошибка — 400 `{project, line, col, message}`); в `hives` — путь `projects/<имя>.py`;
  - серии (M7c, DECISIONS №66–67): `POST /api/series` `{match, overrides, start_seed?, n, jobs?, team?, scripts?, projects?}` → `series.json` серии (сервер запускает `python -m swarmlab.cli series … --progress-json` и ждёт первую строку `{t: "start", id, dir}`; одновременно — одна серия, вторая — 409); `GET /api/series` — прошлые и идущая (из папок `replays/series/`, ничего не удаляется); `GET /api/series/{id}` — `series.json` + `done` (прогресс — опросом раз в 1 с; `state: interrupted`, если процесс серии умер); `POST /api/series/{id}/stop` — файл `.stop` в папке серии; `GET /api/series/{id}/replays/{seed}` — реплей матча.
- CLI серии (M7c, `core/series.py`, DECISIONS №66): `swarmlab series <матч.yaml> --n 10 --seed S [--set ПУТЬ=ЗНАЧЕНИЕ …] [--jobs N] [--out replays/series] [--team H]`. Матч i — seed `S + i`; каждый матч — процесс `python -m swarmlab.core.series` (задание — JSON-строка в stdin, итог — JSON-строка в stdout; сторож stdin запускается только после сборки мира: на Windows поток, ждущий чтения из пайпа, блокирует загрузку DLL). Остановка — EOF в stdin матча, через 15 с — `taskkill /T` (venv-`python.exe` на Windows — лаунчер). `series.json` переписывается атомарно после каждого матча (повтор `os.replace`, пока сервер держит файл открытым). Колонки таблицы — `ScoreColumns.score_columns()` модуля (`ScoreColumn {key, title, worst}`) + ошибки кода из `RunnerStats` (`agent_errors`, `missed`, `over_budget`); худший матч — по колонкам с `worst` по порядку (у пчёл: место, потом мёд). `results.csv` — UTF-8 с BOM, `;`, дробная часть через запятую (Excel на русской Windows; pandas — `sep=";", decimal=","`).
- Живой матч — отдельный процесс `python -m swarmlab.server.worker` (DECISIONS №43): канал stdin/stdout как у раннера; реплей пишется в `replays/<матч>-s<seed>-<дата-время>.swr`, логи кода игрока — `logs/<id>/`. Реальное время (`RealtimePacer`), пауза и скорость 0.25–8 — на лету; не успевает — медленнее реального, шаг физики тот же. Одновременно — `--max-matches` матчей, новый вытесняет старый. Закрытая вкладка матч не останавливает; EOF stdin (сервер умер) — воркер дописывает реплей и выходит.
- WS `/ws/matches/{id}` (сервер → бинарный msgpack, массивы `{"__nd__": [dtype, shape, bytes]}` как в реплее):

| `t` | Поля |
|---|---|
| `header` | заголовок реплея (`module, seed, profile, duration_s, config, teams, scene`) + `match_id, frame_hz, runners [{team, name, ok, error}]` |
| `frame` | `tick, time, arrays, events` — байт в байт запись кадра `.swr` |
| `status` | `state` (starting / running / paused / finished / stopped / error), `speed, time, duration_s, rtf, score, error` — при смене и раз в 1 с |
| `log` | `team, name, time, lines` — новые строки лога кода игрока улья (`print`, трассировки, предупреждения ядра); опоздавшему зрителю — последние 1000 пакетов после header |
| `footer` | `frames, hash, score, replay` — реплей дописан |

  Клиент → JSON: `{t: "pause"}`, `{t: "resume"}`, `{t: "speed", value}`, `{t: "stop"}`. Неизвестный матч — закрытие с кодом 4404. Подключившийся позже получает header, последний status и кадр.
- Вьюер `web/` — ES-модули без сборщика, библиотеки в `web/vendor/` (версии — `VERSIONS.md`, DECISIONS №44):
  - M7c: в лобби — форма матча на `MatchPanel` модуля (у каждого улья пример или загруженный проект, seed по умолчанию случайный, 🎲), «▶ Смотреть матч», «Серия…», проекты (загрузка кнопкой и перетаскиванием `.swarm`, «Открыть в редакторе»), список серий. Редактор: вьюер слева, блоки/код справа (`--ew` — ширина редактора), верхняя панель «Блоки | Python», ↶/↷, имя проекта, «⬇ Экспорт проекта» (Blob), «📂 Открыть проект…»; блоки — рендерер `zelos`, категории с иконкой и справкой, поиск («Найдено» — динамическая категория по тексту блоков), подсказка в пустой программе. Общие модули: `project.js` (`.swarm`), `trust.js` (sha256 кода в `localStorage["swarmlab.trusted"]`), `ui/dialog.js`, `ui/series.js` (прогресс, таблица, «Смотреть» → `ReplaySource`).
  - `js/core/` — общее: `app.js` (лобби → источник → вьюер модуля по `header.module`; режим `#editor`), `codec.js` + `msgpack.js` (пакеты и `.swr`), `live.js` / `replay.js` (источники кадров), `playback.js`, `stage.js` (рендерер, небо, туман, свет, орбита, «следить»), `ui/` (лобби, FPS по клавише F, `editor.js` — редактор M5: CodeMirror 5, файлы, логи ульев, запуск и стоп; вкладки «Блоки | Python», режим файла, «Перейти на Python», «Новый…» (M7b); `markdown.js` — памятка);
  - `js/modules/bees/` — мир (рельеф с цветом по высоте, деревья, камни, ульи с маяками цвета команды, цветы с яркостью по нектару), агенты (InstancedMesh по типам пчёл), погода (дождь, небо), HUD (ульи, погода, лента событий, панель пчелы), `editor.js` (подсказки по API из `api_hints.js` — генерирует `tools/gen_api_hints.py`; панель «Матч»: профиль, скрипты ульев, seed, длительность, пауки / погода, скорость); блоки (M7b): `blocks_api.js` (генерирует `tools/gen_blocks_api.py`), `blocks_ru.js` (подписи вручную), `blocks_gen.js` (Python из JSON рабочей области: `# block:<id>`, неподключённые, дубликаты, проверки, процедуры, рекурсия), `blocks_editor.js` (Blockly: определения блоков, панель, ошибки на блоках).
  - Источник кадров — WS (`LiveSource`) или файл (`ReplaySource`: таймлайн, перемотка, скорость); рендер один. Интерполяция по `uid` между соседними кадрами, ориентация по скорости.
- Отладочный вьюер: `swarmlab run ... --mj-viewer` — `mujoco.viewer.launch_passive`.

### 7.1 Публичный режим — портал (M9a–M9c, DECISIONS №90–97)

Согласованный объём портала описан в DECISIONS №90–97. Реализация M9a и начатая M9b ещё требуют полной приёмки по ROADMAP; наличие кода и конфигов не подтверждает изоляцию или производительность. Админка и развёртывание M9c остаются планом.

- `swarmlab serve --public [--public-config мой.yaml] [--data папка]` — те же приложение, REST и WS, плюс аккаунты и разделение данных по пользователям (M9a), песочница и лимиты (M9b). Без флага сервер работает как выше (локально, без входа, Windows): ни одного нового маршрута, ни cookie, ни CSRF. Целевой запуск портала — Linux в Docker (№95). Для локальной проверки аккаунтов на Windows текущий конфиг требует явно отключить песочницу (`sandbox: {runner_prefix: []}`) и слушать только localhost; команда — в README.
- Код: `server/public.py` (`Portal`, охрана `PortalGuard`, маршруты портала), `server/accounts.py` (настройки, база, пароли, сессии, лимиты частоты), `server/storage.py` (папки пользователей, скрипты поверх общих примеров, реплеи с квотой, архив кода). Настройки — `server/public.yaml` (квоты реплеев, лимиты, длина пароля, cookie, доверенный прокси); `--public-config` накладывается поверх.
- Аккаунты (№91, №97): SQLite одним файлом (`<data>/swarmlab.db`, `sqlite3`, WAL, версия схемы — `PRAGMA user_version`), пароли argon2id, сессия — случайный токен в cookie `swarmlab_session` (HTTP-only, `SameSite=Lax`, `Secure` — когда запрос пришёл по HTTPS); в базе — sha256 токена. Почта — логин, в нижнем регистре. Роли `user` и `admin` (админка — M9c).

  | Таблица | Поля |
  |---|---|
  | `users` | `id` (AUTOINCREMENT — id удалённого не достаётся новому), `email` UNIQUE, `password_hash`, `role`, `created`, `last_login` |
  | `sessions` | `token_hash`, `user_id` → users, `csrf`, `created`, `expires` (`session_days`) |
  | `replays` | `user_id` → users, `name` (= id матча), `created`, `size`, `pinned`, `finished` (0 — пишется) |

- Охрана `PortalGuard` (ASGI, и HTTP, и WS): без входа открыты статика `web/` и `POST /api/auth/register|login` (только с телом JSON); любой другой `/api/*` — 401, WS — отказ рукопожатия HTTP 401. Изменяющие запросы (не GET/HEAD/OPTIONS) — только с заголовком `X-CSRF-Token` сессии (иначе 403); `js/core/api.js` подставляет его сам (токен — из `GET /api/me` и ответа входа). WS с чужим `Origin` — 403. Тело отклонённого запроса дочитывается: иначе на Windows клиент видит обрыв, а не 401.
- IP клиента и HTTPS: прямое подключение — адрес сокета и схема; от адреса из `proxy.trusted` (Caddy) — первый недоверенный справа в `X-Forwarded-For` и `X-Forwarded-Proto`. `serve --public` запускает uvicorn с `proxy_headers=False`, чтобы заголовкам не верил он сам.
- Ограничения частоты (в памяти процесса, после перезапуска — с нуля): не больше `register_per_ip` регистраций за `register_window_s` с одного IP (дальше 429); `login_failures` неверных паролей к одной почте за `login_window_s` — вход к ней закрыт на `login_lockout_s` (429 «попробуйте через N мин»). Для несуществующей почты тоже считается хеш: время ответа не выдаёт, есть ли аккаунт.
- Маршруты портала:
  - `POST /api/auth/register` `{email, password}` (пароль от `password_min` символов; занятая почта — 409), `POST /api/auth/login` (неверно — 401 «Неверная почта или пароль»), `POST /api/auth/logout`;
  - `GET /api/me` → `{email, role, csrf, usage}` (`usage` — реплеи и квота); клиент по нему узнаёт режим: 200 — вошли, 401 — экран входа, 404 — локальный режим;
  - `POST /api/me/password` `{current, new}` — неверный текущий — 403, остальные сессии закрываются; `DELETE /api/me` `{password}` — останавливает матчи пользователя и ждёт выхода процессов, удаляет строки в базе и папку; `GET /api/me/export` — zip: `scripts/<имя>.swarm` (собран из кода и блоков, как «Экспорт проекта» в редакторе) и `projects/<имя>.swarm` (оригиналы);
  - `POST /api/replays/{id}/pin` `{pinned}` (сверх квоты — 409 с текстом), `DELETE /api/replays/{id}`, `DELETE /api/scripts/{name}`, `DELETE /api/projects/{name}`.
  - Прежние маршруты на портале работают с данными вошедшего: `/api/scripts*`, `/api/projects*` — его папки; `GET /api/matches` — его матчи; `GET /api/matches/{id}`, `stop`, WS, `GET /api/replays/{id}` — чужое — 404 (WS — 4404), как несуществующее; `GET /api/replays` — его реплеи с `pinned`. В объёме M9a серии были выключены (403). В рабочей реализации M9b `/api/series*` включены с разделением по владельцам и лимитами из `public.yaml`; лимиты живых матчей тоже берутся из него. `--max-matches` относится к локальному режиму.
- Данные пользователя (№92), папка `--data` (по умолчанию `<root>/data`, в `.gitignore`); пути — только из числового id:

  ```
  data/swarmlab.db
  data/users/<id>/scripts/     свои скрипты редактора (+ .blocks.json)
  data/users/<id>/projects/    загруженные .swarm
  data/users/<id>/replays/     <id матча>.swr
  data/users/<id>/logs/<матч>/ логи кода игрока (удаляются вместе с аккаунтом)
  ```

  Общие примеры — только справочные файлы папки редактора модуля (`template.py`, `example_*.py`): видны всем, только для чтения (запись и удаление — 403); остальные файлы той папки (`my_*.py` локального режима) на портале не видны. Матч пользователя берёт код ульев только из его папок и общих примеров: сервер передаёт воркеру `script_dirs`, `Simulation` проверяет `TeamSpec.script` каждой команды до запуска раннеров (`core.module.check_team_scripts`); чужой путь в переопределениях конфига — матч `error` «код улья недоступен», чужой код не запускается.
- Реплеи (№92): строка в `replays` появляется при старте матча (`finished = 0`, в списке не видна), при выходе процесса матча — размер и `finished = 1`, затем очистка. Очистка (конец матча и старт сервера): у незакреплённых остаются `keep_last` последних и не старше `unpinned_max_age_days`; закреплённые («Сохранить») не трогаются, их квота — `pinned_max_count` штук и `pinned_max_mb`. На старте сервера недописанные строки сверяются с диском, файлы без строки вносятся в список.
- Клиент: `js/core/ui/account.js` — экран входа и регистрации, профиль (смена пароля, архив проектов, удаление аккаунта, выход), «Мои проекты» (свои скрипты: открыть, скачать `.swarm`, удалить; загруженные проекты: скачать, удалить), «Мои реплеи» (смотреть, сохранить, скачать `.swr`, удалить; квота). На портале у `body` класс `portal`. После живого матча — «📌 Сохранить реплей». 401 на любой запрос — экран входа «Вход истёк».
- Рабочая реализация M9b: `RunnerLaunch` в `core/runner_host.py` добавляет префикс к команде `python -m swarmlab.runner`. `ProcessLink.start()` формирует ограниченное окружение через `runner_env()` при каждом запуске, с префиксом и без него. Префикс nsjail задаёт `public.yaml`; Dockerfile и профили в `docker/` предназначены для требований №93: без сети, файловая система только для чтения, лимиты CPU, памяти и процессов. Набор прав контейнера, фактическая изоляция и нагрузка ещё требуют проверки в Linux; это не подтверждённая схема запуска.
- План M9c (№96): compose-проект в `/opt/swarmlab` на VPS Лео, наружу — через существующий Caddy (`swarmlab.kmashinist.ru`, HTTPS, `wss://`); `tools/deploy.ps1` — обновление и скачивание бэкапа. Инструкция `docs/DEPLOY.md` будет создана в этой вехе.

## 8. Мост к реальным роботам (позже)

Роботы собственной разработки. Код агента выполняется на компьютере (вариант «а»), роботы получают команды по радио/сети.

- `RobotLink` реализует тот же `AgentLink`: собирает `AgentSensors` из телеметрии роботов и системы позиционирования, отправляет высокоуровневые команды на автопилот робота.
- Поэтому в API уже сейчас: высокоуровневые команды отделены от физики; сенсоры — только то, что реалистично получить на роботе; есть шум сенсоров.
- Транспорт и формат телеметрии фиксируются, когда будет железо.

## 9. Подключение будущих модулей

Новый модуль = пакет `swarmlab/<name>/`, реализующий `Module` и свой `PhysicsBackend`, свой `api.py` для игроков и `configs/<name>/`. Ядро, раннер, реплеи, сервер, бенчмарк используются как есть. Детали модулей «Карьер» и «Город» — после отдельного обсуждения.
