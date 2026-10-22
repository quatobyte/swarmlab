// Реплей `.swr`: весь файл в памяти, свои часы — пауза, скорость, перемотка.

import { parseReplay } from "./codec.js";
import { Emitter, frameIndexAt, sampleAt } from "./playback.js";

export class ReplaySource extends Emitter {
  constructor({ header, frames, footer }, name = "") {
    super();
    this.kind = "replay";
    this.name = name;
    this.header = header;
    this.frames = frames;
    this.footer = footer;
    this.t0 = frames.length ? frames[0].time : 0;
    this.t1 = frames.length ? frames[frames.length - 1].time : 0;
    this.renderTime = this.t0;
    this.speed = 1;
    this.paused = false;
    this._cursor = -1; // последний кадр, чьи события уже отданы
  }

  static async fromUrl(url, name) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Не удалось загрузить реплей: ${res.status} ${res.statusText}`);
    return new ReplaySource(parseReplay(await res.arrayBuffer()), name);
  }

  static async fromFile(file) {
    return new ReplaySource(parseReplay(await file.arrayBuffer()), file.name);
  }

  get ready() {
    return this.frames.length > 0;
  }

  get time() {
    return this.renderTime;
  }

  get duration() {
    return this.t1;
  }

  get ended() {
    return this.renderTime >= this.t1;
  }

  sample(wallDt) {
    if (!this.frames.length) return null;
    if (!this.paused && !this.ended) {
      this.renderTime = Math.min(this.renderTime + wallDt * this.speed, this.t1);
    }
    const i = frameIndexAt(this.frames, this.renderTime);
    for (let k = this._cursor + 1; k <= i; k++) {
      const ev = this.frames[k].events;
      if (ev.length) this.emit("events", ev);
    }
    if (i > this._cursor) this._cursor = i;
    if (this.ended && !this._endEmitted) {
      this._endEmitted = true;
      this.emit("end", this.footer);
    }
    return sampleAt(this.frames, this.renderTime);
  }

  /** Перемотка: события до точки не проигрываются, вьюер сбрасывает ленту. */
  seek(t) {
    this.renderTime = Math.min(Math.max(t, this.t0), this.t1);
    this._cursor = frameIndexAt(this.frames, this.renderTime);
    this._endEmitted = false;
    this.emit("seek", this.renderTime);
  }

  pause() {
    this.paused = true;
    this.emit("status", { state: "paused", speed: this.speed });
  }
  resume() {
    if (this.ended) this.seek(this.t0);
    this.paused = false;
    this.emit("status", { state: "running", speed: this.speed });
  }
  setSpeed(v) {
    this.speed = v;
    this.emit("status", { state: this.paused ? "paused" : "running", speed: v });
  }
  close() {}
}
