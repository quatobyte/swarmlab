// Обучение (M11, DECISIONS №100, №103): экран кампании и миссия в редакторе.
//
// Ядро не знает, чему учит кампания: миссии, их цели, подсказки и тексты даёт модуль
// (`missions` в registry.js). Модуль кампании отдаёт:
//   CAMPAIGN {title, intro, script}           — название, вступление, файл программы игрока;
//   MISSIONS [{id, title, brief[], examples[{pic, title, text}], fresh, goal}] — по порядку;
//   illustrate(el, pic)                        — нарисовать картинку примера в `el` → «убрать»;
//   explainError(message)                      — совет, как исправить ошибку программы;
//   starterWorkspace()                         — блоки новой программы игрока;
//   editorSetup(mission)                       — что открыто в редакторе: {features[], blocks};
//   matchRequest(mission, {script, scripts})   — тело POST /api/matches;
//   createTracker(mission, header, code)       — судья матча:
//       update(frame) → {progress, hints[{id, text, fix}], result?};  finish(score, stopped) → result.
//   result = {win, title, text, stats}.
// Ядро хранит прогресс в браузере и показывает: список миссий, полосу миссии над полем (цель,
// прогресс, кнопки) и окна посреди экрана — брифинг по страницам с картинками-примерами,
// подсказки, ошибки программы с советом и итог (№103, №104).

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
  constructor(storage) {
    this.data = { passed: {} };
    try {
      this.storage = storage === undefined ? globalThis.localStorage : storage;
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
    return Number.isInteger(i) && i >= 0 && i < missions.length
      && (i === 0 || this.passed(missions[i - 1].id));
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

// ------------------------------------------------------------------ окно посреди экрана

let windowClose = null; // закрыть открытое окно обучения (оно одно)

/** Закрыть окно обучения, если оно открыто (без действий его кнопок). */
export function closeWindow() {
  windowClose?.();
}

/**
 * Окно посреди экрана (DECISIONS №103): `{kicker, title, body[], note, foot, actions, esc, draw}`.
 * body — абзацы: строка, `{text, cls}` или картинка `{picture}` — её рисует `draw(el, picture)`
 * (возвращает «убрать картинку»); actions — `[[подпись, действие, главная?]]`, действие
 * выполняется после закрытия окна; esc — действие по Esc (без него Esc окно не закрывает).
 * Новое окно заменяет прежнее.
 */
export function showWindow({ kicker = "", title = "", body = [], note = "", foot = "", actions = [], esc = null, draw = null }) {
  closeWindow();
  const back = el("div", "modal-back mission-window");
  const box = el("div", "modal");
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-modal", "true");
  box.setAttribute("aria-label", title || kicker);
  const previousFocus = document.activeElement;
  if (kicker) box.append(el("div", "mw-kicker", kicker));
  if (title) box.append(el("h3", "", title));
  const text = el("div", "mw-body");
  const pictures = []; // [элемент, данные] — рисуются, когда окно уже в документе
  for (const p of body) {
    if (typeof p === "string") text.append(el("p", "", p));
    else if (p.picture !== undefined) {
      const frame = el("div", "mw-picture");
      const canvas = el("div", "mw-canvas");
      frame.append(canvas);
      text.append(frame);
      pictures.push([canvas, p.picture]);
    } else text.append(el("p", p.cls || "", p.text));
  }
  box.append(text);
  const cleanup = [];
  if (note) box.append(el("p", "mw-note", note));
  const row = el("div", "modal-actions");
  if (foot) row.append(el("span", "mw-foot muted small", foot));
  const close = () => {
    for (const undo of cleanup) undo();
    back.remove();
    window.removeEventListener("keydown", onKey, true);
    if (windowClose === close) windowClose = null;
    if (previousFocus?.isConnected) previousFocus.focus();
  };
  const run = (fn) => {
    close();
    fn?.();
  };
  const onKey = (e) => {
    if (e.key === "Tab") {
      const buttons = [...box.querySelectorAll("button")];
      const first = buttons[0], last = buttons.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      return;
    }
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    if (esc) run(esc);
  };
  for (const [label, fn, primary] of actions) {
    const b = el("button", `btn${primary ? " primary" : ""}`, label);
    b.onclick = () => run(fn);
    row.append(b);
  }
  box.append(row);
  back.append(box);
  window.addEventListener("keydown", onKey, true);
  document.body.append(back);
  windowClose = close;
  for (const [canvas, picture] of pictures) {
    const undo = draw?.(canvas, picture);
    if (typeof undo === "function") cleanup.push(undo);
    else canvas.parentElement.remove(); // картинку нарисовать нечем — страница остаётся с текстом
  }
  (box.querySelector(".btn.primary") || box.querySelector(".btn"))?.focus();
}

/** Окна по страницам: «Назад» / «Далее», на последней — кнопка `last`; после неё — `done()`. */
export function showPages(pages, { last = "Понятно", done = null } = {}, i = 0) {
  const page = pages[i];
  const end = i === pages.length - 1;
  const actions = [];
  if (i > 0) actions.push(["← Назад", () => showPages(pages, { last, done }, i - 1)]);
  actions.push(end ? [last, done, true] : ["Далее →", () => showPages(pages, { last, done }, i + 1), true]);
  showWindow({ draw: null, ...page, foot: pages.length > 1 ? `${i + 1} из ${pages.length}` : "", actions, esc: done || (() => {}) });
}

const clock = (time) => `${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, "0")}`;

/**
 * Миссия в редакторе: полоса миссии над полем, окна брифинга, подсказок и итога, судья матча.
 * Редактор зовёт `request(script, scripts)` при запуске и `attach(source, code)` после него.
 */
export class MissionRun {
  /** handlers: {notify(text), result(result, run), stop(), pause(), resume()} */
  constructor(campaign, index, handlers) {
    this.campaign = campaign;
    this.index = index;
    this.mission = campaign.MISSIONS[index];
    this.setup = campaign.editorSetup?.(this.mission) || { features: null, blocks: null };
    this.h = handlers;
    this.tracker = null;
    this.decided = false;
    this.hints = []; // подсказки этого матча: {time, text}
    this.queue = []; // важные подсказки, которые ждут своего окна
    this.asking = false;
    this.erred = false; // об ошибке программы в этом матче уже сказано
    this.render();
  }

  get script() {
    return this.campaign.CAMPAIGN.script;
  }

  get name() {
    return `Миссия ${this.index + 1}. ${this.mission.title}`;
  }

  request(script, scripts) {
    return this.campaign.matchRequest(this.mission, { script, scripts });
  }

  render() {
    $("mission-title").textContent = this.name;
    $("mission-goal").textContent = `Цель: ${this.mission.goal}`;
    $("mission-progress").textContent = "";
    $("mission-brief-open").onclick = () => this.brief();
    $("mission-hints-open").onclick = () => this.showHints();
    this._renderHints();
  }

  /** Брифинг по страницам: сюжет, примеры с картинками, что нового, цель (DECISIONS №103, №104). */
  brief() {
    const m = this.mission;
    const draw = (canvas, pic) => this.campaign.illustrate?.(canvas, pic);
    const pages = m.brief.map((text) => ({ kicker: this.name, title: "Задание", body: [text] }));
    for (const ex of m.examples || []) {
      pages.push({ kicker: this.name, title: ex.title, body: [ex.text, { picture: ex.pic }], draw });
    }
    if (m.fresh) pages.push({ kicker: this.name, title: "Что нового", body: [{ text: m.fresh, cls: "mission-fresh" }] });
    pages.push({
      kicker: this.name, title: "Цель миссии", body: [{ text: m.goal.replace(/^./, (c) => c.toUpperCase()), cls: "mw-goal" }],
      note: "Собери программу в редакторе и нажми «▶ Начать миссию» вверху. Это окно можно открыть снова кнопкой «📖 Задание».",
    });
    showPages(pages, { last: "К программе" });
  }

  /** Подсказки этого матча — окном. */
  showHints() {
    const body = this.hints.length
      ? this.hints.map((h) => `${clock(h.time)} · ${h.text}`)
      : ["Подсказок пока нет: они появляются по ходу матча."];
    showWindow({ kicker: this.name, title: "💡 Подсказки этого матча", body, actions: [["Закрыть", null, true]], esc: () => {} });
  }

  _renderHints() {
    const b = $("mission-hints-open");
    b.hidden = this.hints.length === 0;
    b.textContent = `💡 Подсказки (${this.hints.length})`;
  }

  /** Новый матч миссии: судья с нуля. */
  attach(source, code) {
    this.source = source;
    closeWindow();
    this.decided = false;
    this.tracker = null;
    this.hints = [];
    this.queue = [];
    this.asking = false;
    this.erred = false;
    $("mission-progress").textContent = "";
    this._renderHints();
    const onHeader = (header) => {
      if (this.source !== source || this.decided) return;
      this.tracker = this.campaign.createTracker(this.mission, header, code);
    };
    if (source.header) onHeader(source.header);
    else source.on("header", onHeader);
    const current = () => this.source === source && !this.decided;
    source.on("frame", (frame) => { if (current()) this._onFrame(frame); });
    source.on("footer", (footer) => { if (current()) this._onFooter(footer, source); });
    source.on("status", (status) => {
      if (current() && status.state === "error") this._interrupted(status.error || "Ошибка сервера");
    });
    source.on("close", () => {
      if (current() && !source.footer) this._interrupted("Связь с сервером потеряна. Программа сохранена; можно повторить запуск.");
    });
  }

  /** Старый источник больше не влияет на новую попытку или другой экран. */
  dispose() {
    this.decided = true;
    this.source = null;
    this.queue = [];
  }

  _interrupted(message) {
    this.dispose();
    this.startError(message, null, { title: "⚠ Матч прерван", advice: false });
  }

  _onFrame(frame) {
    if (!this.tracker || this.decided) return;
    const r = this.tracker.update(frame);
    if (r.progress) $("mission-progress").textContent = r.progress;
    for (const hint of r.hints || []) this._hint(frame.time, hint);
    if (r.result) this._decide(r.result, true);
  }

  _onFooter(footer, source) {
    if (this.decided || !this.tracker) return;
    const stopped = source.status?.state === "stopped";
    this._decide(this.tracker.finish(footer.score, stopped), false);
  }

  /** Важная подсказка (`fix`) — окно, матч ждёт; остальные — строка в ленте событий на поле. */
  _hint(time, hint) {
    this.hints.push({ time, text: hint.text });
    this._renderHints();
    if (!hint.fix) {
      this.h.notify(hint.text);
      return;
    }
    this.queue.push(hint.text);
    this._ask();
  }

  /**
   * Ошибка во время матча в программе игрока (редактор): окно с паузой, как у важной подсказки,
   * с советом кампании, как исправить (DECISIONS №104). Одна на матч. `show` — показать место.
   */
  runError(message, show) {
    if (this.decided || this.erred) return;
    this.erred = true;
    this.queue.push({ error: message, show });
    this._ask();
  }

  /** Программа не запустилась (ошибка в блоках, отказ сервера) — окно с советом. */
  startError(message, show, { title = "⚠ Программа не запустилась", advice = true } = {}) {
    showWindow({
      kicker: this.name, title,
      body: advice ? this._errorBody(message) : [{ text: message, cls: "mw-error" }],
      actions: [show ? ["Показать блок", show, true] : ["Понятно", null, true]], esc: () => {},
    });
  }

  _errorBody(message) {
    const advice = this.campaign.explainError?.(message) || "";
    return [{ text: message, cls: "mw-error" }, ...(advice ? [{ text: advice }] : [])];
  }

  _ask() {
    if (this.asking || this.decided || !this.queue.length) return;
    this.asking = true;
    this.h.pause();
    const item = this.queue.shift();
    const error = typeof item === "object";
    const fix = () => {
      // Игрок идёт править программу: матч больше не нужен, окна итога не будет.
      this.asking = false;
      this.queue = [];
      this.decided = true;
      this.h.stop();
      item.show?.();
    };
    const go = () => {
      this.asking = false;
      if (this.queue.length) this._ask();
      else this.h.resume();
    };
    showWindow({
      kicker: this.name, title: error ? "⚠ Ошибка в программе" : "💡 Подсказка",
      body: error ? this._errorBody(item.error) : [item], note: "Матч на паузе.",
      actions: [["Продолжить матч", go], [error && item.show ? "Показать блок" : "Поправить программу", fix, true]], esc: go,
    });
  }

  _decide(result, early) {
    this.decided = true;
    this.queue = [];
    if (early) this.h.stop(); // цель решена до конца времени — матч больше не нужен
    this.h.result(result, this);
  }
}
