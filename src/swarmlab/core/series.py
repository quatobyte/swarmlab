"""Серии матчей: один матч на разных seed подряд, реплеи и таблица (DECISIONS №66).

`swarmlab series` — первичный интерфейс; сервер и меню запускают ту же команду
отдельным процессом. Матч i серии идёт с seed `начальный + i`; каждый матч — свой
процесс `python -m swarmlab.core.series` (как воркер живого матча, без `fork`,
spawn-совместимо): задание — JSON-строка в stdin, итог — JSON-строка в stdout.
Число одновременных процессов (`jobs`) на результат не влияет: строки собираются
по seed, а сам матч зависит только от seed и скриптов.

Папка серии `<out>/<YYYYMMDD-HHMMSS>-<проект>/`:

- `s<seed>.swr` — реплей каждого матча (`make_header` + `ReplayWriter`, как у `swarmlab run`);
- `series.json` — параметры, ульи с sha256 кода, строки матчей, итог; переписывается
  атомарно после каждого матча (по нему сервер показывает прогресс);
- `results.csv` — таблица по улью проекта (UTF-8 с BOM, разделитель `;`, дробная часть
  через запятую — так файл открывается в Excel на русской Windows);
- `logs/s<seed>/` — логи кода игрока и вывод процесса матча.

Остановка — файл `.stop` в папке серии (так её останавливает сервер) или Ctrl+C:
идущие матчи прерываются, их недописанные реплеи удаляются, дописанные остаются.

Ядро не знает модуля: колонки таблицы — `ScoreColumns.score_columns()` модуля (если он
их описывает) и ошибки кода из `RunnerStats`.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

#: Матчей в серии по умолчанию и допустимый диапазон.
DEFAULT_N, N_MIN, N_MAX = 10, 2, 50
FORMAT_VERSION = 1
#: Файл-флаг остановки серии в её папке.
STOP_FILE = ".stop"
SERIES_FILE = "series.json"
CSV_FILE = "results.csv"
#: Как часто опрашивать процессы матчей и флаг остановки, с.
_POLL_S = 0.1
#: Сколько ждать выхода матча после EOF в stdin, прежде чем убить его, с.
_KILL_WAIT_S = 15.0
#: Состояния серии.
RUNNING, FINISHED, STOPPED = "running", "finished", "stopped"
_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


@dataclass(frozen=True)
class Column:
    """Колонка таблицы серии (как `core.module.ScoreColumn`, но сериализуемая в JSON)."""

    key: str
    title: str
    worst: str | None = None


#: Ошибки кода игрока — из `RunnerStats`, у любого модуля.
RUNNER_COLUMNS = (
    Column("agent_errors", "ошибки кода: исключения"),
    Column("missed", "ошибки кода: пропущено тиков"),
    Column("over_budget", "ошибки кода: сверх бюджета"),
)
_ERROR_KEYS = tuple(c.key for c in RUNNER_COLUMNS)


class SeriesError(ValueError):
    """Неверные параметры серии."""


# ====================================================================== ядра процессора


def physical_cores() -> int:
    """Число физических ядер (без гиперпоточности); не удалось узнать — половина потоков."""
    logical = os.cpu_count() or 1
    try:
        if sys.platform == "win32":
            n = _win_cores()
        elif Path("/proc/cpuinfo").is_file():
            n = _linux_cores()
        else:
            n = 0
    except (OSError, ValueError, AttributeError):
        n = 0
    return n if n > 0 else max(1, logical // 2)


def _win_cores() -> int:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    size = wintypes.DWORD(0)
    k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(size))  # 0 = RelationProcessorCore
    if not size.value:
        return 0
    buf = ctypes.create_string_buffer(size.value)
    if not k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(size)):
        return 0
    count, off = 0, 0
    while off + 8 <= size.value:
        relation, rec = struct.unpack_from("<II", buf.raw, off)
        if rec <= 0:
            break
        count += relation == 0
        off += rec
    return count


def _linux_cores() -> int:
    cores: set[tuple[str, str]] = set()
    phys = core = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("physical id"):
            phys = line.split(":", 1)[1].strip()
        elif line.startswith("core id"):
            core = line.split(":", 1)[1].strip()
        elif not line.strip() and core:
            cores.add((phys, core))
            phys = core = ""
    if core:
        cores.add((phys, core))
    return len(cores)


def default_jobs() -> int:
    """Параллельных матчей по умолчанию: `max(1, физических ядер − 1)`."""
    return max(1, physical_cores() - 1)


# ====================================================================== один матч


def play_match(job: dict[str, Any], on_ready: Callable[[], None] | None = None) -> dict[str, Any]:
    """Матч headless → реплей + счёт + статистика раннеров (в процессе матча серии).

    `job`: `{match, configs?, overrides[], replay, log_dir?}`; seed — среди `overrides`.
    `on_ready` — вызывается, когда мир собран и раннеры запущены.
    """
    from swarmlab.core.config import load_match
    from swarmlab.core.module import Replayable
    from swarmlab.core.replay import ReplayWriter, make_header, score_dict
    from swarmlab.core.sim import Simulation

    cfg = load_match(job["match"], configs_dir=job.get("configs"),
                     cli_overrides=list(job.get("overrides") or []))
    log_dir = Path(job["log_dir"]) if job.get("log_dir") else None
    with Simulation(cfg, log_dir=log_dir) as sim:
        if not isinstance(sim.module, Replayable):
            raise TypeError(f"Модуль {cfg.module} не пишет реплей (нет Replayable)")
        writer = ReplayWriter(job["replay"], make_header(cfg, sim.teams, sim.module.scene()))
        sim.on_frame = writer
        if on_ready is not None:
            on_ready()
        try:
            sim.run()
        finally:
            board = sim.module.score()
            digest = writer.close(board)
        stats = sim.runners.stats if sim.runners is not None else {}
        teams: dict[str, dict[str, Any]] = {}
        for team, row in board.teams.items():
            st = stats.get(team)
            teams[str(team)] = {
                **row,
                "agent_errors": st.agent_errors if st else 0,
                "missed": st.missed if st else 0,
                "over_budget": st.over_budget if st else 0,
                "restarts": st.restarts if st else 0,
                "load_error": bool(st and st.load_error),
            }
        return {"seed": cfg.seed, "state": FINISHED, "hash": digest, "frames": writer.frames,
                "time": round(sim.time, 3), "winner": score_dict(board)["winner"],
                "teams": teams}


def _child_main() -> int:
    """`python -m swarmlab.core.series`: одно задание из stdin, итог — в stdout."""
    out = sys.stdout
    sys.stdout = sys.stderr  # print из ядра и модуля не испортит итог
    line = sys.stdin.readline()
    if not line:
        return 1

    def watch_stdin() -> None:  # родитель закрылся или умер — выйти, сирот не оставлять
        sys.stdin.read()
        os._exit(3)

    # Сторож stdin — только после сборки мира: на Windows поток, ждущий чтения из пайпа,
    # блокирует загрузку DLL (numpy, MuJoCo) в главном потоке.
    def ready() -> None:
        threading.Thread(target=watch_stdin, daemon=True).start()

    job = json.loads(line)
    try:
        result = play_match(job, ready)
    except Exception:
        traceback.print_exc()
        return 2
    out.write(json.dumps(result, ensure_ascii=False) + "\n")
    out.flush()
    return 0


# ====================================================================== серия


@dataclass
class SeriesSpec:
    """Параметры серии. `team` — улей, по которому строится таблица (None — первый)."""

    match: Path
    overrides: list[str] = field(default_factory=list)
    start_seed: int = 0
    n: int = DEFAULT_N
    jobs: int = 1
    out: Path = Path("replays") / "series"
    configs: Path | None = None
    team: int | None = None
    name: str | None = None


@dataclass
class _Running:
    seed: int
    proc: subprocess.Popen[bytes]
    replay: Path
    stderr: Path
    started: float


ProgressCallback = Callable[[dict[str, Any]], None]


class Series:
    """Серия матчей: план, процессы, файлы. `run()` — до конца или до остановки."""

    def __init__(self, spec: SeriesSpec, *, root: Path | None = None) -> None:
        if not N_MIN <= spec.n <= N_MAX:
            raise SeriesError(f"Матчей в серии — от {N_MIN} до {N_MAX}, а не {spec.n}")
        if spec.start_seed < 0:
            raise SeriesError("Начальный seed не может быть отрицательным")
        self.spec = spec
        self.jobs = max(1, int(spec.jobs))
        self.root = Path(root or Path.cwd())
        self._interrupted = False
        self.data = self._prepare()
        self.dir: Path = self._make_dir()
        self.data["id"] = self.dir.name
        self.write()

    # ------------------------------------------------------------ подготовка

    def _prepare(self) -> dict[str, Any]:
        """Конфиг первого матча, ульи (скрипты и sha256), колонки таблицы модуля."""
        from swarmlab.core.config import load_match
        from swarmlab.core.module import ScoreColumns, load_module
        from swarmlab.core.replay import file_sha256
        from swarmlab.core.rng import RngRegistry

        s = self.spec
        cfg = load_match(s.match, configs_dir=s.configs,
                         cli_overrides=[*s.overrides, f"seed={s.start_seed}"])
        module = load_module(cfg.module)
        module.build(cfg, RngRegistry(cfg.seed))  # ульи и скрипты; раннеры не запускаются
        teams = module.agent_teams()
        columns: list[Column] = []
        if isinstance(module, ScoreColumns):
            columns = [Column(c.key, c.title, c.worst) for c in module.score_columns()]
        hives = [{"team": t.team, "name": t.name,
                  "script": str(t.script) if t.script else None,
                  "sha256": file_sha256(t.script) if t.script else None} for t in teams]
        focus = s.team if s.team is not None else (teams[0].team if teams else 0)
        if teams and focus not in {t.team for t in teams}:
            raise SeriesError(f"Нет улья {focus} с кодом игрока: есть "
                              + ", ".join(str(t.team) for t in teams))
        script = next((t.script for t in teams if t.team == focus and t.script), None)
        project = s.name or (Path(script).stem if script else Path(s.match).stem)
        return {
            "format": FORMAT_VERSION,
            "id": "",
            "created": datetime.now().isoformat(timespec="seconds"),
            "state": RUNNING,
            "project": project,
            "match": str(s.match),
            "overrides": list(s.overrides),
            "module": cfg.module,
            "profile": cfg.profile,
            "duration_s": cfg.duration_s,
            "start_seed": s.start_seed,
            "n": s.n,
            "jobs": self.jobs,
            "team": focus,
            "hives": hives,
            "columns": [asdict(c) for c in (*columns, *RUNNER_COLUMNS)],
            "running": [],
            "matches": [],
            "summary": None,
        }

    def _make_dir(self) -> Path:
        safe = "".join(ch if ch in _SAFE else "_" for ch in self.data["project"])
        project = safe[:40] or "series"
        base = f"{datetime.now():%Y%m%d-%H%M%S}-{project}"
        out = Path(self.spec.out)
        path, k = out / base, 1
        while path.exists():
            k += 1
            path = out / f"{base}-{k}"
        path.mkdir(parents=True)
        return path

    # ------------------------------------------------------------ файлы

    def write(self) -> None:
        """`series.json` атомарно (сервер читает его во время серии)."""
        text = json.dumps(self.data, ensure_ascii=False, indent=1)
        _replace_retry(self.dir / SERIES_FILE, text.encode("utf-8"))

    def write_csv(self) -> None:
        _replace_retry(self.dir / CSV_FILE, results_csv(self.data).encode("utf-8-sig"))

    @property
    def stop_requested(self) -> bool:
        return self._interrupted or (self.dir / STOP_FILE).exists()

    def request_stop(self) -> None:
        self._interrupted = True

    # ------------------------------------------------------------ процессы

    def _launch(self, seed: int) -> _Running:
        logs = self.dir / "logs" / f"s{seed}"
        logs.mkdir(parents=True, exist_ok=True)
        replay = self.dir / f"s{seed}.swr"
        job = {"match": str(self.spec.match),
               "configs": str(self.spec.configs) if self.spec.configs else None,
               "overrides": [*self.spec.overrides, f"seed={seed}"],
               "replay": str(replay), "log_dir": str(logs)}
        env = dict(os.environ)
        env.update(PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        stderr_path = logs / "match.log"
        with stderr_path.open("wb") as err:
            proc = subprocess.Popen(
                [sys.executable, "-m", "swarmlab.core.series"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                cwd=str(self.root), env=env, creationflags=flags,
            )
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(job, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
        return _Running(seed, proc, replay, stderr_path, time.monotonic())

    def _collect(self, r: _Running) -> dict[str, Any]:
        assert r.proc.stdout is not None
        raw = r.proc.stdout.read()
        if r.proc.stdin is not None:
            r.proc.stdin.close()
        r.proc.wait()
        try:
            result = json.loads(raw.decode("utf-8").strip().splitlines()[-1])
        except (ValueError, IndexError):
            tail = r.stderr.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
            return {"seed": r.seed, "state": "error", "replay": None, "hash": None, "teams": {},
                    "error": f"Процесс матча завершился с кодом {r.proc.returncode}.\n"
                             + "\n".join(tail)}
        result["replay"] = r.replay.name
        result["wall_s"] = round(time.monotonic() - r.started, 2)
        return result

    @staticmethod
    def _kill(r: _Running) -> None:
        """Прервать матч: EOF в stdin (процесс выходит сам), не помогло — всё дерево процессов.

        `python.exe` из venv на Windows — лаунчер настоящего интерпретатора: `kill()`
        убил бы только его, а матч продолжал бы писать реплей.
        """
        proc = r.proc
        if proc.stdin is not None:
            with contextlib.suppress(OSError):
                proc.stdin.close()
        try:
            proc.wait(_KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, check=False)
            else:
                proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()

    def run(self, on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        """Сыграть серию; вернуть содержимое `series.json`."""
        pending = [self.spec.start_seed + i for i in range(self.spec.n)]
        running: list[_Running] = []
        try:
            while (pending or running) and not self.stop_requested:
                while pending and len(running) < self.jobs:
                    running.append(self._launch(pending.pop(0)))
                    self._update_running(running)
                done = [r for r in running if r.proc.poll() is not None]
                for r in done:
                    running.remove(r)
                    self._add(self._collect(r))
                    self._update_running(running)
                    if on_progress is not None:
                        on_progress(self._last(r.seed))
                if not done:
                    time.sleep(_POLL_S)
        except KeyboardInterrupt:
            self.request_stop()
        except Exception:
            self.data["error"] = traceback.format_exc()
            raise
        finally:
            for r in running:  # остановлено: недописанные реплеи не нужны
                self._kill(r)
                r.replay.unlink(missing_ok=True)
            stopped = bool(pending or running)
            self.data["state"] = ("error" if self.data.get("error")
                                  else STOPPED if stopped else FINISHED)
            self.data["running"] = []
            self.data["finished"] = datetime.now().isoformat(timespec="seconds")
            self.data["summary"] = summarize(self.data)
            self.write()
            self.write_csv()
            (self.dir / STOP_FILE).unlink(missing_ok=True)
        return self.data

    def _last(self, seed: int) -> dict[str, Any]:
        return next(m for m in self.data["matches"] if m["seed"] == seed)

    def _add(self, result: dict[str, Any]) -> None:
        matches = self.data["matches"]
        matches.append(result)
        matches.sort(key=lambda m: m["seed"])
        self.data["summary"] = summarize(self.data)
        self.write()

    def _update_running(self, running: list[_Running]) -> None:
        self.data["running"] = sorted(r.seed for r in running)
        self.write()


def _replace_retry(path: Path, data: bytes, attempts: int = 50) -> None:
    """Записать через временный файл и `os.replace`. На Windows замена падает, пока файл
    открыт другим процессом (сервер читает `series.json`) — тогда повторить чуть позже."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02)


def read_series(path: Path, attempts: int = 20) -> dict[str, Any]:
    """Прочитать `series.json` (повтор, если файл как раз заменяется)."""
    for i in range(attempts):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (PermissionError, ValueError):
            if i == attempts - 1:
                raise
            time.sleep(0.02)
    raise AssertionError("недостижимо")


# ====================================================================== таблица


def focus_row(match: dict[str, Any], team: int) -> dict[str, Any] | None:
    """Строка улья проекта в итоге матча (`None` — матч не сыгран)."""
    return (match.get("teams") or {}).get(str(team))


def has_code_errors(row: dict[str, Any] | None) -> bool:
    return bool(row) and (any(row.get(k, 0) for k in _ERROR_KEYS) or bool(row.get("load_error")))


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    """Итог серии по улью проекта: средние, победы, худший seed, матчи с ошибками кода."""
    team = data["team"]
    played = [(m, focus_row(m, team)) for m in data["matches"] if m.get("state") == FINISHED]
    played = [(m, row) for m, row in played if row is not None]
    columns = data["columns"]
    means: dict[str, float] = {}
    for c in columns:
        vals = [float(row.get(c["key"], 0.0)) for _, row in played]
        if vals:
            means[c["key"]] = sum(vals) / len(vals)
    worst: int | None = None
    order = [c for c in columns if c.get("worst") in ("max", "min")]
    if played:
        def badness(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[float, ...]:
            m, row = item
            key = [float(row.get(c["key"], 0.0)) * (1 if c["worst"] == "max" else -1)
                   for c in order]
            return (*key, -m["seed"])
        worst = max(played, key=badness)[0]["seed"]
    return {
        "played": len(played),
        "errors": sum(1 for m in data["matches"] if m.get("state") != FINISHED),
        "wins": sum(1 for m, _ in played if m.get("winner") == team),
        "with_code_errors": sum(1 for _, row in played if has_code_errors(row)),
        "worst_seed": worst,
        "means": means,
    }


def _num(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        f = float(v)
        text = f"{f:.0f}" if abs(f - round(f)) < 1e-9 else f"{f:.2f}"
        return text.replace(".", ",")
    return "" if v is None else str(v)


def results_csv(data: dict[str, Any]) -> str:
    """`results.csv`: строка на матч по улью проекта + строка средних."""
    team = data["team"]
    columns = data["columns"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["seed", "состояние", *(c["title"] for c in columns), "победа", "реплей"])
    for m in data["matches"]:
        row = focus_row(m, team) or {}
        state = "ок" if m.get("state") == FINISHED else "ошибка матча"
        if m.get("state") == FINISHED and has_code_errors(row):
            state = "ошибки кода"
        w.writerow([m["seed"], state, *(_num(row.get(c["key"])) for c in columns),
                    _num(m.get("winner") == team), m.get("replay") or ""])
    summary = data.get("summary") or summarize(data)
    w.writerow(["среднее", "", *(_num(summary["means"].get(c["key"])) for c in columns),
                _num(summary["wins"]), ""])
    return buf.getvalue()


def list_series(root: Path) -> list[dict[str, Any]]:
    """Прошлые серии из папок `root/*/series.json` (новые первыми)."""
    out = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob(f"*/{SERIES_FILE}"), reverse=True):
        try:
            data = read_series(path)
        except (OSError, ValueError):
            continue
        out.append(data)
    return out


if __name__ == "__main__":
    raise SystemExit(_child_main())
