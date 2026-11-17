"""Четыре одновременных medium-матча с песочницей M9b (запуск в Linux-образе)."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import queue
import tempfile
import time
import traceback
from pathlib import Path

from swarmlab.core.config import load_match
from swarmlab.core.replay import ReplayWriter, make_header
from swarmlab.core.runner_host import READY, RunnerLaunch
from swarmlab.core.sim import Simulation
from swarmlab.server.accounts import load_settings


def _match(index: int, seconds: float, barrier: mp.synchronize.Barrier,
           results: mp.queues.Queue) -> None:
    try:
        cfg = load_match(Path("configs/bench/medium.yaml"),
                         cli_overrides=[f"duration_s={seconds + 10}"])
        launch = RunnerLaunch(tuple(load_settings().sandbox.runner_prefix))
        with tempfile.TemporaryDirectory(prefix=f"swarmlab-m9b-{index}-") as folder:
            with Simulation(cfg, launch=launch, log_dir=Path(folder) / "logs") as sim:
                assert sim.runners is not None
                assert all(link.state == READY for link in sim.runners.links.values()), [
                    (link.team, link.state, link.load_error)
                    for link in sim.runners.links.values()
                ]
                writer = ReplayWriter(Path(folder) / "match.swr",
                                      make_header(cfg, sim.teams, sim.module.scene()))
                sim.on_frame = writer
                try:
                    sim.run(max_steps=sim.clock.steps_for(3))
                    barrier.wait(timeout=90)
                    start = time.perf_counter()
                    stats = sim.run(max_steps=sim.clock.steps_for(seconds))
                    wall = time.perf_counter() - start
                    results.put((index, stats.sim_time, wall,
                                 sim.physics.n_bodies, len(sim.teams), None))
                finally:
                    writer.close()
    except BaseException:
        barrier.abort()
        results.put((index, 0.0, 0.0, 0, 0, traceback.format_exc()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(4)
    results = ctx.Queue()
    workers = [ctx.Process(target=_match, args=(i, args.seconds, barrier, results))
               for i in range(1, 5)]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 180
    for worker in workers:
        worker.join(max(0, deadline - time.monotonic()))
    for worker in workers:
        if worker.is_alive():
            worker.terminate()
            worker.join(5)
    found = []
    while True:
        try:
            found.append(results.get_nowait())
        except queue.Empty:
            break
    for index, sim_s, wall_s, bodies, teams, error in sorted(found):
        if error:
            print(f"Матч {index}: ошибка\n{error}")
        else:
            print(f"Матч {index}: medium, {teams} команды, {bodies} тел; "
                  f"{sim_s:.1f} с симуляции за {wall_s:.2f} с, RTF = {sim_s / wall_s:.2f}")
    return 0 if len(found) == 4 and all(error is None and sim_s / wall_s >= 1.0
                                       for _, sim_s, wall_s, _, _, error in found) else 1


if __name__ == "__main__":
    raise SystemExit(main())
