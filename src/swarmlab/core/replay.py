"""Реплеи `.swr`: запись, чтение, хеш (ARCHITECTURE §5, DECISIONS №39).

Формат файла::

    b"SWR1" + поток zstd из записей  [u32 LE длина][msgpack]
      header — версии, конфиг матча, скрипты (путь + sha256), сцена модуля
      frame  — кадры 10 Гц: {t, tick, time, arrays, events}
      footer — {t, frames, hash, score}  (нет, если матч оборвался)

Массивы NumPy в msgpack — словарь `{"__nd__": [dtype, shape, bytes]}`: ядро пишет
их как есть, компактные типы (квантование позиций и т. п.) выбирает модуль в
`snapshot()`. Хеш реплея — sha256 несжатых байтов всех записей `frame` по порядку:
он не зависит от путей и версий в заголовке, и при чтении его можно проверить по
тем же байтам (длина перед записью). Один seed и одни скрипты на одной машине →
одинаковый хеш.
"""

from __future__ import annotations

import hashlib
import platform
import struct
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, BinaryIO

import msgpack
import numpy as np
import zstandard

from swarmlab.core.module import Frame, ScoreBoard, TeamSpec

MAGIC = b"SWR1"
FORMAT_VERSION = 1
#: Уровень сжатия zstd: 9 — хорошее сжатие при малой цене на кадр (~0.1 мс).
ZSTD_LEVEL = 9
_LEN = struct.Struct("<I")
_MAX_RECORD = 256 * 1024 * 1024
_ND = "__nd__"
#: Пакеты, версии которых пишутся в заголовок.
_VERSIONED = ("swarmlab", "numpy", "msgpack", "zstandard", "pydantic")


class ReplayError(RuntimeError):
    """Файл не похож на реплей или повреждён."""


# ------------------------------------------------------------------ msgpack + NumPy


def _default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        a = np.ascontiguousarray(obj)
        return {_ND: [a.dtype.str, list(a.shape), a.tobytes()]}
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Не умею сохранить в реплей: {type(obj).__name__}")


def _hook(d: dict[str, Any]) -> Any:
    if len(d) == 1 and _ND in d:
        dtype, shape, data = d[_ND]
        return np.frombuffer(data, dtype=np.dtype(dtype)).reshape(shape)
    return d


def pack(obj: Any) -> bytes:
    """msgpack с массивами NumPy; порядок ключей — порядок вставки (детерминированно)."""
    return msgpack.packb(obj, default=_default, use_bin_type=True)


def unpack(data: bytes) -> Any:
    return msgpack.unpackb(data, object_hook=_hook, raw=False, strict_map_key=False)


# ------------------------------------------------------------------ заголовок


def _version(dist: str) -> str | None:
    try:
        return version(dist)
    except PackageNotFoundError:
        return None


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def make_header(cfg: Any, teams: Iterable[TeamSpec], scene: dict[str, Any]) -> dict[str, Any]:
    """Заголовок реплея: всё, чтобы понять и воспроизвести матч (кроме самих кадров)."""
    versions = {name: _version(name) for name in _VERSIONED}
    versions["python"] = platform.python_version()
    return {
        "t": "header",
        "format": FORMAT_VERSION,
        "versions": versions,
        "platform": f"{platform.system()} {platform.machine()}",
        "module": cfg.module,
        "seed": cfg.seed,
        "profile": cfg.profile,
        "duration_s": cfg.duration_s,
        "config": cfg.model_dump(mode="json"),
        "teams": [
            {"team": t.team, "name": t.name, "color": t.color,
             "script": str(t.script) if t.script else None,
             "sha256": file_sha256(t.script) if t.script else None}
            for t in teams
        ],
        "scene": scene,
    }


def pack_frame(frame: Frame) -> bytes:
    """Запись `frame` реплея — те же байты идут в файл, в хеш и в живой стрим."""
    return pack({"t": "frame", "tick": frame.tick, "time": frame.time,
                 "arrays": frame.arrays, "events": frame.events})


def score_dict(board: ScoreBoard) -> dict[str, Any]:
    return {"teams": {str(k): v for k, v in board.teams.items()}, "winner": board.winner}


def event_key(event: dict[str, Any]) -> str:
    """Ключ сводки событий: тип и, если есть, причина (`death/hornet`)."""
    key = str(event.get("type", "?"))
    cause = event.get("cause")
    return f"{key}/{cause}" if cause is not None else key


# ------------------------------------------------------------------ запись


class ReplayWriter:
    """Пишет реплей по мере матча: `writer(frame)` подходит как `on_frame` симуляции."""

    def __init__(self, path: str | Path, header: dict[str, Any], *, level: int = ZSTD_LEVEL):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file: BinaryIO = self.path.open("wb")
        self._file.write(MAGIC)
        self._zstd = zstandard.ZstdCompressor(level=level).stream_writer(self._file)
        self._hash = hashlib.sha256()
        self.frames = 0
        self.raw_bytes = 0
        #: Сводка событий: «тип[/причина]» → сколько.
        self.events: Counter[str] = Counter()
        self.closed = False
        self._record(pack(header))

    def _record(self, data: bytes) -> None:
        self._zstd.write(_LEN.pack(len(data)))
        self._zstd.write(data)
        self.raw_bytes += len(data) + _LEN.size

    def write(self, frame: Frame) -> bytes:
        """Записать кадр; вернуть его байты msgpack (их же сервер шлёт в живой стрим)."""
        data = pack_frame(frame)
        self._hash.update(data)
        self._record(data)
        self.frames += 1
        self.events.update(event_key(e) for e in frame.events)
        return data

    __call__ = write

    @property
    def hash(self) -> str:
        return self._hash.hexdigest()

    def close(self, score: ScoreBoard | None = None) -> str:
        """Дописать итог и закрыть файл; вернуть хеш реплея."""
        if not self.closed:
            footer = {"t": "footer", "frames": self.frames, "hash": self.hash,
                      "score": score_dict(score) if score is not None else None}
            self._record(pack(footer))
            self._zstd.close()  # закрывает и файл
            self.closed = True
        return self.hash

    def __enter__(self) -> ReplayWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ------------------------------------------------------------------ чтение


@dataclass
class Replay:
    """Прочитанный реплей. `hash` — пересчитан по байтам кадров при чтении."""

    header: dict[str, Any]
    frames: list[Frame] = field(default_factory=list)
    footer: dict[str, Any] | None = None
    hash: str = ""

    @property
    def complete(self) -> bool:
        return self.footer is not None

    @property
    def hash_ok(self) -> bool:
        """Хеш в итоге совпадает с пересчитанным (файл цел)."""
        return self.footer is not None and self.footer.get("hash") == self.hash

    def event_counts(self) -> Counter[str]:
        return Counter(event_key(e) for f in self.frames for e in f.events)


def read_replay(path: str | Path) -> Replay:
    """Прочитать реплей целиком (5 минут матча — несколько МБ, это быстро).

    Оборванный файл (матч не дописался) читается до последней целой записи:
    кадры есть, итога нет (`complete` = False).
    """
    path = Path(path)
    raw = path.read_bytes()
    if raw[: len(MAGIC)] != MAGIC:
        raise ReplayError(f"{path}: это не реплей SwarmLab (нет сигнатуры {MAGIC!r})")
    try:
        data = zstandard.ZstdDecompressor().decompressobj().decompress(raw[len(MAGIC):])
    except zstandard.ZstdError as e:
        raise ReplayError(f"{path}: повреждённое сжатие: {e}") from e
    h = hashlib.sha256()
    replay: Replay | None = None
    view = memoryview(data)
    at = 0
    while at + _LEN.size <= len(view):
        (n,) = _LEN.unpack_from(view, at)
        if n > _MAX_RECORD:
            raise ReplayError(f"{path}: запись {n} байт — файл повреждён")
        body = view[at + _LEN.size : at + _LEN.size + n]
        if len(body) < n:
            break  # оборванная последняя запись
        at += _LEN.size + n
        rec = unpack(body)
        kind = rec.get("t")
        if replay is None:
            if kind != "header":
                raise ReplayError(f"{path}: первая запись — не заголовок")
            replay = Replay(header=rec)
        elif kind == "frame":
            h.update(body)
            replay.frames.append(
                Frame(tick=rec["tick"], time=rec["time"], arrays=rec["arrays"],
                      events=rec["events"])
            )
        elif kind == "footer":
            replay.footer = rec
    if replay is None:
        raise ReplayError(f"{path}: пустой реплей")
    replay.hash = h.hexdigest()
    return replay


def default_replay_path(match: Path, seed: int, root: Path = Path("replays")) -> Path:
    """`replays/<матч>-s<seed>.swr`."""
    return root / f"{Path(match).stem}-s{seed}.swr"

