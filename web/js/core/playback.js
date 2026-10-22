// Общая часть источников кадров: события, поиск пары кадров для интерполяции.
// Источник (живой или реплей) отдаёт рендеру одно и то же: header и sample() → {a, b, alpha, time}.

export class Emitter {
  constructor() {
    this._handlers = {};
  }
  on(type, fn) {
    (this._handlers[type] ||= []).push(fn);
    return this;
  }
  emit(type, payload) {
    for (const fn of this._handlers[type] || []) fn(payload);
  }
}

/** Индекс последнего кадра с time ≤ t (двоичный поиск); -1, если t раньше первого. */
export function frameIndexAt(frames, t) {
  let lo = 0;
  let hi = frames.length - 1;
  if (hi < 0 || frames[0].time > t) return -1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].time <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Пара кадров вокруг момента t и доля интерполяции. */
export function sampleAt(frames, t) {
  if (!frames.length) return null;
  let i = frameIndexAt(frames, t);
  if (i < 0) i = 0;
  const a = frames[i];
  const b = frames[i + 1] || null;
  let alpha = 0;
  if (b && b.time > a.time) alpha = Math.min(Math.max((t - a.time) / (b.time - a.time), 0), 1);
  return { a, b, alpha, time: b ? a.time + alpha * (b.time - a.time) : a.time, index: i };
}
