// Вьюер модуля «пчёлки»: собирает мир, агентов, погоду и HUD; интерфейс для core/app.js:
//   update(sample, dt), onEvents(events), reset(), notify(text), pickAt(x, y), unfollow(),
//   focusHive(i), overview(), describeResult(score, stopped), dispose(),
//   setDebug(team, agents) — снимки программ от отладчика (M12, DECISIONS №105).
// `onInspect({team, line} | null)` — за чьей программой следит игрок и на какой она строке.

import * as THREE from "three";
import { Agents } from "./agents.js";
import { BeesHud, KIND_RU } from "./hud.js";
import { WeatherFx } from "./weather.js";
import { BeesWorld } from "./world.js";

export function createViewer({ stage, header, onInspect = null }) {
  return new BeesViewer(stage, header, onInspect);
}

/** На каком расстоянии от улья на экране клик считается кликом по улью, пикс: точный клик
 * (важнее пчёл рядом) и клик мимо пчёл. */
const HIVE_EXACT_PX = 16;
const HIVE_PICK_PX = 44;

class BeesViewer {
  constructor(stage, header, onInspect) {
    this.stage = stage;
    this.header = header;
    this.onInspect = onInspect;
    this.debug = new Map(); // команда → Map(ключ агента → снимок программы)
    this.followTeam = null; // улей пчелы, за которой следим (нужен, пока она внутри улья)
    this.followHive = null; // улей, чью программу показываем
    this._lastInfo = null;
    this._inspected = "";
    const scene = header.scene;
    this.scene = scene;
    this.world = new BeesWorld(scene);
    this.agents = new Agents(scene, this.world.hiveColors);
    this.weather = new WeatherFx(stage, this.world.size);
    this.hud = new BeesHud(header, (h) => this.inspectHive(h));
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
    if (this.followUid != null || this.followHive != null) {
      const now = performance.now();
      if (now - (this._followShown || 0) > 200) {
        this._followShown = now;
        this._showFollow();
      }
    }
  }

  // ------------------------------------------------------------ инспектор (M12)

  /** Снимки программ команды от отладчика: `agents` — {ключ: снимок | null (агента нет)}. */
  setDebug(team, agents) {
    let map = this.debug.get(team);
    if (!map) this.debug.set(team, (map = new Map()));
    for (const [key, snap] of Object.entries(agents || {})) {
      if (snap == null) map.delete(key);
      else map.set(key, snap);
    }
    if (map.has("hive")) this.hud.markInspectable(team);
  }

  /** Показать программу улья `h` (клик по улью на поле или по его карточке). */
  inspectHive(h) {
    if (!this._snap(h, "hive")) return false;
    this.unfollow();
    this.followHive = h;
    this._showFollow();
    return true;
  }

  _snap(team, key) {
    return this.debug.get(team)?.get(String(key)) || null;
  }

  /** Карточка того, за кем следим, и сообщение редактору, какая строка программы выполняется. */
  _showFollow() {
    let team, key, info;
    if (this.followHive != null) {
      [team, key, info] = [this.followHive, "hive", { type: "hive", hive: this.followHive }];
    } else {
      [team, key] = [this.followTeam, this.followUid];
      info = this.agents.info.get(this.followUid);
      if (info) this._lastInfo = info;
      else if (this._lastInfo && this._snap(team, key)) info = { ...this._lastInfo, inHive: true, cargo: 0 };
    }
    const snap = this._snap(team, key);
    const shown = snap ? !!this._inspect({ team, line: snap.line ?? snap.error?.line ?? null }) : this._inspect(null);
    this.hud.showFollow(info, this.followUid, snap ? { snap, blockShown: shown } : null);
  }

  /** Сообщить редактору, что подсветить; вернуть, подсветил ли он блок. */
  _inspect(target) {
    const id = target ? `${target.team}:${target.line}` : "";
    if (id !== this._inspected) {
      this._inspected = id;
      this._inspectShown = this.onInspect ? this.onInspect(target) : false;
    }
    return target ? this._inspectShown : false;
  }

  onEvents(events) {
    this.hud.onEvents(events);
    for (const e of events) {
      if (e.type === "death") this.lost.set(e.bee, `погиб(ла): ${e.cause === "spider" ? "паук" : "кончилась энергия"}`);
      if (e.type === "delivery") this.lost.set(e.bee, "вернулась в улей с нектаром");
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
    // Точный клик по улью важнее пчёл, которые вьются вокруг него.
    if (this._pickHive(x, y, HIVE_EXACT_PX)) return true;
    const uid = this.agents.pick(this.stage, x, y);
    if (uid == null) return this._pickHive(x, y, HIVE_PICK_PX);
    this.followHive = null;
    this.followUid = uid;
    const team = this.followTeam = this.agents.info.get(uid)?.hive ?? null;
    this._lastInfo = null;
    this._missing = 0;
    this.stage.follow((out) => {
      if (this.agents.positionOf(uid, out)) {
        this._missing = 0;
        return true;
      }
      // Пчела с программой под отладчиком жива, но внутри улья: камера ждёт её у улья.
      if (this._snap(team, uid) && this.world.hivePos[team]) {
        out.copy(this.world.hivePos[team]);
        return true;
      }
      return ++this._missing < 20; // пара кадров без цели — не повод отпускать
    });
    this._showFollow();
    return true;
  }

  /** Клик по улью: карточка программы улья (только если отладчик прислал её снимок). */
  _pickHive(x, y, radiusPx) {
    const scr = { x: 0, y: 0 };
    let best = null;
    let bestD = radiusPx;
    this.world.hivePos.forEach((p, i) => {
      if (!this._snap(i, "hive") || !this.stage.project(p, scr)) return;
      const d = Math.hypot(scr.x - x, scr.y - y);
      if (d < bestD) [best, bestD] = [i, d];
    });
    return best != null && this.inspectHive(best);
  }

  unfollow() {
    this.followUid = null;
    this.followHive = null;
    this.stage.unfollow();
    this.hud.showFollow(null);
    this._inspect(null);
  }

  _followLost() {
    const uid = this.followUid;
    const why = this.lost.get(uid) || "залетела в улей или исчезла";
    this.hud.feed(this._lastTime || 0, `👁 Пчела #${uid}: ${why}`);
    this.followUid = null;
    this.hud.showFollow(null);
    this._inspect(null);
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
