// Проверка JS-кодека вьюера под Node: читает .swr тем же кодом, что браузер, и печатает сводку в JSON.
//   node tests/web/codec_check.mjs <файл.swr> <номер кадра>
// Тест tests/web/test_web.py сравнивает сводку с тем, что прочитал Python.

import { readFileSync } from "node:fs";
import { dequantize, halfToFloat, parseReplay } from "../../web/js/core/codec.js";
import { decode } from "../../web/js/core/msgpack.js";
import { frameIndexAt, sampleAt } from "../../web/js/core/playback.js";

const [file, k] = process.argv.slice(2);
const buf = readFileSync(file);
const { header, frames, footer } = parseReplay(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length));
const scene = header.scene;
const f = frames[Number(k)];
const pos = dequantize(f.arrays.bee_pos, scene.pos_lo, scene.pos_hi);

// Интерполяция: середина между кадрами k и k+1.
const tMid = (frames[k].time + frames[Number(k) + 1].time) / 2;
const s = sampleAt(frames, tMid);

// msgpack: краевые типы.
const mp = decode(new Uint8Array([0x93, 0xcf, 0, 0, 0, 1, 0, 0, 0, 0, 0xd0, 0x85, 0xcb, 0x40, 0x09, 0x21, 0xfb, 0x54, 0x44, 0x2d, 0x18]));

console.log(JSON.stringify({
  module: header.module,
  seed: header.seed,
  frames: frames.length,
  footerHash: footer ? footer.hash : null,
  t0: frames[0].time,
  t1: frames[frames.length - 1].time,
  terrainShape: scene.world.terrain.shape,
  terrainSum: Array.from(scene.world.terrain).reduce((a, b) => a + b, 0),
  tick: f.tick,
  beeUid: Array.from(f.arrays.bee_uid),
  beePos: Array.from(pos),
  beeVel: Array.from(f.arrays.bee_vel),
  honey: Array.from(f.arrays.hive_honey),
  events: frames.reduce((n, fr) => n + fr.events.length, 0),
  sample: { index: s.index, alpha: s.alpha, time: s.time },
  before: frameIndexAt(frames, -1),
  after: frameIndexAt(frames, 1e9),
  half: Array.from(halfToFloat(new Uint16Array([0x3c00, 0xc000, 0x7bff, 0x0001]))),
  msgpack: mp,
}));
