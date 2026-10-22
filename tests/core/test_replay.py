"""Формат реплея `.swr` (ядро, без модуля): запись, чтение, хеш, обрыв."""

import numpy as np
import pytest

from swarmlab.core.module import Frame, ScoreBoard
from swarmlab.core.replay import MAGIC, ReplayError, ReplayWriter, read_replay


def _frames(n=30, seed=0):
    rng = np.random.default_rng(seed)
    for i in range(n):
        k = int(rng.integers(0, 20))
        yield Frame(
            tick=i * 20,
            time=(i + 1) * 0.1,
            arrays={
                "pos": rng.integers(0, 65535, (k, 3)).astype(np.uint16),
                "vel": rng.normal(0, 3, (k, 3)).astype(np.float16),
                "honey": np.array([20.0 + i, 19.5], dtype=np.float32),
            },
            events=[{"type": "death", "time": i * 0.1, "bee": i, "cause": "hornet"}]
            if i % 7 == 0 else [],
        )


def _write(path, frames, score=True):
    header = {"t": "header", "seed": 1, "scene": {"lo": np.array([-1.0, -2.0, 0.0])}}
    w = ReplayWriter(path, header)
    for f in frames:
        w(f)
    return w, (w.close(ScoreBoard(teams={0: {"honey": 3.0}}, winner=0)) if score else None)


def test_roundtrip_arrays_events_and_hash(tmp_path):
    path = tmp_path / "a.swr"
    src = list(_frames())
    w, digest = _write(path, src)
    assert path.read_bytes()[:4] == MAGIC
    rp = read_replay(path)
    assert rp.complete and rp.hash_ok and rp.hash == digest == w.hash
    assert np.array_equal(rp.header["scene"]["lo"], [-1.0, -2.0, 0.0])
    assert len(rp.frames) == len(src)
    for a, b in zip(src, rp.frames, strict=True):
        assert a.tick == b.tick and a.time == b.time and a.events == b.events
        for name, arr in a.arrays.items():
            assert b.arrays[name].dtype == arr.dtype
            assert np.array_equal(b.arrays[name], arr)
    assert rp.footer["score"] == {"teams": {"0": {"honey": 3.0}}, "winner": 0}
    assert rp.event_counts() == w.events == {"death/hornet": 5}


def test_same_frames_same_hash_different_frames_different_hash(tmp_path):
    _, h1 = _write(tmp_path / "1.swr", _frames(seed=1))
    _, h2 = _write(tmp_path / "2.swr", _frames(seed=1))
    _, h3 = _write(tmp_path / "3.swr", _frames(seed=2))
    assert h1 == h2 != h3


def test_truncated_replay_reads_frames_without_footer(tmp_path):
    path = tmp_path / "cut.swr"
    w = ReplayWriter(path, {"t": "header"})
    for f in _frames(50):
        w(f)
    w._zstd.flush()  # матч оборвался: итог не дописан, поток не закрыт
    w._file.flush()
    rp = read_replay(path)
    assert not rp.complete and not rp.hash_ok
    assert 0 < len(rp.frames) <= 50
    w._zstd.close()


def test_not_a_replay_is_an_error(tmp_path):
    bad = tmp_path / "x.swr"
    bad.write_bytes(b"hello world")
    with pytest.raises(ReplayError):
        read_replay(bad)
