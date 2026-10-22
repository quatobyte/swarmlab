// Вьюер модуля «пчёлки»: собирает мир, агентов, погоду и HUD; интерфейс для core/app.js:
//   update(sample, dt), onEvents(events), reset(), notify(text), pickAt(x, y), unfollow(),
//   focusHive(i), overview(), describeResult(score, stopped), dispose().

import * as THREE from "three";
import { Agents } from "./agents.js";
import { BeesHud, KIND_RU } from "./hud.js";
import { WeatherFx } from "./weather.js";
import { BeesWorld } from "./world.js";

export function createViewer({ stage, header }) {
  return new BeesViewer(stage, header);
}

class BeesViewer {
  constructor(stage, header) {
    this.stage = stage;
    this.header = header;
    const scene = header.scene;
    this.scene = scene;
    this.world = new BeesWorld(scene);
    this.agents = new Agents(scene, this.world.hiveColors);
    this.weather = new WeatherFx(stage, this.world.size);
    this.hud = new BeesHud(header);
    stage.scene.add(this.world.group, this.agents.group);
    this.followUid = null;
    this.lost = new Map(); // uid → причина гибели (из событий)
    this._camDir = new THREE.Vector3();
    stage.onFollowLost = () => this._followLost();
    this.overview();
  }

  overview() {
    this.unfollow();
    this.stage.overview(this.world.size);
  }

  focusHive(i) {
    const p = this.world.hivePos[i];
    if (p) {
      this.unfollow();
      this.stage.flyTo(p, 40);
    }
  }

  update(sample, dt) {
    this._lastTime = sample.time;
    // Пчёлы крупнее реального, когда камера далеко (иначе их не видно), и почти в натуральную
    // величину вблизи.
    const dist = this.stage.camera.position.distanceTo(this.stage.controls.target);
    this.agents.scale = Math.min(Math.max(dist / 14, 1.3), 3.5);
    this.agents.update(sample, dt);
    const A = sample.a.arrays;
    this.world.updateFlowers((sample.b || sample.a).arrays.flower_nectar);
    const ws = this.scene.weather_states[A.weather[0]] || "clear";
    this.weather.update(dt, ws, A.wind);
    this.stage.camera.getWorldDirection(this._camDir);
    this._camDir.y = 0;
    this._camDir.normalize();
    this.hud.update(sample.b && sample.alpha > 0.5 ? sample.b : sample.a, performance.now(), this._camDir);
    this.agents.setMarker(this.followUid);
    if (this.followUid != null) {
      const now = performance.now();
      if (now - (this._followShown || 0) > 200) {
        this._followShown = now;
        this.hud.showFollow(this.agents.info.get(this.followUid), this.followUid);
      }
    }
  }

  onEvents(events) {
    this.hud.onEvents(events);
    for (const e of events) {
      if (e.type === "death") this.lost.set(e.bee, `погиб(ла): ${e.cause === "hornet" ? "шершень" : e.cause === "spider" ? "паук" : "кончилась энергия"}`);
      if (e.type === "delivery") this.lost.set(e.bee, "вернулась в улей с нектаром");
      if (e.type === "hornet_death") this.lost.set(e.hornet, "погиб в тепловом шаре");
      if (e.type === "hornet_left") this.lost.set(e.hornet, "улетел с поля");
    }
    if (this.lost.size > 2000) this.lost.clear();
  }

  /** Служебное сообщение в ленту событий (например, от ядра вьюера). */
  notify(text) {
    this.hud.feed(this._lastTime || 0, text, true);
  }

  reset() {
    this.hud.clearFeed();
    this.lost.clear();
  }

  pickAt(x, y) {
    const uid = this.agents.pick(this.stage, x, y);
    if (uid == null) return false;
    this.followUid = uid;
    this._missing = 0;
    this.stage.follow((out) => {
      if (this.agents.positionOf(uid, out)) {
        this._missing = 0;
        return true;
      }
      return ++this._missing < 20; // пара кадров без цели — не повод отпускать
    });
    return true;
  }

  unfollow() {
    this.followUid = null;
    this.stage.unfollow();
    this.hud.showFollow(null);
  }

  _followLost() {
    const uid = this.followUid;
    const why = this.lost.get(uid) || "залетела в улей или исчезла";
    const info = this.agents.info.get(uid);
    const who = info?.type === "hornet" ? "Шершень" : "Пчела";
    this.hud.feed(this._lastTime || 0, `👁 ${who} #${uid}: ${why}`);
    this.followUid = null;
    this.hud.showFollow(null);
  }

  describeResult(score, stopped = false) {
    const head = stopped ? `Матч остановлен на ${Math.floor(this._lastTime / 60)}:${String(Math.floor(this._lastTime % 60)).padStart(2, "0")}` : "Матч окончен";
    if (!score || score.winner == null) return head;
    const w = score.winner;
    const row = score.teams?.[String(w)] || {};
    const lead = stopped ? "Впереди" : "Победил";
    const lines = [`${head}. ${lead} ${this.hud.teamName(w)} — мёд ${Number(row.honey ?? 0).toFixed(1)}`];
    const others = Object.entries(score.teams || {})
      .filter(([, r]) => r.place > 0)
      .sort((a, b) => a[1].place - b[1].place)
      .map(([t, r]) => `${r.place}. ${this.hud.teamName(Number(t))}: мёд ${r.honey.toFixed(1)}, доставлено ${r.delivered.toFixed(1)}, живых ${r.alive}`);
    return [...lines, ...others].join("\n");
  }

  dispose() {
    this.stage.scene.remove(this.world.group, this.agents.group, this.weather.rain);
    const free = (o) => o.traverse((m) => {
      m.geometry?.dispose();
      m.material?.dispose?.();
    });
    free(this.world.group);
    free(this.agents.group);
    free(this.weather.rain);
    this.stage.onFollowLost = null;
  }
}

export { KIND_RU };
