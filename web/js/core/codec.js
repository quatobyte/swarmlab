// Пакеты сервера и записи реплея `.swr` → объекты JS (ARCHITECTURE §5, §7).
// Массивы NumPy приходят как {"__nd__": [dtype, shape, bytes]} и превращаются в typed arrays
// (свойство `.shape`); float16 и 64-битные целые переводятся в Float32/Float64.

import { decode } from "./msgpack.js";
import { decompress } from "../../vendor/fzstd/fzstd.js";

const MAGIC = "SWR1";

let f16table = null;

/** float16 (биты в Uint16Array) → Float32Array. */
export function halfToFloat(u16) {
  if (!f16table) {
    f16table = new Float32Array(65536);
    for (let h = 0; h < 65536; h++) {
      const s = h & 0x8000 ? -1 : 1;
      const e = (h >> 10) & 0x1f;
      const f = h & 0x3ff;
      let v;
      if (e === 0) v = f * 2 ** -24;
      else if (e === 31) v = f ? NaN : Infinity;
      else v = (1 + f / 1024) * 2 ** (e - 15);
      f16table[h] = s * v;
    }
  }
  const out = new Float32Array(u16.length);
  for (let i = 0; i < u16.length; i++) out[i] = f16table[u16[i]];
  return out;
}

/** Массив NumPy из пакета → typed array с `.shape`. */
export function ndarray(dtype, shape, bytes) {
  if (dtype[0] === ">") throw new Error(`Порядок байт big-endian не поддерживается: ${dtype}`);
  const code = dtype.slice(1);
  const buf = bytes.slice().buffer; // копия: выравнивание под тип
  let out;
  switch (code) {
    case "u1": case "b1": out = new Uint8Array(buf); break;
    case "i1": out = new Int8Array(buf); break;
    case "u2": out = new Uint16Array(buf); break;
    case "i2": out = new Int16Array(buf); break;
    case "u4": out = new Uint32Array(buf); break;
    case "i4": out = new Int32Array(buf); break;
    case "f2": out = halfToFloat(new Uint16Array(buf)); break;
    case "f4": out = new Float32Array(buf); break;
    case "f8": out = new Float64Array(buf); break;
    case "i8": out = Float64Array.from(new BigInt64Array(buf), Number); break;
    case "u8": out = Float64Array.from(new BigUint64Array(buf), Number); break;
    default: throw new Error(`Неизвестный тип массива: ${dtype}`);
  }
  out.shape = shape;
  return out;
}

function revive(v) {
  if (v === null || typeof v !== "object" || v instanceof Uint8Array) return v;
  if (Array.isArray(v)) {
    for (let i = 0; i < v.length; i++) v[i] = revive(v[i]);
    return v;
  }
  const nd = v.__nd__;
  if (nd !== undefined && Object.keys(v).length === 1) return ndarray(nd[0], nd[1], nd[2]);
  for (const k in v) v[k] = revive(v[k]);
  return v;
}

/** Один пакет msgpack (WS или запись реплея) → объект с полем `t`. */
export function decodePacket(bytes) {
  return revive(decode(bytes));
}

/** Файл `.swr` → {header, frames, footer}. Оборванный файл читается до последней целой записи. */
export function parseReplay(arrayBuffer) {
  const raw = new Uint8Array(arrayBuffer);
  const magic = String.fromCharCode(...raw.subarray(0, 4));
  if (magic !== MAGIC) throw new Error("Это не реплей SwarmLab (нет сигнатуры SWR1)");
  const data = decompress(raw.subarray(4));
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let header = null;
  let footer = null;
  const frames = [];
  let at = 0;
  while (at + 4 <= data.length) {
    const n = view.getUint32(at, true);
    if (at + 4 + n > data.length) break;
    const rec = decodePacket(data.subarray(at + 4, at + 4 + n));
    at += 4 + n;
    if (!header) {
      if (rec.t !== "header") throw new Error("Первая запись реплея — не заголовок");
      header = rec;
    } else if (rec.t === "frame") frames.push(rec);
    else if (rec.t === "footer") footer = rec;
  }
  if (!header) throw new Error("Пустой реплей");
  return { header, frames, footer };
}

/** uint16 с фиксированной точкой в рамке [lo, hi] → метры (x, y, z мира), Float32Array (K*3). */
export function dequantize(q, lo, hi) {
  const out = new Float32Array(q.length);
  for (let i = 0; i < q.length; i += 3) {
    out[i] = lo[0] + (q[i] / 65535) * (hi[0] - lo[0]);
    out[i + 1] = lo[1] + (q[i + 1] / 65535) * (hi[1] - lo[1]);
    out[i + 2] = lo[2] + (q[i + 2] / 65535) * (hi[2] - lo[2]);
  }
  return out;
}
