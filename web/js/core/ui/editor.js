// Редактор кода в браузере (M5): CodeMirror 5 слева, вьюер матча справа, внизу — панель
// матча и логи ульев. Сервер хранит скрипты в examples/bees/ и проверяет синтаксис (ast.parse).
// Часть, которая знает модуль (подсказки, форма матча), — js/modules/<модуль>/editor.js.

import { api } from "../api.js";
import { renderMarkdown } from "./markdown.js";

const $ = (id) => document.getElementById(id);
const CM = window.CodeMirror;

const MODULE_EDITORS = {
  bees: () => import("../../modules/bees/editor.js"),
};
const DEFAULT_FILE = "my_bees.py";
const TEMPLATE_FILE = "template.py";
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,63}\.py$/;
const MAX_LOG_LINES = 5000;
const TEAM_COLORS = ["#f5b700", "#3a86ff", "#e63946"];

function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function baseName(path) {
  return String(path).split(/[\\/]/).pop();
}

export class Editor {
  /** handlers: {start(body) → Promise, stop(), exit()} */
  constructor(handlers) {
    this.h = handlers;
    this.cm = null;
    this.mod = null;
    this.panel = null;
    this.file = null; // {name, readonly}
    this.savedText = "";
    this.scripts = [];
    this.logs = [];
    this.logFilter = "all";
    this.teams = new Map(); // team → {name, warn, err}
    this.runErrors = []; // ошибки выполнения из логов: {file, line, message}
    this.pendingFrame = new Map(); // team → {file, line} последней строки File "…" трассировки
    this.active = false;
    this.running = false;
    this._ready = null;
  }

  // ------------------------------------------------------------ вход и выход

  async open() {
    this.active = true;
    document.body.classList.add("editing");
    for (const id of ["editor", "dock", "ed-split"]) $(id).hidden = false;
    await (this._ready ||= this._init());
    this.cm.refresh();
    this.cm.focus();
  }

  close() {
    this.active = false;
    document.body.classList.remove("editing");
    for (const id of ["editor", "dock", "ed-split", "view-empty"]) $(id).hidden = true;
  }

  get dirty() {
    return this.cm !== null && this.file !== null && this.cm.getValue() !== this.savedText;
  }

  /** Вьюер пуст (матча нет) — подсказка в правой колонке. */
  setEmpty(empty) {
    $("view-empty").hidden = !(empty && this.active);
  }

  async _init() {
    const load = MODULE_EDITORS.bees;
    const [mod, profiles] = await Promise.all([load(), api.profiles()]);
    this.mod = mod;
    this.cm = CM($("ed-code"), {
      mode: { name: "python", version: 3 },
      theme: "material-darker",
      lineNumbers: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      matchBrackets: true,
      autoCloseBrackets: true,
      styleActiveLine: true,
      gutters: ["CodeMirror-lint-markers", "CodeMirror-linenumbers"],
      lint: { getAnnotations: (text, cb) => this._lint(text, cb), async: true, delay: 400 },
      extraKeys: {
        "Ctrl-S": () => this.save(),
        "Cmd-S": () => this.save(),
        "Ctrl-Space": (cm) => cm.showHint({ hint: mod.hint, completeSingle: false }),
        "Ctrl-/": "toggleComment",
        "Ctrl-Enter": () => this.start(),
        Tab: (cm) => (cm.somethingSelected() ? cm.indentSelection("add") : cm.replaceSelection("    ", "end")),
        "Shift-Tab": (cm) => cm.indentSelection("subtract"),
      },
    });
    this.cm.on("inputRead", (cm, change) => {
      if (change.text.length === 1 && change.text[0] === ".") {
        cm.showHint({ hint: mod.hint, completeSingle: false });
      }
    });
    this.cm.on("changes", () => this._updateStatus());

    this.panel = new mod.MatchPanel($("match-form"), { profiles });
    $("ed-file").onchange = () => this._switchFile($("ed-file").value);
    $("ed-save").onclick = () => this.save();
    $("ed-save-as").onclick = () => this.saveAs();
    $("ed-menu").onclick = () => this.h.exit();
    $("ed-help").onclick = () => this.showHelp();
    $("help").onclick = (e) => {
      if (e.target.id === "help" || e.target.classList.contains("close")) $("help").hidden = true;
    };
    $("match-start").onclick = () => this.start();
    $("match-stop").onclick = () => this.h.stop();
    $("match-error").onclick = () => this._jumpToError();
    $("ed-status").onclick = () => this._jumpToError();
    window.addEventListener("beforeunload", (e) => {
      if (this.active && this.dirty) e.preventDefault();
    });
    this._setupSplitters();
    this._renderLogTabs();
    this._renderLogs();

    await this._loadScripts();
    if (!this.scripts.some((s) => s.name === DEFAULT_FILE)) {
      // Первый вход: свой файл из шаблона.
      const tpl = await api.script(TEMPLATE_FILE);
      await api.saveScript(DEFAULT_FILE, tpl.text);
      await this._loadScripts();
    }
    let last = null;
    try {
      last = localStorage.getItem("swarmlab.editor.file");
    } catch {
      last = null;
    }
    await this.openFile(this.scripts.some((s) => s.name === last) ? last : DEFAULT_FILE);
  }

  // ------------------------------------------------------------ файлы

  async _loadScripts() {
    this.scripts = await api.scripts();
    const sel = $("ed-file");
    sel.innerHTML = "";
    const own = this.scripts.filter((s) => !s.readonly);
    const ref = this.scripts.filter((s) => s.readonly);
    for (const [title, group] of [["Мои скрипты", own], ["Примеры (только чтение)", ref]]) {
      if (!group.length) continue;
      const og = document.createElement("optgroup");
      og.label = title;
      for (const s of group) {
        const opt = document.createElement("option");
        opt.value = s.name;
        opt.textContent = s.readonly ? `${s.name} 🔒` : s.name;
        og.appendChild(opt);
      }
      sel.appendChild(og);
    }
    if (this.file) sel.value = this.file.name;
    this.panel?.setScripts(this.scripts, this.file?.name ?? DEFAULT_FILE);
  }

  async _switchFile(name) {
    if (this.file && name !== this.file.name && this.dirty
        && !confirm(`В ${this.file.name} есть несохранённые правки. Открыть ${name} без сохранения?`)) {
      $("ed-file").value = this.file.name;
      return;
    }
    await this.openFile(name);
  }

  async openFile(name) {
    const data = await api.script(name);
    this.file = { name: data.name, readonly: data.readonly };
    this.savedText = data.text;
    this.cm.setValue(data.text);
    this.cm.clearHistory();
    this.cm.setOption("readOnly", false);
    $("ed-file").value = name;
    try {
      localStorage.setItem("swarmlab.editor.file", name);
    } catch {
      /* не запомним */
    }
    this.panel.setScripts(this.scripts, name);
    this._updateStatus();
    this.cm.performLint();
  }

  /** Сохранить; справочный файл — через «Сохранить как». `true` — сохранено. */
  async save() {
    if (!this.file) return false;
    if (this.file.readonly) return this.saveAs();
    const text = this.cm.getValue();
    try {
      const res = await api.saveScript(this.file.name, text);
      this.savedText = text;
      this._syntax = res.errors;
      this._updateStatus();
      return true;
    } catch (e) {
      this._status(`Не сохранено: ${e.message}`, "bad");
      return false;
    }
  }

  async saveAs() {
    const suggestion = this.file?.readonly ? this.file.name.replace(/^example_|^template/, "my_") : this.file?.name;
    let name = prompt("Имя файла (латиница, цифры и _, в конце .py):", suggestion || DEFAULT_FILE);
    if (name === null) return false;
    name = name.trim();
    if (!name.endsWith(".py")) name += ".py";
    if (!NAME_RE.test(name)) {
      alert("Имя: латинские буквы, цифры и _, начинается с буквы, в конце .py — например, my_bees2.py");
      return false;
    }
    const existing = this.scripts.find((s) => s.name === name);
    if (existing?.readonly) {
      alert(`${name} — справочный файл, выберите другое имя`);
      return false;
    }
    if (existing && existing.name !== this.file?.name && !confirm(`${name} уже есть. Перезаписать?`)) return false;
    const text = this.cm.getValue();
    try {
      await api.saveScript(name, text);
    } catch (e) {
      alert(`Не сохранено: ${e.message}`);
      return false;
    }
    await this._loadScripts();
    await this.openFile(name);
    return true;
  }

  // ------------------------------------------------------------ статус и ошибки

  _status(text, cls = "") {
    const el = $("ed-status");
    el.textContent = text;
    el.className = `ed-status ${cls}`;
  }

  _updateStatus() {
    if (!this.file) return;
    const err = this._syntax?.[0];
    if (err) this._status(`✖ строка ${err.line}: ${err.message}`, "bad");
    else if (this.file.readonly) this._status("🔒 пример — «Сохранить как», чтобы менять", "");
    else if (this.dirty) this._status("● есть несохранённые правки", "dirty");
    else this._status("✓ сохранено, синтаксис в порядке", "ok");
  }

  async _lint(text, cb) {
    let errors = [];
    try {
      errors = (await api.checkScript(text)).errors;
    } catch {
      errors = [];
    }
    this._syntax = errors;
    this._updateStatus();
    const out = errors.map((e) => ({
      from: CM.Pos(e.line - 1, Math.max(0, e.col - 1)),
      to: CM.Pos(e.end_line - 1, Math.max(e.col, e.end_col - 1)),
      message: e.message,
      severity: "error",
    }));
    for (const r of this.runErrors) {
      if (r.file !== this.file?.name) continue;
      const line = r.line - 1;
      if (line < 0 || line >= this.cm.lineCount()) continue;
      out.push({ from: CM.Pos(line, 0), to: CM.Pos(line, this.cm.getLine(line).length), severity: "warning",
        message: `Ошибка во время матча (${r.team}): ${r.message}` });
    }
    cb(out);
  }

  /** Перейти к строке (и подсветить её). */
  goto(line, col = 1) {
    if (!this.cm || !line) return;
    const l = Math.min(Math.max(0, line - 1), this.cm.lineCount() - 1);
    this.cm.focus();
    this.cm.setCursor({ line: l, ch: Math.max(0, col - 1) });
    this.cm.scrollIntoView({ line: l, ch: 0 }, 80);
    const h = this.cm.addLineClass(l, "background", "cm-flash");
    setTimeout(() => this.cm.removeLineClass(h, "background", "cm-flash"), 1200);
  }

  _jumpToError() {
    const err = this._syntax?.[0] || this._startError;
    if (!err) return;
    if (err.script && err.script !== this.file?.name) {
      this.openFile(err.script).then(() => this.goto(err.line, err.col));
    } else this.goto(err.line, err.col);
  }

  _showStartError(text, data) {
    this._startError = data && data.line ? data : null;
    const el = $("match-error");
    el.hidden = !text;
    el.textContent = text ? `${text}${this._startError ? " — нажмите, чтобы перейти к строке" : ""}` : "";
  }

  // ------------------------------------------------------------ матч

  async start() {
    if (!this.file) return;
    this._showStartError(null);
    if (this.dirty) {
      const ok = await this.save();
      if (!ok) return;
    }
    const body = this.panel.build();
    $("match-start").disabled = true;
    try {
      await this.h.start(body);
    } catch (e) {
      this._showStartError(`Матч не запущен: ${e.message}`, e.data);
      if (this._startError) this._jumpToError();
    } finally {
      $("match-start").disabled = false;
    }
  }

  /** Новый матч (живой источник): логи и ошибки выполнения — заново. */
  attach(source) {
    this.logs = [];
    this.teams = new Map();
    this.runErrors = [];
    this.pendingFrame = new Map();
    this.logFilter = "all";
    this._renderLogTabs();
    this._renderLogs();
    this.cm?.performLint();
    source.on("header", (h) => {
      for (const r of h.runners || []) this._team(r.team, r.name, r.script);
      this._renderLogTabs();
    });
    source.on("log", (msg) => this._onLog(msg));
    source.on("status", (st) => this.setRunning(!["finished", "stopped", "error"].includes(st.state)));
    source.on("close", () => this.setRunning(false));
  }

  setRunning(running) {
    this.running = running;
    $("match-stop").disabled = !running;
    $("match-start").textContent = running ? "↻ Перезапустить" : "▶ Запустить";
  }

  // ------------------------------------------------------------ логи

  _team(team, name, script) {
    let t = this.teams.get(team);
    if (!t) {
      t = { team, name: name || `hive${team}`, script: script || "", warn: 0, err: 0 };
      this.teams.set(team, t);
    }
    if (script) t.script = script;
    return t;
  }

  _onLog(msg) {
    const t = this._team(msg.team, msg.name);
    const added = [];
    for (const text of msg.lines) {
      const cls = this._classify(text, t);
      const entry = { team: msg.team, time: msg.time, text, cls };
      this.logs.push(entry);
      added.push(entry);
    }
    if (this.logs.length > MAX_LOG_LINES) this.logs.splice(0, this.logs.length - MAX_LOG_LINES);
    this._renderLogTabs();
    this._appendLogs(added);
  }

  _classify(text, t) {
    const frame = /^\s*File "(.+)", line (\d+)/.exec(text);
    if (frame) {
      this.pendingFrame.set(t.team, { file: baseName(frame[1]), line: Number(frame[2]) });
      return "err";
    }
    const exc = /^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))\b(:.*)?$/.exec(text);
    if (exc) {
      t.err += 1;
      const fr = this.pendingFrame.get(t.team);
      this.pendingFrame.delete(t.team);
      if (fr && !this.runErrors.some((r) => r.file === fr.file && r.line === fr.line)) {
        this.runErrors.push({ ...fr, team: t.name, message: text });
        if (fr.file === this.file?.name) this.cm.performLint();
      }
      return "err";
    }
    if (/^(Ошибка|Скрипт .* не загрузился|Traceback)/.test(text) || /^\s{4}\S/.test(text) && this.pendingFrame.has(t.team)) {
      return "err";
    }
    if (text.startsWith("[ядро]") || text.startsWith("[сервер]")) {
      if (/пропущен|бюджет|отключ|перезапуск/.test(text)) t.warn += 1;
      return "core";
    }
    return "";
  }

  _renderLogTabs() {
    const box = $("log-tabs");
    box.innerHTML = "";
    const tab = (key, label, color, t) => {
      const b = document.createElement("button");
      b.className = `log-tab${this.logFilter === key ? " active" : ""}`;
      if (color) b.style.setProperty("--c", color);
      b.textContent = label;
      if (t?.err) b.insertAdjacentHTML("beforeend", `<span class="err" title="ошибок">✖${t.err}</span>`);
      if (t?.warn) b.insertAdjacentHTML("beforeend", `<span class="warn" title="предупреждений ядра">⚠${t.warn}</span>`);
      b.onclick = () => {
        this.logFilter = key;
        this._renderLogTabs();
        this._renderLogs();
      };
      box.appendChild(b);
    };
    tab("all", "Все ульи");
    for (const t of [...this.teams.values()].sort((a, b) => a.team - b.team)) {
      tab(String(t.team), `Улей ${t.team + 1}${t.script ? ` · ${t.script}` : ""}`, TEAM_COLORS[t.team], t);
    }
    const clear = document.createElement("button");
    clear.className = "log-tab clear";
    clear.textContent = "Очистить";
    clear.onclick = () => {
      this.logs = [];
      this._renderLogs();
    };
    box.appendChild(clear);
  }

  _visible(entry) {
    return this.logFilter === "all" || String(entry.team) === this.logFilter;
  }

  _logLine(entry) {
    const row = document.createElement("div");
    row.className = `log-line ${entry.cls}`;
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = fmtTime(entry.time);
    row.appendChild(t);
    if (this.logFilter === "all") {
      const who = document.createElement("span");
      who.className = "who";
      who.style.setProperty("--c", TEAM_COLORS[entry.team] || "#aaa");
      who.textContent = `У${entry.team + 1}`;
      row.appendChild(who);
    }
    const body = document.createElement("span");
    const frame = /^(\s*File ")(.+)(", line )(\d+)(.*)$/.exec(entry.text);
    if (frame) {
      const file = baseName(frame[2]);
      body.append(frame[1]);
      const a = document.createElement("a");
      a.textContent = `${file}, строка ${frame[4]}`;
      a.title = "Открыть в редакторе";
      a.onclick = async () => {
        if (file !== this.file?.name) {
          if (!this.scripts.some((s) => s.name === file)) return;
          if (this.dirty && !confirm(`В ${this.file.name} есть несохранённые правки. Открыть ${file}?`)) return;
          await this.openFile(file);
        }
        this.goto(Number(frame[4]));
      };
      body.append(a, frame[5]);
    } else body.textContent = entry.text;
    row.appendChild(body);
    return row;
  }

  _renderLogs() {
    const box = $("log-body");
    box.innerHTML = "";
    const shown = this.logs.filter((e) => this._visible(e));
    if (!shown.length) {
      box.innerHTML = '<div class="log-empty">Здесь появится всё, что печатают ваши пчёлы (<code>print</code>), '
        + "ошибки с номером строки и предупреждения ядра — например, о превышении бюджета времени.</div>";
      return;
    }
    const frag = document.createDocumentFragment();
    for (const e of shown.slice(-1500)) frag.appendChild(this._logLine(e));
    box.appendChild(frag);
    box.scrollTop = box.scrollHeight;
  }

  _appendLogs(entries) {
    const box = $("log-body");
    const shown = entries.filter((e) => this._visible(e));
    if (!shown.length) return;
    if (box.querySelector(".log-empty")) box.innerHTML = "";
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    for (const e of shown) box.appendChild(this._logLine(e));
    while (box.childElementCount > 2000) box.firstElementChild.remove();
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  // ------------------------------------------------------------ памятка

  async showHelp() {
    const body = $("help-body");
    $("help").hidden = false;
    if (body.dataset.loaded) return;
    body.innerHTML = '<p class="muted">Загрузка…</p>';
    try {
      const doc = await api.help();
      body.innerHTML = `<button class="btn close">Закрыть</button>${renderMarkdown(doc.text)}`;
      body.dataset.loaded = "1";
    } catch (e) {
      body.innerHTML = `<button class="btn close">Закрыть</button><p class="error">Памятка не загрузилась: ${e.message}</p>`;
    }
  }

  // ------------------------------------------------------------ раскладка

  _setupSplitters() {
    const root = document.body.style;
    try {
      const saved = JSON.parse(localStorage.getItem("swarmlab.editor.layout") || "null");
      if (saved?.ew) root.setProperty("--ew", saved.ew);
      if (saved?.dh) root.setProperty("--dh", saved.dh);
    } catch {
      /* раскладка по умолчанию */
    }
    const remember = () => {
      try {
        localStorage.setItem("swarmlab.editor.layout", JSON.stringify({
          ew: root.getPropertyValue("--ew"), dh: root.getPropertyValue("--dh"),
        }));
      } catch {
        /* не запомним */
      }
    };
    const drag = (el, onMove) => {
      el.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        const move = (ev) => onMove(ev);
        const up = () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", up);
          this.cm.refresh();
          remember();
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
      });
    };
    drag($("ed-split"), (e) => {
      const w = Math.min(Math.max(e.clientX, 320), window.innerWidth - 360);
      root.setProperty("--ew", `${w}px`);
    });
    drag($("dock-split"), (e) => {
      const h = Math.min(Math.max(window.innerHeight - e.clientY, 160), window.innerHeight - 200);
      root.setProperty("--dh", `${h}px`);
    });
  }
}
