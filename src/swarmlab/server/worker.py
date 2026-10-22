"""Процесс живого матча: `python -m swarmlab.server.worker` (ARCHITECTURE §7, DECISIONS №43).

Сервер запускает матч в отдельном процессе, чтобы физика не блокировала event loop.
Канал — как у раннера (ARCHITECTURE §3.4): stdin/stdout, кадр = u32 LE длина + msgpack.

Сервер → воркер (`core.protocol`): первым — `start {id, match, configs, overrides,
replay, log_dir, speed}`, дальше управление `pause`, `resume`, `speed {value}`, `stop`.

Воркер → сервер (msgpack с массивами `{"__nd__": …}`, как в реплее):

- `header` — заголовок реплея (`make_header`) + `match_id`, `frame_hz`, `runners`;
- `frame` — запись кадра реплея, байт в байт как в файле `.swr`;
- `status {state, speed, time, duration_s, rtf, score, error}` — при смене состояния
  и раз в секунду;
- `log {team, name, time, lines}` — новые строки лога кода игрока улья (`print`, ошибки
  с трассировкой, предупреждения ядра о бюджете); раз в порцию шагов, в реплей не идут;
- `footer {frames, hash, score, replay}` — матч закончился или остановлен, реплей дописан.

Матч идёт в реальном времени (`RealtimePacer`, скорость меняется на лету); если машина
не успевает — медленнее реального, шаг физики не меняется. `sys.stdout` уводится в
stderr: случайный `print` не ломает канал. EOF на stdin (сервер закрылся или умер) —
матч останавливается, процесс выходит, раннеры игроков выходят следом по своему EOF.
"""

from __future__ import annotations

import os
import queue
import struct
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, BinaryIO

from swarmlab.core.clock import RealtimePacer
from swarmlab.core.config import load_match
from swarmlab.core.module import Replayable
from swarmlab.core.protocol import ProtocolError, read_frame
from swarmlab.core.replay import ReplayWriter, make_header, pack, score_dict
from swarmlab.core.sim import Simulation

_LEN = struct.Struct("<I")
#: Шаги физики идут порциями не дольше этого, чтобы управление отвечало быстро, с.
_CHUNK_S = 0.05
#: Пауза цикла, когда шагать пока нечего, с.
_IDLE_S = 0.004
#: Как часто слать `status`, с.
_STATUS_EVERY_S = 1.0
#: Допустимые скорости живого матча.
SPEED_MIN, SPEED_MAX = 0.25, 8.0
#: После EOF на stdin — столько секунд на нормальную остановку, потом `os._exit`.
_EOF_GRACE_S = 10.0
#: Сколько строк лога одного улья уходит одним пакетом `log` (остальные — счётчиком).
_LOG_LINES_PER_PACKET = 400


class Channel:
    """Запись пакетов в stdout сервера (только из главного потока)."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream

    def send_raw(self, body: bytes) -> None:
        self.stream.write(_LEN.pack(len(body)))
        self.stream.write(body)
        self.stream.flush()

    def send(self, msg: dict[str, Any]) -> None:
        self.send_raw(pack(msg))


def _stdin_reader(stream: Any, inbox: queue.Queue[dict[str, Any] | None]) -> None:
    """Команды сервера → очередь. EOF — сервер закрылся: остановить матч и выйти."""
    try:
        while True:
            msg = read_frame(stream)
            if msg is None:
                break
            inbox.put(msg)
    except (OSError, ValueError, ProtocolError):
        pass
    inbox.put(None)
    time.sleep(_EOF_GRACE_S)
    os._exit(0)  # главный поток мог застрять (например, в запуске раннеров)


def clamp_speed(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    return min(max(v, SPEED_MIN), SPEED_MAX)


class LiveMatch:
    """Матч в реальном времени с паузой и скоростью; пакеты — в `Channel`."""

    def __init__(self, start: dict[str, Any], out: Channel,
                 inbox: queue.Queue[dict[str, Any] | None]) -> None:
        self.start = start
        self.out = out
        self.inbox = inbox
        self.match_id = str(start.get("id", ""))
        self.state = "starting"
        self.speed = clamp_speed(start.get("speed", 1.0))
        self.sim: Simulation | None = None
        self.writer: ReplayWriter | None = None
        self.replay_path: Path | None = None
        self._rtf = 0.0
        self._log_lines: queue.Queue[tuple[int, str]] = queue.Queue()
        self._team_names: dict[int, str] = {}

    # ------------------------------------------------------------ пакеты

    def status(self, error: str | None = None) -> None:
        sim = self.sim
        msg: dict[str, Any] = {
            "t": "status",
            "match_id": self.match_id,
            "state": self.state,
            "speed": self.speed,
            "time": sim.time if sim else 0.0,
            "duration_s": sim.cfg.duration_s if sim else None,
            "rtf": self._rtf,
            "score": score_dict(sim.module.score()) if sim else None,
        }
        if error:
            msg["error"] = error
        self.out.send(msg)

    def flush_logs(self) -> None:
        """Накопленные строки логов ульев → пакеты `log` (по одному на улей)."""
        by_team: dict[int, list[str]] = {}
        try:
            while True:
                team, line = self._log_lines.get_nowait()
                by_team.setdefault(team, []).append(line)
        except queue.Empty:
            pass
        now = self.sim.time if self.sim else 0.0
        for team, lines in by_team.items():
            if len(lines) > _LOG_LINES_PER_PACKET:
                skipped = len(lines) - _LOG_LINES_PER_PACKET
                lines = lines[:_LOG_LINES_PER_PACKET]
                lines.append(f"[сервер] … и ещё {skipped} строк (полный лог — в папке logs/)")
            self.out.send({"t": "log", "match_id": self.match_id, "team": team,
                           "name": self._team_names.get(team, f"hive{team}"),
                           "time": now, "lines": lines})

    def _on_frame(self, frame: Any) -> None:
        assert self.writer is not None
        self.out.send_raw(self.writer.write(frame))

    # ------------------------------------------------------------ жизненный цикл

    def build(self) -> None:
        s = self.start
        cfg = load_match(s["match"], configs_dir=s.get("configs"),
                         cli_overrides=list(s.get("overrides") or []))
        self.status()
        log_dir = Path(s["log_dir"]) if s.get("log_dir") else None
        self.sim = sim = Simulation(cfg, log_dir=log_dir)
        if not isinstance(sim.module, Replayable):
            raise TypeError(f"Модуль {cfg.module} не отдаёт сцену (Replayable) — показать нечего")
        header = make_header(cfg, sim.teams, sim.module.scene())
        if s.get("replay"):
            self.replay_path = Path(s["replay"])
            self.writer = ReplayWriter(self.replay_path, header)
        else:  # без файла: тот же кодер кадров, но в никуда
            self.writer = ReplayWriter(Path(os.devnull), header)
        runners = []
        if sim.runners is not None:
            for team, st in sim.runners.stats.items():
                spec = sim.runners.links[team].spec
                runners.append({"team": team, "name": spec.name, "ok": not st.load_error,
                                "error": st.load_error or None,
                                "script": spec.script.name if spec.script else None})
                self._team_names[team] = spec.name
                sim.runners.logs[team].subscribe(
                    lambda line, team=team: self._log_lines.put((team, line)))
        self.out.send({**header, "match_id": self.match_id,
                       "frame_hz": cfg.timing.frame_hz, "runners": runners})
        self.flush_logs()
        sim.on_frame = self._on_frame
        # Начальный кадр: вьюер сразу видит пчёл, не дожидаясь первого шага кадров.
        self._on_frame(sim.module.snapshot())

    def _control(self, msg: dict[str, Any] | None) -> bool:
        """Применить команду сервера; False — пора останавливаться."""
        if msg is None:
            return False
        t = msg.get("t")
        if t == "stop":
            return False
        if t == "pause" and self.state == "running":
            self.state = "paused"
            self.status()
        elif t == "resume" and self.state == "paused":
            self.state = "running"
            self.status()
        elif t == "speed":
            self.speed = clamp_speed(msg.get("value"))
            self.status()
        return True

    def run(self) -> str:
        """Крутить матч до конца или до `stop`; вернуть итоговое состояние."""
        sim = self.sim
        assert sim is not None
        pacer = RealtimePacer(sim.clock.dt, speed=self.speed)
        self.state = "running"
        self.status()
        last = time.perf_counter()
        status_at = last + _STATUS_EVERY_S
        window_wall, window_sim = last, sim.time
        while not sim.finished:
            try:
                while True:
                    if not self._control(self.inbox.get_nowait()):
                        return "stopped"
            except queue.Empty:
                pass
            now = time.perf_counter()
            elapsed, last = now - last, now
            if self.state == "paused":
                self.flush_logs()
                time.sleep(0.02)
                window_wall, window_sim = time.perf_counter(), sim.time
                continue
            pacer.speed = self.speed
            pacer.max_lag_s = 0.25 * max(1.0, self.speed)
            n = pacer.steps_due(elapsed)
            deadline = now + _CHUNK_S
            done = 0
            while done < n and not sim.finished:
                sim.step()
                done += 1
                if time.perf_counter() > deadline:
                    break  # порция кончилась: проверить управление и вернуться
            # Несделанные шаги — обратно в бюджет пейсера: они не теряются, пока отставание
            # меньше `max_lag_s`; дальше симуляция честно идёт медленнее реального времени.
            pacer.refund(n - done)
            self.flush_logs()
            now = time.perf_counter()
            if now >= status_at:
                if now > window_wall:
                    self._rtf = (sim.time - window_sim) / (now - window_wall)
                window_wall, window_sim = now, sim.time
                status_at = now + _STATUS_EVERY_S
                self.status()
            if n == 0:
                time.sleep(_IDLE_S)
        return "finished"

    def close(self, state: str, error: str | None = None) -> None:
        self.state = state
        self.flush_logs()
        footer: dict[str, Any] | None = None
        if self.writer is not None and self.sim is not None:
            score = self.sim.module.score()
            digest = self.writer.close(score)
            footer = {"t": "footer", "match_id": self.match_id, "frames": self.writer.frames,
                      "hash": digest, "score": score_dict(score),
                      "replay": self.replay_path.name if self.replay_path else None}
        self.status(error)
        if footer is not None:
            self.out.send(footer)
        if self.sim is not None:  # раннеры останавливаются после итога: зрителю не ждать
            self.sim.close()


def main() -> int:
    channel_in = sys.stdin.buffer
    out = Channel(sys.stdout.buffer)
    sys.stdout = sys.stderr  # print из кода ядра/модуля не попадёт в канал
    inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
    threading.Thread(target=_stdin_reader, args=(channel_in, inbox), daemon=True).start()

    start = inbox.get()
    if start is None or start.get("t") != "start":
        return 1
    match = LiveMatch(start, out, inbox)
    try:
        match.build()
        state = match.run()
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        try:
            match.close("error", err)
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
        return 1
    match.close(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
