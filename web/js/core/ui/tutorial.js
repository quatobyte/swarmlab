// Обучение (M11, DECISIONS №100, №103): экран кампании и миссия в редакторе.
//
// Ядро не знает, чему учит кампания: миссии, их цели, подсказки и тексты даёт модуль
// (`missions` в registry.js). Модуль кампании отдаёт:
//   CAMPAIGN {title, intro, script}           — название, вступление, файл программы игрока;
//   MISSIONS [{id, title, brief[], examples[{pic, title, text}], fresh, watch, goal}] — по порядку;
//   illustrate(el, pic, {scale}?)              — нарисовать картинку примера в `el` → «убрать»;
//   explainError(message)                      — совет, как исправить ошибку программы;
//   starterWorkspace()                         — блоки новой программы игрока;
//   editorSetup(mission)                       — что открыто в редакторе: {features[], blocks};
//   matchRequest(mission, {script, scripts})   — тело POST /api/matches;
//   createTracker(mission, header, code)       — судья матча:
//       update(frame) → {progress, hints[{id, text, fix}], result?};  finish(score, stopped) → result.
//   result = {win, title, text, stats}.
// Ядро хранит прогресс в браузере и показывает: список миссий, полосу миссии над полем (цель,
// прогресс, кнопки) и окна посреди экрана — брифинг по страницам с картинками-примерами,
// подсказки, ошибки программы с советом и итог (№103, №104). Пример можно оставить окошком
// над полем матча и собирать программу, подсматривая в него (№109).

import { DEFAULT_MODULE, MODULES } from "../../modules/registry.js";

const $ = (id) => document.getElementById(id);
const STORE = "swarmlab.tutorial";
const PIN_STORE = "swarmlab.tutorial.pin"; // место и размер окошка с примером: {x, y, big}

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
  };
  const run = (fn) => {
    close();
    fn?.();
  };
  const onKey = (e) => {
    if (e.key !== "Escape") return;
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
  box.querySelector(".btn.primary")?.focus();
}

/**
 * Окна по страницам: «Назад» / «Далее», на последней — кнопка `last`; после неё — `done()`.
 * `page.extra` — свои кнопки страницы `[[подпись, действие]]` (перед «Назад»).
 */
export function showPages(pages, { last = "Понятно", done = null } = {}, i = 0) {
  const { extra = [], ...page } = pages[i];
  const end = i === pages.length - 1;
  const actions = [...extra];
  if (i > 0) actions.push(["← Назад", () => showPages(pages, { last, done }, i - 1)]);
  actions.push(end ? [last, done, true] : ["Далее →", () => showPages(pages, { last, done }, i + 1), true]);
  showWindow({ draw: null, ...page, foot: pages.length > 1 ? `${i + 1} из ${pages.length}` : "", actions, esc: done || (() => {}) });
}

// ------------------------------------------------------------------ пример окошком

/**
 * Окошко с примером программы над полем матча (DECISIONS №109): не модальное — блоки собираются,
 * матч идёт; одно на миссию, листается ◀ ▶ по её примерам; двигается за заголовок, ⤢ — крупнее.
 * Место и размер помнит браузер. Окна обучения посреди экрана открываются поверх него.
 */
class PinnedExample {
  constructor() {
    this.root = null;
    this.undo = null; // убрать нарисованную картинку
    this.examples = [];
    this.i = 0;
    this.draw = null;
    this.state = { x: null, y: null, big: false };
    try {
      Object.assign(this.state, JSON.parse(localStorage.getItem(PIN_STORE) || "{}"));
    } catch {
      /* хранилище недоступно — окошко на месте по умолчанию */
    }
    window.addEventListener("resize", () => this.root && this._place());
  }

  get open() {
    return !!this.root;
  }

  /** Показать пример `i` из `examples` ([{pic, title, text}]); `draw(el, pic)` рисует картинку. */
  show(examples, i, draw) {
    this.examples = examples;
    this.draw = draw;
    this.i = Math.min(Math.max(i, 0), examples.length - 1);
    if (!this.root) this._build();
    this._render();
  }

  hide() {
    this.undo?.();
    this.undo = null;
    this.root?.remove();
    this.root = null;
  }

  _build() {
    const root = el("div", "mission-pin");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", "Пример программы");
    const head = el("div", "mp-head");
    this.title = el("span", "mp-title");
    this.count = el("span", "mp-count muted small");
    const btn = (text, title, fn) => {
      const b = el("button", "btn small", text);
      b.title = title;
      b.onclick = fn;
      return b;
    };
    this.prev = btn("◀", "Предыдущий пример", () => this.show(this.examples, this.i - 1, this.draw));
    this.next = btn("▶", "Следующий пример", () => this.show(this.examples, this.i + 1, this.draw));
    this.size = btn("⤢", "", () => {
      this.state.big = !this.state.big;
      this._save();
      this._render();
    });
    head.append(this.title, this.count, this.prev, this.next, this.size,
      btn("✕", "Убрать окошко (снова — «📌 Примеры» в полосе миссии)", () => this.hide()));
    this.frame = el("div", "mw-picture mp-picture");
    root.append(head, this.frame);
    this._drag(head);
    document.body.append(root);
    this.root = root;
  }

  _render() {
    const ex = this.examples[this.i];
    const many = this.examples.length > 1;
    this.title.textContent = `📌 ${ex.title}`;
    this.title.title = ex.text || "";
    this.count.textContent = many ? `${this.i + 1} из ${this.examples.length}` : "";
    this.prev.hidden = this.next.hidden = !many;
    this.prev.disabled = this.i === 0;
    this.next.disabled = this.i === this.examples.length - 1;
    this.root.classList.toggle("big", !!this.state.big);
    this.size.title = this.state.big ? "Мельче" : "Крупнее";
    this._place();
    // Картинка заново: её масштаб зависит от размера окошка.
    this.undo?.();
    this.undo = null;
    this.frame.innerHTML = "";
    const canvas = el("div", "mw-canvas");
    this.frame.append(canvas);
    // Крупное окошко — и блоки крупнее (на картинке-примере в задании они 0,75).
    const undo = this.draw?.(canvas, ex.pic, { scale: this.state.big ? 1 : 0.75 });
    if (typeof undo === "function") this.undo = undo;
  }

  /** На экран целиком: по умолчанию — над полем матча слева, под карточками счёта. */
  _place() {
    const r = this.root;
    const view = document.getElementById("view")?.getBoundingClientRect();
    const top = view ? view.top : 0;
    let { x, y } = this.state;
    if (x === null || y === null) {
      x = (view ? view.left : 0) + 12;
      y = top + 104;
    }
    const w = r.offsetWidth, h = r.offsetHeight;
    x = Math.min(Math.max(x, 0), Math.max(0, innerWidth - w));
    y = Math.min(Math.max(y, top), Math.max(top, innerHeight - Math.min(h, 80)));
    r.style.left = `${x}px`;
    r.style.top = `${y}px`;
  }

  _drag(head) {
    head.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button")) return;
      const r = this.root.getBoundingClientRect();
      const dx = e.clientX - r.left, dy = e.clientY - r.top;
      head.setPointerCapture(e.pointerId);
      const move = (ev) => {
        this.state.x = ev.clientX - dx;
        this.state.y = ev.clientY - dy;
        this._place();
      };
      const up = () => {
        head.removeEventListener("pointermove", move);
        head.removeEventListener("pointerup", up);
        head.removeEventListener("pointercancel", up);
        const box = this.root?.getBoundingClientRect();
        if (box) Object.assign(this.state, { x: box.left, y: box.top });
        this._save();
      };
      head.addEventListener("pointermove", move);
      head.addEventListener("pointerup", up);
      head.addEventListener("pointercancel", up);
      e.preventDefault();
    });
  }

  _save() {
    try {
      localStorage.setItem(PIN_STORE, JSON.stringify(this.state));
    } catch {
      /* не запомним */
    }
  }
}

const pinned = new PinnedExample();

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
    pinned.hide(); // окошко прежней миссии
    pinned.i = 0; // у новой миссии — с её первого примера
    const pin = $("mission-pin-open");
    pin.hidden = !this.mission.examples?.length;
    pin.onclick = () => (pinned.open ? pinned.hide() : this.pin(pinned.i));
    this._renderHints();
  }

  /** Пример `i` миссии — окошком над полем матча (DECISIONS №109). */
  pin(i = 0) {
    const examples = this.mission.examples || [];
    if (!examples.length) return;
    pinned.show(examples, Math.min(i, examples.length - 1),
      (canvas, pic, opts) => this.campaign.illustrate?.(canvas, pic, opts));
  }

  /** Миссия закрыта (выход из обучения или в обычный редактор): убрать окошко с примером. */
  close() {
    pinned.hide();
  }

  /** Брифинг по страницам: сюжет, примеры с картинками, что нового, цель (DECISIONS №103, №104). */
  brief() {
    const m = this.mission;
    const draw = (canvas, pic) => this.campaign.illustrate?.(canvas, pic);
    const pages = m.brief.map((text) => ({ kicker: this.name, title: "Задание", body: [text] }));
    (m.examples || []).forEach((ex, k) => {
      pages.push({
        kicker: this.name, title: ex.title, body: [ex.text, { picture: ex.pic }], draw,
        extra: [["📌 Оставить окошком", () => this.pin(k)]],
      });
    });
    if (m.fresh) pages.push({ kicker: this.name, title: "Что нового", body: [{ text: m.fresh, cls: "mission-fresh" }] });
    // Как следить за работой программы во время матча (инспектор, DECISIONS №105).
    if (m.watch) pages.push({ kicker: this.name, title: "Как следить за программой", body: [m.watch] });
    pages.push({
      kicker: this.name, title: "Цель миссии", body: [{ text: m.goal.replace(/^./, (c) => c.toUpperCase()), cls: "mw-goal" }],
      note: "Собери программу справа и нажми «▶ Начать миссию» вверху. Это окно можно открыть снова кнопкой «📖 Задание».",
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
  startError(message, show) {
    showWindow({
      kicker: this.name, title: "⚠ Программа не запустилась", body: this._errorBody(message),
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
