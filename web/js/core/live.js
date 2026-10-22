// Живой матч: кадры по WebSocket, управление паузой и скоростью уходит на сервер.
// Рендер отстаёт от свежего кадра на ~1.5 периода кадров — так есть между чем интерполировать.

import { decodePacket } from "./codec.js";
import { Emitter, frameIndexAt, sampleAt } from "./playback.js";

const KEEP_FRAMES = 60;

export class LiveSource extends Emitter {
  constructor(matchId) {
    super();
    this.kind = "live";
    this.matchId = matchId;
    this.header = null;
    this.status = null;
    this.footer = null;
    this.frames = [];
    this.renderTime = null;
    this.speed = 1;
    this.paused = false;
    this.closed = false;
    this._emittedIndex = -1; // tick последнего кадра, чьи события уже отданы
    this._lastTick = -1;
    this._connect();
  }

  _connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/matches/${encodeURIComponent(this.matchId)}`);
    ws.binaryType = "arraybuffer";
    ws.onmessage = (ev) => this._onPacket(decodePacket(new Uint8Array(ev.data)));
    ws.onclose = (ev) => {
      this.closed = true;
      this.emit("close", ev);
    };
    ws.onerror = () => this.emit("error", "Нет связи с сервером");
    this.ws = ws;
  }

  _onPacket(msg) {
    switch (msg.t) {
      case "header":
        this.header = msg;
        this.frameDt = 1 / (msg.frame_hz || 10);
        this.emit("header", msg);
        break;
      case "frame":
        if (msg.tick <= this._lastTick) return;
        this._lastTick = msg.tick;
        this.frames.push(msg);
        if (this.frames.length > KEEP_FRAMES) this.frames.splice(0, this.frames.length - KEEP_FRAMES);
        if (this.renderTime === null) this.renderTime = msg.time;
        break;
      case "status":
        this.status = msg;
        this.speed = msg.speed || 1;
        this.paused = msg.state === "paused";
        this.emit("status", msg);
        break;
      case "log":
        this.emit("log", msg);
        break;
      case "footer":
        this.footer = msg;
        this.emit("footer", msg);
        break;
    }
  }

  get ready() {
    return this.header !== null && this.frames.length > 0;
  }

  get time() {
    return this.renderTime ?? 0;
  }

  get duration() {
    return this.header?.duration_s ?? 0;
  }

  /**
   * Продвинуть часы рендера на `wallDt` секунд и вернуть пару кадров.
   *
   * Часы идут с той скоростью, с какой реально приходят кадры (RTF из статуса), а не с
   * выбранной: если машина не успевает, пчёлы плавно летят в замедлении, а не стоят и прыгают.
   * Отставание от свежего кадра мягко подтягивается к ~1.5 периодам кадров (есть между чем
   * интерполировать); большой разрыв (вкладка была скрыта) — перескок.
   */
  sample(wallDt) {
    const frames = this.frames;
    if (!frames.length) return null;
    const latest = frames[frames.length - 1].time;
    const st = this.status;
    const ended = st && ["finished", "stopped", "error"].includes(st.state);
    const rate = st && st.state === "running" && st.rtf > 0 ? Math.min(this.speed, st.rtf) : this.speed;
    // Задержка в секундах симуляции: 1.5 периода кадров с поправкой на темп прихода кадров.
    const delay = ended ? 0 : 1.5 * (this.frameDt || 0.1) * Math.max(1, rate);
    const target = latest - delay;
    if (!this.paused) {
      const pull = (target - this.renderTime) * Math.min(1, 1.5 * wallDt); // мягкая подстройка
      this.renderTime += wallDt * rate + pull;
    }
    if (this.renderTime > latest) this.renderTime = latest;
    if (this.renderTime < latest - 3 * Math.max(1, this.speed)) this.renderTime = target;
    // События кадров, через которые прошло время рендера.
    const i = frameIndexAt(frames, this.renderTime);
    for (let k = 0; k <= i; k++) {
      const f = frames[k];
      if (f.tick > this._emittedIndex) {
        this._emittedIndex = f.tick;
        if (f.events.length) this.emit("events", f.events);
      }
    }
    return sampleAt(frames, this.renderTime);
  }

  send(msg) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }
  pause() { this.send({ t: "pause" }); }
  resume() { this.send({ t: "resume" }); }
  setSpeed(v) { this.send({ t: "speed", value: v }); }
  stop() { this.send({ t: "stop" }); }

  close() {
    this.closed = true;
    this.ws.onclose = null;
    this.ws.close();
  }
}
