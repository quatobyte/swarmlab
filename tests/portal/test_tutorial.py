"""Запрос учебной кампании совместим с приватными скриптами актуального портала."""

from __future__ import annotations

import json
import shutil
import subprocess
import time

import pytest
from websockets.sync.client import connect

from swarmlab.core.replay import unpack

from .conftest import ROOT


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — запрос кампании")
def test_campaign_request_uses_private_program_and_readonly_rivals(make_portal):
    portal = make_portal(real_matches=True)
    player, other = portal.user("learner@example.ru"), portal.user("other@example.ru")
    code = (ROOT / "tests/bees/tutorial/ref_8.py").read_text(encoding="utf-8")
    assert player.json("PUT", "/api/scripts/tutorial.py", {"text": code})[0] == 200
    assert other.json("GET", "/api/scripts/tutorial.py")[0] == 404
    scripts = player.json("GET", "/api/scripts")[1]
    for name in ("example_rival_hoarder.py", "example_rival_horde.py"):
        assert next(s for s in scripts if s["name"] == name)["readonly"]
        assert player.json("PUT", f"/api/scripts/{name}", {"text": code})[0] == 403
    # Тело запроса строит сама кампания, как в браузере; правила целей здесь не повторяются.
    js = """
      import { MISSIONS, matchRequest } from './web/js/modules/bees/missions.js';
      console.log(JSON.stringify(matchRequest(MISSIONS[7], {
        script: 'tutorial.py', scripts: JSON.parse(process.argv[1])
      })));
    """
    out = subprocess.run(["node", "--input-type=module", "-e", js, json.dumps(scripts)],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    body = json.loads(out.stdout)
    body["overrides"].append("duration_s=2")
    status, match = player.json("POST", "/api/matches", body)
    assert status == 200, match
    mid = match["id"]
    assert other.json("GET", f"/api/matches/{mid}")[0] == 404
    with connect(f"{portal.ws}/ws/matches/{mid}",
                 additional_headers={"Cookie": player.cookie_header(),
                                     "Origin": portal.base}) as ws:
        while True:
            packet = unpack(ws.recv(timeout=30))
            if packet["t"] == "header":
                assert len(packet["runners"]) == 3
                assert all(r["ok"] for r in packet["runners"]), packet["runners"]
                break
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = player.json("GET", f"/api/matches/{mid}")[1]["state"]
        if state in ("finished", "stopped", "error"):
            break
        time.sleep(0.1)
    assert state == "finished"
    assert player.json("GET", "/api/scripts/tutorial.py")[1]["text"] == code
