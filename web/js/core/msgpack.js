// Распаковка msgpack (только чтение) — всё, что пишет Python `msgpack.packb(use_bin_type=True)`.
// bin → Uint8Array-вид на исходный буфер (без копии); map → обычный объект.

const textDecoder = new TextDecoder("utf-8");

export function decode(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let pos = 0;

  function str(n) {
    const s = textDecoder.decode(bytes.subarray(pos, pos + n));
    pos += n;
    return s;
  }
  function bin(n) {
    const b = bytes.subarray(pos, pos + n);
    pos += n;
    return b;
  }
  function arr(n) {
    const out = new Array(n);
    for (let i = 0; i < n; i++) out[i] = read();
    return out;
  }
  function map(n) {
    const out = {};
    for (let i = 0; i < n; i++) {
      const k = read();
      out[k] = read();
    }
    return out;
  }

  function read() {
    const b = bytes[pos++];
    if (b <= 0x7f) return b;
    if (b >= 0xe0) return b - 0x100;
    if ((b & 0xf0) === 0x80) return map(b & 0x0f);
    if ((b & 0xf0) === 0x90) return arr(b & 0x0f);
    if ((b & 0xe0) === 0xa0) return str(b & 0x1f);
    let v;
    switch (b) {
      case 0xc0: return null;
      case 0xc2: return false;
      case 0xc3: return true;
      case 0xc4: v = view.getUint8(pos); pos += 1; return bin(v);
      case 0xc5: v = view.getUint16(pos); pos += 2; return bin(v);
      case 0xc6: v = view.getUint32(pos); pos += 4; return bin(v);
      case 0xca: v = view.getFloat32(pos); pos += 4; return v;
      case 0xcb: v = view.getFloat64(pos); pos += 8; return v;
      case 0xcc: v = view.getUint8(pos); pos += 1; return v;
      case 0xcd: v = view.getUint16(pos); pos += 2; return v;
      case 0xce: v = view.getUint32(pos); pos += 4; return v;
      case 0xcf: v = Number(view.getBigUint64(pos)); pos += 8; return v;
      case 0xd0: v = view.getInt8(pos); pos += 1; return v;
      case 0xd1: v = view.getInt16(pos); pos += 2; return v;
      case 0xd2: v = view.getInt32(pos); pos += 4; return v;
      case 0xd3: v = Number(view.getBigInt64(pos)); pos += 8; return v;
      case 0xd9: v = view.getUint8(pos); pos += 1; return str(v);
      case 0xda: v = view.getUint16(pos); pos += 2; return str(v);
      case 0xdb: v = view.getUint32(pos); pos += 4; return str(v);
      case 0xdc: v = view.getUint16(pos); pos += 2; return arr(v);
      case 0xdd: v = view.getUint32(pos); pos += 4; return arr(v);
      case 0xde: v = view.getUint16(pos); pos += 2; return map(v);
      case 0xdf: v = view.getUint32(pos); pos += 4; return map(v);
      default:
        throw new Error(`msgpack: неподдерживаемый байт 0x${b.toString(16)} на позиции ${pos - 1}`);
    }
  }

  const value = read();
  return value;
}
