"""Воркер естественно завершает матч при открытом stdin без ошибки финализации Python."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from swarmlab.core.protocol import encode

ROOT = Path(__file__).resolve().parents[2]


def test_worker_finishes_with_open_stdin_without_fatal_error(tmp_path: Path) -> None:
    proc = subprocess.Popen([sys.executable, "-m", "swarmlab.server.worker"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=ROOT)
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    stdout = bytearray()
    stderr = bytearray()
    out_thread = threading.Thread(target=lambda: stdout.extend(proc.stdout.read()), daemon=True)
    err_thread = threading.Thread(target=lambda: stderr.extend(proc.stderr.read()), daemon=True)
    out_thread.start()
    err_thread.start()
    try:
        proc.stdin.write(encode({"t": "start", "id": "natural-end",
                                 "match": str(ROOT / "configs/matches/m0.yaml"),
                                 "overrides": ["duration_s=1"],
                                 "replay": str(tmp_path / "natural-end.swr")}))
        proc.stdin.flush()
        assert proc.wait(30) == 0
        out_thread.join(5)
        err_thread.join(5)
        assert b"Fatal Python error" not in stderr, stderr.decode(errors="replace")
        assert stdout
    finally:
        proc.stdin.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)
