"""Командная строка `swarmlab`: run | bench | replay | serve."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from swarmlab.core.clock import RealtimePacer
from swarmlab.core.config import ConfigError, MatchConfig, load_match
from swarmlab.core.module import DebugViewable, Describable, Replayable, ScoreBoard
from swarmlab.core.replay import (
    ReplayError,
    ReplayWriter,
    default_replay_path,
    event_key,
    make_header,
    read_replay,
)
from swarmlab.core.sim import Simulation

#: Частота перерисовки отладочного вьюера, Гц.
_VIEWER_FPS = 60.0
#: Эти события печатаются во время показа реплея (рождения, доставки — слишком часты).
_LOUD_EVENTS = ("weather", "hornet_spawn", "heat_ball", "hornet_death", "hornet_left",
                "rob", "eliminated")


def main(argv: Sequence[str] | None = None) -> int:
    # Windows-консоль по умолчанию не в UTF-8: русский текст не должен ронять вывод.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ConfigError as e:
        print(f"Ошибка конфига: {e}", file=sys.stderr)
        return 2
    except ReplayError as e:
        print(f"Ошибка реплея: {e}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swarmlab", description="Симулятор роевых систем")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="запустить матч")
    run.add_argument("match", type=Path, help="файл матча, например configs/matches/demo.yaml")
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
        help="переопределить параметр, например --set enemies.hornets.rob=false",
    )
    run.add_argument("--configs", type=Path, help="папка configs/ (по умолчанию — рядом с матчем)")
    run.add_argument(
        "--report",
        type=float,
        default=30.0,
        metavar="СЕКУНДЫ",
        help="headless: печатать счёт каждые столько секунд симуляции (0 — только в конце)",
    )
    run.add_argument(
        "--log-dir",
        type=Path,
        help="папка логов кода игрока (по умолчанию logs/<имя матча>/)",
    )
    rep = run.add_mutually_exclusive_group()
    rep.add_argument(
        "--replay", type=Path, metavar="ФАЙЛ",
        help="куда записать реплей (по умолчанию replays/<матч>-s<seed>.swr)",
    )
    rep.add_argument("--no-replay", action="store_true", help="не записывать реплей")
    run.set_defaults(handler=_cmd_run)

    replay = sub.add_parser("replay", help="показать реплей: счёт, события, проверка хеша")
    replay.add_argument("file", type=Path, help="файл реплея .swr")
    replay.add_argument(
        "--mj-viewer", action="store_true", help="воспроизвести в отладочном окне MuJoCo"
    )
    replay.add_argument("--speed", type=float, default=1.0, help="скорость воспроизведения")
    replay.add_argument("--loop", action="store_true", help="по кругу, пока открыто окно")
    replay.set_defaults(handler=_cmd_replay)

    bench = sub.add_parser("bench", help="бенчмарк профилей и рекомендация")
    bench.add_argument(
        "--profiles", nargs="+", metavar="ПРОФИЛЬ", help="только эти профили (по умолчанию все)"
    )
    bench.add_argument("--seconds", type=float, default=10.0, help="длина замера, с")
    bench.add_argument("--configs", type=Path, help="папка configs/ (по умолчанию ./configs)")
    bench.add_argument(
        "--show", action="store_true", help="показать сохранённый результат, не запуская бенч"
    )
    bench.set_defaults(handler=_cmd_bench)

    serve = sub.add_parser("serve", help="веб-сервер и 3D-вьюер в браузере")
    serve.add_argument("--host", default="127.0.0.1", help="адрес (по умолчанию 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="порт (по умолчанию 8000)")
    serve.add_argument("--open", action="store_true", help="открыть вьюер в браузере")
    serve.add_argument("--root", type=Path, help="корень проекта: configs/, replays/, logs/, web/")
    serve.add_argument("--max-matches", type=int, default=1,
                       help="сколько живых матчей одновременно (новый вытесняет старый)")
    serve.set_defaults(handler=_cmd_serve)
    return parser


# ====================================================================== run


def _cmd_run(args: argparse.Namespace) -> int:
    overrides = list(args.overrides)
    if args.duration is not None:
        overrides.append(f"duration_s={args.duration}")
    if args.seed is not None:
        overrides.append(f"seed={args.seed}")
    cfg = load_match(args.match, configs_dir=args.configs, cli_overrides=overrides)

    log_dir = args.log_dir or Path("logs") / args.match.stem
    t0 = time.perf_counter()
    sim = Simulation(cfg, log_dir=log_dir)
    writer: ReplayWriter | None = None
    try:
        build_s = time.perf_counter() - t0
        print(
            f"Матч {cfg.source}: модуль {cfg.module}, профиль {cfg.profile}, seed {cfg.seed}, "
            f"{cfg.duration_s:g} с; сборка мира и запуск раннеров {build_s:.2f} с"
        )
        if isinstance(sim.module, Describable):
            for line in sim.module.describe():
                print(f"  {line}")
        if sim.runners is not None:
            for team, stats in sim.runners.stats.items():
                spec = sim.runners.links[team].spec
                state = "ОШИБКА ЗАГРУЗКИ" if stats.load_error else "готов"
                log = log_dir / f"{spec.name}.log"
                print(f"  {spec.name}: {spec.script} — {state}; лог: {log}")
                if stats.load_error:
                    print(stats.load_error, file=sys.stderr)
        if not args.no_replay and isinstance(sim.module, Replayable):
            path = args.replay or default_replay_path(args.match, cfg.seed)
            writer = ReplayWriter(path, make_header(cfg, sim.teams, sim.module.scene()))
            sim.on_frame = writer

        if args.mj_viewer:
            return _run_viewer(sim, args.speed)
        return _run_headless(sim, args.report, writer)
    finally:
        if writer is not None:
            writer.close(sim.module.score())
            size = writer.path.stat().st_size
            print(
                f"Реплей: {writer.path} — {size / 1e6:.2f} МБ ({writer.raw_bytes / 1e6:.1f} МБ "
                f"до сжатия), кадров {writer.frames}, хеш {writer.hash[:16]}…"
            )
        sim.close()


def _run_headless(sim: Simulation, report_s: float, writer: ReplayWriter | None) -> int:
    t0 = time.perf_counter()
    table = _ScoreTable()
    table.add(sim.time, sim.module.score())
    steps = 0
    if report_s > 0:
        every = sim.clock.steps_for(report_s)
        while not sim.finished:
            steps += sim.run(max_steps=every).steps
            table.add(sim.time, sim.module.score())
    else:
        steps = sim.run().steps
        table.add(sim.time, sim.module.score())
    wall = time.perf_counter() - t0
    sim_time = steps * sim.clock.dt
    rtf = sim_time / wall if wall > 0 else float("inf")
    steps_per_s = f"{steps / wall:_.0f}".replace("_", " ")
    table.print()
    final = table.rows[-1][1]
    if sim.time < sim.cfg.duration_s - 1e-9:
        print(f"Матч закончился досрочно на {sim.time:.1f} с (по правилам модуля).")
    _print_final(final, sim)
    if writer is not None:
        _print_events(writer.events)
    if sim.runners is not None:
        _print_runner_stats(sim)
    print(
        f"Готово: {sim_time:.1f} с симуляции за {wall:.2f} с, "
        f"{steps_per_s} шагов/с, RTF = {rtf:.1f}"
    )
    return 0


class _ScoreTable:
    """Счёт по командам во времени: строка на каждый замер."""

    def __init__(self) -> None:
        self.rows: list[tuple[float, ScoreBoard]] = []

    def add(self, t: float, board: ScoreBoard) -> None:
        self.rows.append((t, board))

    def print(self) -> None:
        if not self.rows or not self.rows[0][1].teams:
            return
        _print_table(
            ["время, с", "команда"],
            [(f"{t:.0f}", str(team), row) for t, board in self.rows
             for team, row in board.teams.items()],
        )


def _print_table(head: list[str], rows: list[tuple[str, str, dict[str, Any]]]) -> None:
    keys = list(rows[0][2]) if rows else []
    header = [*head, *keys]
    lines = [[a, b, *(_fmt(row.get(k, 0.0)) for k in keys)] for a, b, row in rows]
    widths = [max(len(h), *(len(r[i]) for r in lines)) for i, h in enumerate(header)]
    print("  ".join(h.rjust(w) for h, w in zip(header, widths, strict=True)))
    for r in lines:
        print("  ".join(c.rjust(w) for c, w in zip(r, widths, strict=True)))


def _fmt(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return str(v)
    return f"{v:.0f}" if abs(v - round(v)) < 1e-6 else f"{v:.2f}"


def _team_name(sim: Simulation | None, team: Any) -> str:
    if sim is not None:
        for t in sim.teams:
            if t.team == team:
                return f"{t.name} ({t.script.name if t.script else '—'})"
    return str(team)


def _print_final(board: ScoreBoard, sim: Simulation | None = None) -> None:
    if board.winner is None:
        return
    print(f"Победитель: команда {_team_name(sim, board.winner)}")


def _print_events(counts: Counter[str] | dict[str, int]) -> None:
    if not counts:
        return
    print("События матча:")
    for key, n in sorted(counts.items()):
        print(f"  {key}: {n}")


def _print_runner_stats(sim: Simulation) -> None:
    assert sim.runners is not None
    print("Раннеры:")
    for team, s in sim.runners.stats.items():
        name = sim.runners.links[team].spec.name
        flag = " ОТКЛЮЧЁН" if s.disabled else ""
        print(
            f"  {name}: тиков {s.ticks}, ответов {s.replies}, пропущено {s.missed}, "
            f"сверх бюджета {s.over_budget}, перезапусков {s.restarts}, "
            f"ошибок в step() {s.agent_errors}, время кода {s.cpu_ms_mean:.2f} мс "
            f"в среднем / {s.cpu_ms_max:.1f} мс максимум{flag}"
        )


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
                if sim.finished:
                    break
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


# ====================================================================== replay


def _cmd_replay(args: argparse.Namespace) -> int:
    rp = read_replay(args.file)
    h = rp.header
    size = args.file.stat().st_size
    duration = rp.frames[-1].time if rp.frames else 0.0
    print(
        f"Реплей {args.file}: модуль {h['module']}, профиль {h['profile']}, seed {h['seed']}, "
        f"{duration:.1f} с из {h['duration_s']:g}, кадров {len(rp.frames)}, {size / 1e6:.2f} МБ"
    )
    versions = ", ".join(f"{k} {v}" for k, v in h["versions"].items() if v)
    engine = h.get("scene", {}).get("engine")
    print(f"  версии: {versions}" + (f", {engine}" if engine else "") + f"; {h['platform']}")
    for t in h["teams"]:
        sha = (t["sha256"] or "")[:12]
        print(f"  {t['name']}: {t['script']} (sha256 {sha}…)")
    if not rp.complete:
        print("  ВНИМАНИЕ: реплей оборван (нет итога) — матч не дописался.")
    elif rp.hash_ok:
        print(f"  хеш: {rp.hash} — совпадает")
    else:
        print(f"  ХЕШ НЕ СОВПАДАЕТ: в файле {rp.footer.get('hash')}, по кадрам {rp.hash}")
    if rp.footer and rp.footer.get("score"):
        score = rp.footer["score"]
        rows = [("итог", team, row) for team, row in score["teams"].items()]
        if rows:
            _print_table(["", "команда"], rows)
        if score.get("winner") is not None:
            print(f"Победитель: команда {score['winner']}")
    _print_events(rp.event_counts())

    if args.mj_viewer:
        return _play_in_viewer(rp, args.speed, args.loop)
    return 0 if (rp.hash_ok or not rp.complete) else 1


def _play_in_viewer(rp: Any, speed: float, loop: bool) -> int:
    from swarmlab.core.module import load_module
    from swarmlab.core.rng import RngRegistry

    if not rp.frames:
        print("В реплее нет кадров.", file=sys.stderr)
        return 1
    cfg = MatchConfig.model_validate(rp.header["config"])
    module = load_module(cfg.module)
    module.build(cfg, RngRegistry(cfg.seed))  # мир по seed; раннеры не запускаются
    if not (isinstance(module, Replayable) and isinstance(module, DebugViewable)):
        print(f"Модуль {cfg.module} не умеет показывать реплей во вьюере", file=sys.stderr)
        return 1
    digest = rp.header.get("scene", {}).get("world_digest")
    if digest and module.scene().get("world_digest") != digest:
        print("ВНИМАНИЕ: мир, собранный по seed, отличается от мира реплея "
              "(другая версия кода?) — показ может не совпадать.")

    frames = rp.frames
    t_first, t_last = frames[0].time, frames[-1].time
    viewer = module.open_debug_viewer()
    print(f"Воспроизведение {t_last - t_first:.1f} с, скорость ×{speed:g}. "
          "Закройте окно, чтобы выйти.")
    i = 0
    t = t_first
    last = time.perf_counter()
    try:
        while viewer.is_running():
            now = time.perf_counter()
            t += (now - last) * speed
            last = now
            if t >= t_last:
                if loop:
                    t, i = t_first, 0
                else:
                    t = t_last
            while i + 1 < len(frames) and frames[i + 1].time <= t:
                i += 1
                for e in frames[i].events:
                    if e.get("type") in _LOUD_EVENTS:
                        print(f"  [{e.get('time', 0.0):6.1f} с] {_event_text(e)}")
            nxt = frames[i + 1] if i + 1 < len(frames) else None
            alpha = 0.0
            if nxt is not None and nxt.time > frames[i].time:
                alpha = min(max((t - frames[i].time) / (nxt.time - frames[i].time), 0.0), 1.0)
            module.apply_frame(frames[i], nxt, alpha)
            viewer.sync()
            pause = 1.0 / _VIEWER_FPS - (time.perf_counter() - now)
            if pause > 0:
                time.sleep(pause)
    finally:
        viewer.close()
    return 0


def _event_text(e: dict[str, Any]) -> str:
    rest = ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("type", "time"))
    return f"{event_key(e)}: {rest}"


# ====================================================================== bench


def _cmd_bench(args: argparse.Namespace) -> int:
    from swarmlab.core import bench

    if args.show:
        report = bench.load_cache()
        if report is None:
            print(f"Сохранённого результата нет ({bench.cache_path()}). "
                  "Запустите: swarmlab bench", file=sys.stderr)
            return 1
        print(f"Сохранённый результат от {report.created} ({bench.cache_path()}):")
        _print_bench(report)
        return 0

    configs = args.configs or _default_configs()
    matches = bench.bench_matches(configs, args.profiles)
    if not matches:
        print(f"Нет матчей бенчмарка в {configs / 'bench'}", file=sys.stderr)
        return 1
    print(
        f"Бенчмарк: {len(matches)} профил(я/ей), прогрев {bench.DEFAULT_WARMUP_S:g} с, "
        f"замер до {args.seconds:g} с симуляции или {args.seconds:g} с реального времени."
    )

    def progress(r: bench.BenchResult) -> None:
        print(f"  {r.profile}: RTF {r.rtf:.2f} ({r.sim_s:.1f} с симуляции за {r.wall_s:.1f} с)")

    report = bench.run_bench(configs, args.profiles, seconds=args.seconds, on_result=progress)
    _print_bench(report)
    path = bench.save_cache(report)
    print(f"Результат сохранён: {path}")
    return 0


def _print_bench(report: Any) -> None:
    from swarmlab.core.bench import THRESHOLD

    head = ["профиль", "команд", "тел", "сборка, с", "симуляция, с", "стена, с", "шагов/с",
            "RTF", f"≥ {THRESHOLD:g}"]
    rows = [
        [r.profile, str(r.teams), str(r.bodies), f"{r.build_s:.1f}", f"{r.sim_s:.1f}",
         f"{r.wall_s:.1f}", f"{r.steps / r.wall_s:.0f}" if r.wall_s > 0 else "—",
         f"{r.rtf:.2f}", "да" if r.ok else "нет"]
        for r in report.results
    ]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(head)]
    print("  ".join(h.rjust(w) for h, w in zip(head, widths, strict=True)))
    for row in rows:
        print("  ".join(c.rjust(w) for c, w in zip(row, widths, strict=True)))
    m = report.machine
    print(f"Машина: {m.get('system')}, {m.get('processor') or m.get('machine')}, "
          f"ядер {m.get('cpus')}, Python {m.get('python')}")
    if report.recommended:
        print(f"Рекомендуемый профиль: {report.recommended} "
              f"(самый большой с RTF ≥ {THRESHOLD:g})")
    else:
        print(f"Ни один профиль не дал RTF ≥ {THRESHOLD:g}: берите small и ждите, что "
              "симуляция пойдёт медленнее реального времени.")


# ====================================================================== serve


def _cmd_serve(args: argparse.Namespace) -> int:
    import logging
    import threading
    import webbrowser

    import uvicorn

    from swarmlab.server.app import create_app, default_config

    cfg = default_config(args.root)
    cfg.max_matches = max(1, args.max_matches)
    if not cfg.web.is_dir():
        print(f"Нет папки вьюера {cfg.web}", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    url = f"http://{args.host}:{args.port}/"
    print(f"SwarmLab: вьюер — {url}  (остановить — Ctrl+C)")
    print(f"  матчи: {cfg.configs / 'matches'}; реплеи: {cfg.replays}; логи: {cfg.logs}")
    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(cfg), host=args.host, port=args.port, log_level="warning",
                ws="websockets-sansio")
    return 0


def _default_configs() -> Path:
    here = Path("configs")
    if (here / "bench").is_dir():
        return here
    return Path(__file__).resolve().parents[2] / "configs"


if __name__ == "__main__":
    raise SystemExit(main())
