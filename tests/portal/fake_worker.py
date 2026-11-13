"""Подставной процесс живого матча для тестов очереди портала (в `master` нет модуля).

Тот же канал, что у `swarmlab.server.worker` (u32 LE длина + msgpack): на `start` отвечает
`status running`, на `stop` или EOF — `status stopped` и выходит. Реплей не пишет.
`SWARMLAB_FAKE_WORKER_RECORD` — файл, куда дописать пакет `start` (строка JSON).
"""

from __future__ import annotations

import json
import os
import sys

from swarmlab.core.protocol import encode, read_frame


def main() -> int:
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    mid = ""

    def status(state: str) -> None:
        out.write(encode({"t": "status", "match_id": mid, "state": state, "speed": 1.0,
                          "time": 0.0, "duration_s": 60.0, "rtf": 1.0, "score": None}))
        out.flush()

    while True:
        msg = read_frame(inp)
        if msg is None or msg.get("t") == "stop":
            status("stopped")
            return 0
        if msg.get("t") == "start":
            mid = str(msg.get("id", ""))
            record = os.environ.get("SWARMLAB_FAKE_WORKER_RECORD")
            if record:
                with open(record, "a", encoding="utf-8") as f:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            status("running")


if __name__ == "__main__":
    raise SystemExit(main())
