"""Командная строка `swarmlab`: run | bench | replay | serve."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from swarmlab.core.clock import RealtimePacer
from swarmlab.core.config import ConfigError, load_match
from swarmlab.core.module import DebugViewable
from swarmlab.core.sim import Simulation

#: Частота перерисовки отладочного вьюера, Гц.
_VIEWER_FPS = 60.0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ConfigError as e:
        print(f"Ошибка конфига: {e}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swarmlab", description="Симулятор роевых систем")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="запустить матч")
    run.add_argument("match", type=Path, help="файл матча, например configs/matches/m0.yaml")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument(
        "--headless", action="store_true", help="без графики, максимально быстро (по умолчанию)"
    )
    mode.add_argument(
        "--mj-viewer", action="store_true", help="отладочное окно MuJoCo, реальное время"
    )
    run.add_argument("--duration", type=float, help="длительность, с (перекрывает duration_s)")
    run.add_argument("--seed", type=int, help="seed (перекрывает seed матча)")
    run.add_argument("--speed", type=float, default=1.0, help="ускорение времени во вьюере")
    run.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="ПУТЬ=ЗНАЧЕНИЕ",
        help="переопределить параметр, например --set world.map_size=200",
    )
    run.add_argument("--configs", type=Path, help="папка configs/ (по умолчанию — рядом с матчем)")
    run.set_defaults(handler=_cmd_run)

    for name, milestone, text in (
        ("bench", "M3", "бенчмарк профилей"),
        ("replay", "M3", "воспроизвести реплей"),
        ("serve", "M4", "веб-сервер и вьюер"),
    ):
        p = sub.add_parser(name, help=f"{text} (появится в вехе {milestone})")
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.set_defaults(handler=_stub(name, milestone))
    return parser


def _stub(name: str, milestone: str):
    def handler(_: argparse.Namespace) -> int:
        print(f"swarmlab {name}: ещё не реализовано (веха {milestone}).", file=sys.stderr)
        return 1

    return handler


def _cmd_run(args: argparse.Namespace) -> int:
    overrides = list(args.overrides)
    if args.duration is not None:
        overrides.append(f"duration_s={args.duration}")
    if args.seed is not None:
        overrides.append(f"seed={args.seed}")
    cfg = load_match(args.match, configs_dir=args.configs, cli_overrides=overrides)

    t0 = time.perf_counter()
    sim = Simulation(cfg)
    build_s = time.perf_counter() - t0
    print(
        f"Матч {cfg.source}: модуль {cfg.module}, профиль {cfg.profile}, seed {cfg.seed}, "
        f"{cfg.duration_s:g} с; сборка мира {build_s:.2f} с"
    )

    if args.mj_viewer:
        return _run_viewer(sim, args.speed)
    return _run_headless(sim)


def _run_headless(sim: Simulation) -> int:
    t0 = time.perf_counter()
    stats = sim.run()
    wall = time.perf_counter() - t0
    rtf = stats.sim_time / wall if wall > 0 else float("inf")
    steps_per_s = f"{stats.steps / wall:_.0f}".replace("_", " ")
    print(
        f"Готово: {stats.sim_time:.1f} с симуляции за {wall:.2f} с, "
        f"{steps_per_s} шагов/с, RTF = {rtf:.1f}"
    )
    return 0


def _run_viewer(sim: Simulation, speed: float) -> int:
    if not isinstance(sim.module, DebugViewable):
        print(f"Модуль {sim.module.name} не поддерживает --mj-viewer", file=sys.stderr)
        return 1
    viewer = sim.module.open_debug_viewer()
    pacer = RealtimePacer(sim.clock.dt, speed=speed)
    print("Вьюер открыт. Закройте окно, чтобы завершить. Матч крутится, пока открыто окно.")
    last = time.perf_counter()
    try:
        while viewer.is_running():
            now = time.perf_counter()
            for _ in range(pacer.steps_due(now - last)):
                sim.step()
            last = now
            viewer.sync()
            pause = 1.0 / _VIEWER_FPS - (time.perf_counter() - now)
            if pause > 0:
                time.sleep(pause)
    finally:
        viewer.close()
    print(f"Вьюер закрыт на {sim.time:.1f} с симуляции.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
