"""Кадры протокола раннера: 4 байта длины + msgpack."""

import io

import pytest

from swarmlab.core import protocol
from swarmlab.core.protocol import (
    CommandBatch,
    ProtocolError,
    SensorBatch,
    encode,
    read_frame,
    write_frame,
)


class Trickle(io.RawIOBase):
    """Поток, отдающий не больше `chunk` байт за чтение (как пайп под нагрузкой)."""

    def __init__(self, data: bytes, chunk: int = 3) -> None:
        self.data, self.pos, self.chunk = data, 0, chunk

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        n = self.chunk if n < 0 else min(n, self.chunk)
        out = self.data[self.pos : self.pos + n]
        self.pos += len(out)
        return out


def test_batches_roundtrip_through_frames():
    sensors = SensorBatch(7, 1, 20.0, {"honey": 20.5}, [{"me": {"id": 3, "pos": [1.0, 2, 3]}}])
    commands = CommandBatch(
        7, {3: {"move": ["fly_to", 1.0, 2.0, None, None, True]}}, {"breed": [["scout", 1]]},
        cpu_ms=1.5, errors=[4], log=["привет"],
    )
    buf = io.BytesIO()
    write_frame(buf, sensors.to_message())
    write_frame(buf, commands.to_message())
    stream = Trickle(buf.getvalue())
    assert SensorBatch.from_message(read_frame(stream)) == sensors
    got = CommandBatch.from_message(read_frame(stream))
    assert got == commands and list(got.commands) == [3]  # целые ключи сохраняются
    assert read_frame(stream) is None  # EOF между кадрами


def test_truncated_frame_is_an_error():
    data = encode({"t": "stop"})
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO(data[:-1]))


def test_oversized_and_garbage_frames_rejected(monkeypatch):
    monkeypatch.setattr(protocol, "MAX_FRAME_BYTES", 16)
    with pytest.raises(ProtocolError):
        encode({"t": "x", "pad": "x" * 100})
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO((1000).to_bytes(4, "little") + b"\0" * 1000))
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO((2).to_bytes(4, "little") + b"\xc1\xc1"))  # не msgpack
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO(encode({"no_type": 1})[:4] + encode({"no_type": 1})[4:]))


def test_no_pickle_in_protocol():
    import msgpack

    with pytest.raises(TypeError):
        encode({"t": "x", "obj": object()})  # произвольные объекты не сериализуются
    assert msgpack.unpackb(encode({"t": "x"})[4:]) == {"t": "x"}
