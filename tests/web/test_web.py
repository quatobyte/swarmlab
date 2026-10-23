"""Вьюер `web/`: офлайн (без CDN), версии vendored-библиотек, JS-кодек читает реплеи Python."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from swarmlab.bees.module import dequantize
from swarmlab.core.config import load_match
from swarmlab.core.module import Replayable
from swarmlab.core.replay import ReplayWriter, make_header, read_replay
from swarmlab.core.sim import Simulation

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
#: Загрузка по сети: import/from "http…", src=/href=, url(…), адреса в import map.
_REMOTE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*)["'](?:https?:)?//"""
    r"""|\b(?:src|href)=["']?(?:https?:)?//|url\(\s*["']?(?:https?:)?//|":\s*"(?:https?:)?//"""
)


#: Пространства имён XML/SVG выглядят как адреса, но браузер по ним не ходит.
_XML_NAMESPACE = "www.w3.org/"


def test_web_loads_nothing_from_network():
    """Демо может быть без интернета: ни один импорт, скрипт или стиль не идёт по сети."""
    offenders = []
    for path in WEB.rglob("*"):
        if path.suffix not in (".js", ".mjs", ".html", ".css"):
            continue
        text = path.read_text(encoding="utf-8")
        for m in _REMOTE.finditer(text):
            if text.startswith(_XML_NAMESPACE, m.end()):
                continue  # xmlns="http://www.w3.org/2000/svg" (Blockly) — имя, а не загрузка
            offenders.append(f"{path.relative_to(ROOT)}: {text[m.start():m.end() + 30]!r}")
    assert offenders == []


def test_vendor_files_and_versions_recorded():
    vendor = WEB / "vendor"
    versions = (vendor / "VERSIONS.md").read_text(encoding="utf-8")
    for rel in ("three/three.module.js", "three/three.core.js",
                "three/addons/controls/OrbitControls.js",
                "three/addons/utils/BufferGeometryUtils.js", "fzstd/fzstd.js"):
        assert (vendor / rel).is_file(), rel
        assert rel in versions, rel
    assert "REVISION = '186'" in (vendor / "three/three.core.js").read_text(encoding="utf-8")
    assert "0.186.1" in versions and "0.1.1" in versions
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '"three": "./vendor/three/three.module.js"' in html


def test_blockly_vendored_offline():
    """M7b: Blockly — vendored, версия записана, подключён обычными <script>, медиа — свои."""
    vendor = WEB / "vendor"
    versions = (vendor / "VERSIONS.md").read_text(encoding="utf-8")
    for rel in ("blockly/blockly_compressed.js", "blockly/blocks_compressed.js",
                "blockly/msg/ru.js", "blockly/media/sprites.svg", "blockly/LICENSE"):
        assert (vendor / rel).is_file(), rel
    assert "| Blockly | 13.4.0 |" in versions and "blockly-13.4.0.tgz" in versions
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for rel in ("blockly_compressed.js", "blocks_compressed.js", "msg/ru.js"):
        assert f'<script src="vendor/blockly/{rel}"></script>' in html
    # Без media Blockly пошёл бы за картинками на static.blockly.com.
    editor = (WEB / "js/modules/bees/blocks_editor.js").read_text(encoding="utf-8")
    assert 'media: "vendor/blockly/media/"' in editor


@pytest.fixture(scope="module")
def short_replay(tmp_path_factory) -> Path:
    """Короткий матч m2_economy (3 с) с записью реплея."""
    path = tmp_path_factory.mktemp("web") / "short.swr"
    cfg = load_match(ROOT / "configs/matches/m2_economy.yaml", cli_overrides=["duration_s=3"])
    with Simulation(cfg) as sim:
        assert isinstance(sim.module, Replayable)
        writer = ReplayWriter(path, make_header(cfg, sim.teams, sim.module.scene()))
        sim.on_frame = writer
        sim.run()
        writer.close(sim.module.score())
    return path


@pytest.mark.skipif(shutil.which("node") is None, reason="нет Node.js — JS-проверка пропущена")
def test_js_codec_reads_python_replay(short_replay):
    rp = read_replay(short_replay)
    k = 15
    script = ROOT / "tests/web/codec_check.mjs"
    out = subprocess.run(["node", str(script), str(short_replay), str(k)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    h = rp.header
    scene = h["scene"]
    f = rp.frames[k]
    assert js["module"] == h["module"] and js["seed"] == h["seed"]
    assert js["frames"] == len(rp.frames) and js["footerHash"] == rp.hash
    assert js["t0"] == rp.frames[0].time and js["t1"] == rp.frames[-1].time
    terrain = scene["world"]["terrain"]
    assert js["terrainShape"] == list(terrain.shape)
    assert js["terrainSum"] == pytest.approx(float(terrain.sum()), rel=1e-6)
    assert js["tick"] == f.tick
    assert js["beeUid"] == f.arrays["bee_uid"].tolist() and js["beeUid"]
    pos = dequantize(f.arrays["bee_pos"], scene["pos_lo"], scene["pos_hi"])
    np.testing.assert_allclose(js["beePos"], pos.ravel(), atol=1e-3)
    np.testing.assert_allclose(js["beeVel"], f.arrays["bee_vel"].astype(np.float64).ravel())
    np.testing.assert_allclose(js["honey"], f.arrays["hive_honey"], rtol=1e-6)
    assert js["events"] == sum(len(fr.events) for fr in rp.frames)
    assert js["sample"]["index"] == k and js["sample"]["alpha"] == pytest.approx(0.5)
    assert js["before"] == -1 and js["after"] == len(rp.frames) - 1
    assert js["half"] == [1.0, -2.0, 65504.0, pytest.approx(5.96e-8, rel=1e-3)]
    assert js["msgpack"] == [2**32, -123, pytest.approx(3.141592653589793)]
