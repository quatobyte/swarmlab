# SwarmLab — ядро

Модульный 3D-симулятор роевых систем. Эта ветка (`master`) — **ядро без модулей**: цикл симуляции, конфиги и профили, seed-RNG, реплеи `.swr`, раннер кода игрока, CLI, сервер FastAPI и общий веб-вьюер (`web/js/core/`). Модулей-сценариев здесь нет — у каждого своя ветка (DECISIONS №98):

| Ветка | Что в ней | Рабочее дерево |
|---|---|---|
| `master` | ядро и общие документы | `D:\Files\Projects\swarmlab` |
| `bees` | ядро + модуль пчёлок (Swarm Logic) — играть и разрабатывать пчёл здесь | `D:\Files\Projects\swarmlab-worktrees\bees` |
| `city` | ядро + модуль «Город» (пока только ядро) | `D:\Files\Projects\swarmlab-worktrees\city` |
| `quarry` | ядро + модуль «Карьер» (пока только ядро) | `D:\Files\Projects\swarmlab-worktrees\quarry` |

Ядро правится только в `master` и вливается в ветки модулей (`git merge master`). Модуль правится только в своей ветке. Как это устроено — `docs/ARCHITECTURE.md` §2, правила работы — `CLAUDE.md`.

## Установка (Windows, PowerShell)

У каждого рабочего дерева своё окружение `.venv` — пакет ставится в режиме `-e` из папки этого дерева.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
```

Без модуля `swarmlab run` и редактор не работают: модуль ставится в его ветке, вместе с конфигами (`configs/`), примерами (`examples/`) и вьюером (`web/js/modules/<модуль>/`).

## Документы

- `docs/PRD.md` — что строим и что входит в объём работ.
- `docs/ARCHITECTURE.md` — слои, контракты ядра, протокол раннера, реплеи, сервер.
- `docs/ROADMAP.md` — вехи и критерии приёмки.
- `docs/DECISIONS.md` — журнал решений.
- `docs/WORKFLOW.md` — как ведётся работа с Claude Code.

Документы модуля (спецификация, API игрока, памятка) — в его ветке.
