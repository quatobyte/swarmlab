// Обучение (M11, DECISIONS №100): экран кампании и миссия в редакторе.
//
// Ядро не знает, чему учит кампания: миссии, их цели, подсказки и тексты даёт модуль
// (`missions` в registry.js). Модуль кампании отдаёт:
//   CAMPAIGN {title, intro, script}           — название, вступление, файл программы игрока;
//   MISSIONS [{id, title, brief[], fresh, goal}] — по порядку прохождения;
//   starterWorkspace()                         — блоки новой программы игрока;
//   matchRequest(mission, {script, scripts})   — тело POST /api/matches;
//   createTracker(mission, header, code)       — судья матча:
//       update(frame) → {progress, hints[], result?};  finish(score, stopped) → result.
//   result = {win, title, text, stats}.
// Ядро хранит прогресс в браузере, показывает список, панель миссии, подсказки и итог.

import { DEFAULT_MODULE, MODULES } from "../../modules/registry.js";

const $ = (id) => document.getElementById(id);
const STORE = "swarmlab.tutorial";

/** Модуль кампании или `null`, если у модуля нет обучения. */
export async function loadCampaign() {
  const load = DEFAULT_MODULE ? MODULES[DEFAULT_MODULE].missions : null;
  return load ? load() : null;
}

/** Прогресс кампании в браузере: `{passed: {id: {at, stats}}}` (DECISIONS №100). */
export class Progress {
  constructor(storage = globalThis.localStorage) {
    this.storage = storage;
    this.data = { passed: {} };
    try {
      const raw = JSON.parse(this.storage?.getItem(STORE) || "null");
      if (raw && typeof raw.passed === "object" && raw.passed) this.data.passed = raw.passed;
    } catch {
      /* хранилище недоступно — прогресс начнётся заново */
    }
  }

  passed(id) {
    return Object.prototype.hasOwnProperty.call(this.data.passed, String(id));
  }

  /** Миссия открыта: первая или предыдущая пройдена. */
  open(missions, i) {
    return i === 0 || this.passed(missions[i - 1].id);
  }

  pass(id, stats = "") {
    this.data.passed[String(id)] = { at: new Date().toISOString(), stats };
    try {
      this.storage?.setItem(STORE, JSON.stringify(this.data));
    } catch {
      /* не запомним */
    }
  }
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** Экран кампании поверх страницы: список миссий с отметками. */
export class CampaignScreen {
  /** handlers: {play(i), back()} */
  constructor(handlers) {
    this.h = handlers;
    this.root = $("tutorial");
    $("tutorial-back").onclick = () => this.h.back();
  }

  show(campaign, progress) {
    const { CAMPAIGN, MISSIONS } = campaign;
    $("tutorial-title").textContent = CAMPAIGN.title;
    $("tutorial-intro").textContent = CAMPAIGN.intro;
    const list = $("tutorial-list");
    list.innerHTML = "";
    MISSIONS.forEach((m, i) => {
      const open = progress.open(MISSIONS, i);
      const done = progress.passed(m.id);
      const row = el("div", `mission-row${done ? " done" : ""}${open ? "" : " locked"}`);
      row.append(el("span", "mission-num", done ? "✓" : String(i + 1)));
      const body = el("div", "mission-text");
      body.append(el("div", "name", m.title), el("div", "muted small", open ? m.goal : "Откроется, когда пройдена предыдущая миссия"));
      row.append(body);
      const b = el("button", `btn${open && !done ? " primary" : ""}`, done ? "Переиграть" : "Играть");
      b.disabled = !open;
      b.onclick = () => this.h.play(i);
      row.append(b);
      list.append(row);
    });
    this.root.hidden = false;
  }

  hide() {
    this.root.hidden = true;
  }
}

/**
 * Миссия в редакторе: панель с брифингом и целью, судья матча, подсказки и итог.
 * Редактор зовёт `request(script, scripts)` при запуске и `attach(source, code)` после него.
 */
export class MissionRun {
  /** handlers: {notify(text), result(result), stop()} */
  constructor(campaign, index, handlers) {
    this.campaign = campaign;
    this.index = index;
    this.mission = campaign.MISSIONS[index];
    this.h = handlers;
    this.tracker = null;
    this.decided = false;
    this.render();
  }

  get script() {
    return this.campaign.CAMPAIGN.script;
  }

  request(script, scripts) {
    return this.campaign.matchRequest(this.mission, { script, scripts });
  }

  render() {
    const m = this.mission;
    $("mission-title").textContent = `Миссия ${this.index + 1}. ${m.title}`;
    const brief = $("mission-brief");
    brief.innerHTML = "";
    for (const p of m.brief) brief.append(el("p", "", p));
    if (m.fresh) brief.append(el("p", "mission-fresh", m.fresh));
    $("mission-goal").textContent = `Цель: ${m.goal}`;
    $("mission-progress").textContent = "";
    $("mission-hints").innerHTML = "";
  }

  /** Новый матч миссии: судья с нуля. */
  attach(source, code) {
    this.decided = false;
    this.tracker = null;
    $("mission-progress").textContent = "";
    $("mission-hints").innerHTML = "";
    const onHeader = (header) => {
      this.tracker = this.campaign.createTracker(this.mission, header, code);
    };
    if (source.header) onHeader(source.header);
    else source.on("header", onHeader);
    source.on("frame", (frame) => this._onFrame(frame));
    source.on("footer", (footer) => this._onFooter(footer, source));
  }

  _onFrame(frame) {
    if (!this.tracker || this.decided) return;
    const r = this.tracker.update(frame);
    if (r.progress) $("mission-progress").textContent = r.progress;
    for (const text of r.hints || []) this._hint(frame.time, text);
    if (r.result) this._decide(r.result, true);
  }

  _onFooter(footer, source) {
    if (this.decided || !this.tracker) return;
    const stopped = source.status?.state === "stopped";
    this._decide(this.tracker.finish(footer.score, stopped), false);
  }

  _hint(time, text) {
    const item = el("li", "", text);
    const t = el("span", "t", `${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, "0")}`);
    item.prepend(t);
    $("mission-hints").prepend(item);
    this.h.notify(text);
  }

  _decide(result, early) {
    this.decided = true;
    if (early) this.h.stop(); // цель решена до конца времени — матч больше не нужен
    this.h.result(result, this);
  }
}
