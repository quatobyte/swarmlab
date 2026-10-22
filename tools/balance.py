"""Балансный прогон: один матч на нескольких seed'ах headless, сводная таблица.

По каждому seed — мёд в конце, гибели пчёл по причинам, судьба шершней; в конце —
победы по скриптам, средний мёд по времени (кривая: выходит ли на плато) и средние
гибели. Матчи идут параллельно в отдельных процессах (`--jobs`), у каждого свои
раннеры кода игрока. Детерминизм не нарушается: seed матча задаёт всё.

Запуск (PowerShell, из корня репозитория):

    .venv\\Scripts\\python tools\\balance.py                       # demo.yaml, seed 1–10
    .venv\\Scripts\\python tools\\balance.py --seeds 3 --duration 120
    .venv\\Scripts\\python tools\\balance.py --scripts example_basic.py example_basic.py `
        example_basic.py --set economy.start_bees.guard=0           # без охраны
    .venv\\Scripts\\python tools\\balance.py --set enemies.hornets.enabled=false
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAUSES = ("energy", "hornet", "spider")
HORNET_FATES = ("hornet_spawn", "hornet_death", "hornet_flee", "hornet_left")


@dataclass
class Result:
    """Итог одного матча."""

    seed: int
    scripts: list[str]
    winner: int | None
    honey: list[float]
    delivered: list[float]
    stolen: list[float]
    alive: list[int]
    deaths: list[Counter[str]]
    hornets: Counter[str]
    heat_ball: int
    curve: list[tuple[float, list[float]]] = field(default_factory=list)
    wall_s: float = 0.0


def run_one(match: str, seed: int, overrides: list[str], curve_s: float) -> Result:
    """Сыграть матч целиком (в отдельном процессе-воркере)."""
    from swarmlab.core.config import load_match
    from swarmlab.core.sim import Simulation

    cfg = load_match(ROOT / match, cli_overrides=[*overrides, f"seed={seed}"])
    deaths: dict[int, Counter[str]] = {}
    hornets: Counter[str] = Counter()
    heat_ball = 0

    def on_frame(frame) -> None:
        nonlocal heat_ball
        for e in frame.events:
            kind = e.get("type")
            if kind == "death":
                deaths.setdefault(int(e["hive"]), Counter())[e["cause"]] += 1
            elif kind in HORNET_FATES:
                hornets[kind] += 1
            elif kind == "heat_ball":
                heat_ball += 1

    t0 = time.perf_counter()
    curve: list[tuple[float, list[float]]] = []
    with Simulation(cfg, on_frame=on_frame, log_dir=ROOT / "logs" / "balance" / f"s{seed}") as sim:
        teams = [t.team for t in sim.teams]
        scripts = [t.script.name if t.script else "—" for t in sim.teams]
        every = sim.clock.steps_for(curve_s)
        while not sim.finished:
            sim.run(max_steps=every)
            board = sim.module.score()
            curve.append((sim.time, [board.teams[t]["honey"] for t in teams]))
        board = sim.module.score()
    rows = [board.teams[t] for t in teams]
    return Result(
        seed=seed,
        scripts=scripts,
        winner=teams.index(board.winner) if board.winner in teams else None,
        honey=[r["honey"] for r in rows],
        delivered=[r["delivered"] for r in rows],
        stolen=[r["stolen"] for r in rows],
        alive=[int(r["alive"]) for r in rows],
        deaths=[deaths.get(int(t), Counter()) for t in teams],
        hornets=hornets,
        heat_ball=heat_ball,
        curve=curve,
        wall_s=time.perf_counter() - t0,
    )


def _table(head: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(head)]
    print("  ".join(h.rjust(w) for h, w in zip(head, widths, strict=True)))
    for r in rows:
        print("  ".join(c.rjust(w) for c, w in zip(r, widths, strict=True)))


def report(results: list[Result]) -> None:
    n_hives = len(results[0].scripts)
    names = [f"{i}:{s.removesuffix('.py').removeprefix('example_')}"
             for i, s in enumerate(results[0].scripts)]
    print("Улья: " + ", ".join(f"{i} — {s}" for i, s in enumerate(results[0].scripts)))
    print()
    head = ["seed", "победил"]
    head += [f"мёд {i}" for i in range(n_hives)]
    head += [f"гибели {i} э/ш/п" for i in range(n_hives)]
    head += ["шершни: всего/убит/бежал", "тепл.шар"]
    rows = []
    for r in results:
        row = [str(r.seed), names[r.winner] if r.winner is not None else "—"]
        row += [f"{h:.1f}" for h in r.honey]
        row += ["/".join(str(d[c]) for c in CAUSES) for d in r.deaths]
        row += [f"{r.hornets['hornet_spawn']}/{r.hornets['hornet_death']}/"
                f"{r.hornets['hornet_flee']}", str(r.heat_ball)]
        rows.append(row)
    _table(head, rows)

    print()
    wins = Counter(r.winner for r in results)
    print("Побед: " + ", ".join(f"{names[i]} — {wins[i]}" for i in range(n_hives))
          + f" (из {len(results)})")
    head = ["улей", "мёд ср.", "мин", "макс", "доставлено", "украдено", "живых",
            "гибели энерг.", "шершень", "паук"]
    rows = []
    k = len(results)
    for i in range(n_hives):
        honey = [r.honey[i] for r in results]
        rows.append([
            names[i], f"{sum(honey) / k:.1f}", f"{min(honey):.1f}", f"{max(honey):.1f}",
            f"{sum(r.delivered[i] for r in results) / k:.1f}",
            f"{sum(r.stolen[i] for r in results) / k:.1f}",
            f"{sum(r.alive[i] for r in results) / k:.1f}",
            *(f"{sum(r.deaths[i][c] for r in results) / k:.1f}" for c in CAUSES),
        ])
    _table(head, rows)
    hn = Counter()
    for r in results:
        hn.update(r.hornets)
    print(f"Шершни в среднем за матч: появилось {hn['hornet_spawn'] / k:.1f}, "
          f"убито {hn['hornet_death'] / k:.1f}, бежало {hn['hornet_flee'] / k:.1f}, "
          f"покинуло карту {hn['hornet_left'] / k:.1f}; "
          f"тиков теплового шара {sum(r.heat_ball for r in results) / k:.0f}")

    print()
    print("Мёд по времени (среднее по seed'ам):")
    times = [t for t, _ in results[0].curve]
    head = ["время, с", *names]
    rows = []
    for j, t in enumerate(times):
        vals = [r.curve[j][1] for r in results if j < len(r.curve)]
        rows.append([f"{t:.0f}", *(f"{sum(v[i] for v in vals) / len(vals):.1f}"
                                   for i in range(n_hives))])
    _table(head, rows)
    wall = sum(r.wall_s for r in results) / k
    print(f"\nСреднее время матча: {wall:.0f} с")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Балансный прогон матча на нескольких seed'ах")
    p.add_argument("--match", default="configs/matches/demo.yaml", help="файл матча")
    p.add_argument("--seeds", type=int, default=10, help="сколько seed'ов (по умолчанию 10)")
    p.add_argument("--seed0", type=int, default=1, help="первый seed (по умолчанию 1)")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
                   help="матчей одновременно")
    p.add_argument("--duration", type=float, help="длительность, с (вместо duration_s)")
    p.add_argument("--curve", type=float, default=30.0, help="шаг кривой мёда, с")
    p.add_argument("--scripts", nargs="+", metavar="ФАЙЛ",
                   help="скрипты ульев из examples/bees/ (вместо hives матча)")
    p.add_argument("--set", dest="overrides", action="append", default=[],
                   metavar="ПУТЬ=ЗНАЧЕНИЕ", help="переопределить параметр, как в swarmlab run")
    args = p.parse_args(argv)

    overrides = list(args.overrides)
    if args.duration is not None:
        overrides.append(f"duration_s={args.duration}")
    if args.scripts:
        hives = ", ".join(f"{{script: examples/bees/{s}}}" for s in args.scripts)
        overrides.append(f"hives=[{hives}]")
    seeds = range(args.seed0, args.seed0 + args.seeds)
    print(f"Матч {args.match}, seed {seeds.start}–{seeds.stop - 1}, параллельно {args.jobs}"
          + (f", оверрайды: {' '.join(overrides)}" if overrides else ""), flush=True)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, args.match, s, overrides, args.curve) for s in seeds]
        results = []
        for f in futures:
            results.append(f.result())
            r = results[-1]
            print(f"  seed {r.seed}: мёд {' / '.join(f'{h:.1f}' for h in r.honey)} "
                  f"({r.wall_s:.0f} с)", flush=True)
    print()
    report(results)
    print(f"Всего: {time.perf_counter() - t0:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
