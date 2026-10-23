# SwarmLab

Модульный 3D-симулятор роевых систем. Первый модуль — **Swarm Logic**: вы пишете на Python поведение каждой пчелы, а улей из этих маленьких решений собирает коллективное поведение — разведку, сбор нектара, защиту от шершней.

Что внутри:

- 3D-мир по seed: рельеф, деревья, камни, 3 улья, поляны цветов; физика на MuJoCo — пчёлы летают, сталкиваются, их сносит ветер и мочит дождь;
- 4 типа пчёл (разведчик, сборщик, охранник, домашняя), экономика улья (нектар → мёд → новые пчёлы), шершни и пауки, погода;
- код игрока работает в отдельном процессе с бюджетом времени: бесконечный цикл не вешает матч;
- матч можно смотреть в браузере (Three.js), править код пчёл прямо там и перезапускать;
- каждый матч пишется в реплей `.swr`; один seed + те же скрипты → тот же хеш реплея.

## Установка на Windows

Нужны Windows 10/11 x64, 4+ ядра, любая видеокарта (хватает встроенной Intel). Все команды — в **PowerShell**.

1. **Python 3.12** с [python.org](https://www.python.org/downloads/windows/) (подойдёт 3.10–3.12). В установщике отметьте «Add python.exe to PATH». Проверка в новом окне PowerShell:

   ```powershell
   py -3.12 --version
   ```

   Если `py` не найден — `python --version`, и дальше везде вместо `py -3.12` пишите `python`.

2. **Код проекта.** Через Git:

   ```powershell
   git clone <адрес репозитория> swarmlab
   cd swarmlab
   ```

   …или распакуйте архив и откройте PowerShell в папке `swarmlab`.

3. **Виртуальное окружение и зависимости** (MuJoCo, NumPy, FastAPI и т. д. — около 100 МБ):

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

   Если PowerShell пишет, что выполнение сценариев отключено, один раз выполните `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` и повторите `Activate.ps1`. Без активации можно вызывать `.\.venv\Scripts\swarmlab.exe` напрямую.

4. **Проверка:**

   ```powershell
   swarmlab run configs/matches/m2_economy.yaml --headless --duration 30
   ```

   Матч на 30 секунд без графики: в конце таблица счёта и `RTF` — во сколько раз симуляция быстрее реального времени.

   Тесты (несколько минут): `python -m pytest`. Линтер: `ruff check .`

Дальше все команды — из папки проекта с активированным `.venv`.

## Песочница в браузере

```powershell
swarmlab serve --open
```

Откроется `http://127.0.0.1:8000`. Остановить сервер — `Ctrl+C` в окне PowerShell.

- **Матч: рои в ульях** — у каждого улья пример или загруженный проект `.swarm`, «▶ Смотреть матч» или «Серия…» (тот же матч на 10 seed подряд: таблица, `results.csv`, реплеи в `replays/series/`).
- **Матч из файла** → выберите `demo.yaml` → «Запустить»: три улья, шершни и погода включены, 5 минут.
- **Камера:** левая кнопка мыши — вращать, колесо — приблизить, правая — сдвинуть. Клик по пчеле — следить за ней (`Esc` — перестать), `H` — обзор карты, `1`–`3` — к улью, пробел — пауза, `F` — счётчик FPS. Скорость — кнопки ×0.5…×4.
- **Реплеи:** каждый матч сохраняется в `replays/`. В меню «Реплеи» — список, или «Открыть файл .swr…». Есть таймлайн, перемотка и скорость.
- **✎ Редактор кода** — свои пчёлы, см. ниже.

Если игра подтормаживает на слабой видеокарте, в панели матча выберите качество «Экономное».

## Как написать свою пчелу

1. `swarmlab serve --open` → «✎ Редактор кода». Откроется `my_bees.py` — копия шаблона с подробными комментариями.
2. Поправьте поведение и нажмите «▶ Запустить» (`Ctrl+Enter`). Код сохранится, проверится, и матч перезапустится. Ваш улей играет против `example_basic.py` и `example_smart.py`; соперников, seed, врагов и погоду можно поменять в панели «Матч».
3. Ошибки и `print` ваших пчёл — во вкладке логов под редактором; синтаксическая ошибка подсвечивается на нужной строке.

Как устроен скрипт: на каждый тип пчелы — свой класс с методом `step(self, s)`. Его вызывают 10 раз в секунду: `s` — что пчела видит, а методы `self.…` — что она делает. Отдельная функция `hive_step(hive)` решает, кого выводить в улье.

```python
from swarmlab.bees.api import Forager, Hive, Sensors


class MyForager(Forager):
    def step(self, s: Sensors):
        if s.me.in_hive:                      # в улье: выгрузить нектар и снова в путь
            if s.me.cargo > 0:
                self.unload()
            elif s.me.energy_percent > 80:
                self.leave_hive()
            return
        if s.me.is_full or s.me.energy_percent < 30:
            self.go_home()                    # полный груз или мало сил — домой
            return
        flower = s.nearest_flower(min_nectar=0.3)
        if flower:
            self.collect(flower)              # подлететь и собирать нектар
        else:
            self.fly_to(s.home.pos.x + 30, s.home.pos.y)   # искать цветы


def hive_step(hive: Hive):
    if hive.honey > 30 and not hive.queue:
        hive.breed("forager")                 # мёд есть — ещё один сборщик
```

Классы, которые вы не переопределили, ведут себя по умолчанию: разведчики облетают окрестности, охранники патрулируют у улья.

Куда смотреть дальше:

- [`docs/CHEATSHEET.md`](docs/CHEATSHEET.md) — памятка на одну страницу (в редакторе — кнопка «Памятка»);
- [`docs/PLAYER_API.md`](docs/PLAYER_API.md) — полный справочник: сенсоры, команды, сообщения, феромоны;
- `examples/bees/template.py` — шаблон, `example_basic.py` — простой улей, `example_smart.py` — разведка, общая карта полян и пауков, тепловой шар против шершней.

Скрипт можно писать и в любом редакторе: файлы лежат в `examples/bees/`. Запустить свой матч без браузера — скопировать `configs/matches/demo.yaml` в ту же папку под новым именем, указать в `hives` свой скрипт и выполнить `swarmlab run configs/matches/<новое имя>.yaml`.

## Команды CLI

| Команда | Что делает |
|---|---|
| `swarmlab run configs/matches/demo.yaml --headless` | матч без графики: таблица счёта, события, статистика раннеров, RTF; реплей в `replays/demo-s42.swr` |
| `swarmlab run configs/matches/demo.yaml --mj-viewer` | тот же матч в отладочном окне MuJoCo |
| `swarmlab run … --seed 7 --duration 120` | другой seed, другая длительность |
| `swarmlab run … --set enemies.hornets.enabled=false` | поменять любой параметр из `configs/bees/defaults.yaml` (можно несколько `--set`) |
| `swarmlab run … --report 30` | печатать счёт каждые 30 с симуляции |
| `swarmlab replay replays/demo-s42.swr` | итог реплея: счёт, события, проверка хеша |
| `swarmlab replay replays/demo-s42.swr --mj-viewer` | показать реплей в окне MuJoCo (`--speed 4`, `--loop`) |
| `swarmlab bench` | замерить RTF профилей small / medium / large и посоветовать профиль для этой машины |
| `swarmlab serve --open` | сервер и 3D-вьюер в браузере (`--port 8080`, `--host 0.0.0.0` — открыть для других в сети) |
| `python tools/balance.py` | балансный прогон: `demo.yaml` на 10 seed'ах, таблица мёда, гибелей и шершней |

Подсказка по любой команде — `swarmlab <команда> --help`.

Файл матча ищет `configs/` в папке над собой (`configs/matches/x.yaml` → `configs/`). Если файл матча лежит в другом месте, укажите `--configs путь\к\configs`.

## Конфиги

- `configs/bees/defaults.yaml` — все параметры механик с комментариями: скорости, энергия, экономика, шершни, пауки, погода;
- `configs/profiles/` — размер мира: `small` (1 улей, карта 150 м), `medium` (3 улья × 100 пчёл, 300 м — для показа), `large` (3 × 300, 600 м);
- `configs/matches/` — матчи: seed, профиль, длительность, скрипты ульев, переключатели врагов и погоды, `overrides`.

## Документы

- Что строим — [`docs/PRD.md`](docs/PRD.md)
- Как устроено — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Механики пчёлок — [`docs/BEES_SPEC.md`](docs/BEES_SPEC.md)
- План и статус вех — [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Журнал решений — [`docs/DECISIONS.md`](docs/DECISIONS.md)
- Сценарий показа — [`docs/DEMO.md`](docs/DEMO.md)
- Как вести разработку с Claude Code — [`docs/WORKFLOW.md`](docs/WORKFLOW.md)
