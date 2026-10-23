// Редактор кода в браузере (M5): CodeMirror 5 и блоки, вьюер матча, внизу — панель
// матча и логи ульев. Сервер хранит скрипты в examples/bees/ и проверяет синтаксис (ast.parse).
// Часть, которая знает модуль (подсказки, форма матча), — js/modules/<модуль>/editor.js.
//
// Блоки (M7b, DECISIONS №50–56): у скрипта может быть файл блоков `X.blocks.json`. В режиме
// «Блоки» `.py` генерируется из блоков при каждом изменении (вкладка Python — только чтение);
// «Перейти на Python» помечает файл блоков `mode: "python"`, и дальше блоки `.py` не трогают.

//
// M7c: вьюер слева, код или блоки справа (`--ew` — ширина редактора), верхняя панель
// «Блоки | Python», отмена/повтор, имя проекта, «⬇ Экспорт проекта» / «📂 Открыть проект…»
// (файл `.swarm`, DECISIONS №63, №65), «Серия…» в панели «Матч» (таблица поверх вьюера).

import { api } from "../api.js";
import { makeProject, parseProject, projectName, projectText, PROJECT_EXT } from "../project.js";
import { confirmForeignCode } from "../trust.js";
import { ask, askSeries } from "./dialog.js";
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

/** `my_bees.py` → `my_bees.blocks.json` (файл блоков рядом со скриптом). */
function blocksName(name) {
  return name.replace(/\.py$/, ".blocks.json");
}

export class Editor {
  /** handlers: {start(body) → Promise, stop(), startSeries(body), showSeries(id), exit()} */
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
    // Блоки: режим открытого файла ("blocks" | "python"), видимая вкладка, редактор блоков.
    this.mode = "python";
    this.view = "python";
    this.blocks = null;
    this.gen = null; // последний результат генерации из блоков
    this.savedBlocks = "";
    this._regenTimer = 0;
  }

  // ------------------------------------------------------------ вход и выход

  async open() {
    this.active = true;
    document.body.classList.add("editing");
    for (const id of ["editor", "dock", "ed-split"]) $(id).hidden = false;
    await (this._ready ||= this._init());
    this.cm.refresh();
    this.blocks?.resize();
    if (this.view === "python") this.cm.focus();
  }

  close() {
    this.active = false;
    document.body.classList.remove("editing");
    for (const id of ["editor", "dock", "ed-split", "view-empty"]) $(id).hidden = true;
  }

  get dirty() {
    if (this.cm === null || this.file === null) return false;
    if (this.mode === "blocks") return JSON.stringify(this.blocks.save()) !== this.savedBlocks;
    return this.cm.getValue() !== this.savedText;
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
    $("ed-new").onclick = () => this.newBlocksScript();
    $("ed-tab-blocks").onclick = () => this.setView("blocks");
    $("ed-tab-python").onclick = () => this.setView("python");
    $("ed-to-python").onclick = () => this.toPython();
    $("ed-menu").onclick = () => this.h.exit();
    $("ed-help").onclick = () => this.showHelp();
    $("ed-undo").onclick = () => this.undo(false);
    $("ed-redo").onclick = () => this.undo(true);
    $("ed-export").onclick = () => this.exportProject();
    $("ed-open-project").onchange = (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (f) this.openProjectFile(f);
    };
    $("match-series").onclick = () => this.startSeries();
    $("match-series-table").onclick = () => this.lastSeries && this.h.showSeries(this.lastSeries);
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
      // Первый вход: свой файл — из блоков (DECISIONS №51); модуль без блоков — из шаблона.
      if (mod.BlocksEditor) await this._createBlocksScript(DEFAULT_FILE);
      else await api.saveScript(DEFAULT_FILE, (await api.script(TEMPLATE_FILE)).text);
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
        opt.textContent = `${s.name}${s.mode === "blocks" ? " 🧩" : ""}${s.readonly ? " 🔒" : ""}`;
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
    const blocks = data.blocks?.mode === "blocks" && this.mod.BlocksEditor;
    if (blocks) this._ensureBlocks();
    this.mode = blocks ? "blocks" : "python";
    this.blocksFile = data.blocks || null;
    this.cm.setValue(data.text);
    this.cm.clearHistory();
    this.cm.setOption("readOnly", this.mode === "blocks");
    if (this.mode === "blocks") {
      this.blocks.load(data.blocks.workspace);
      this.savedBlocks = JSON.stringify(this.blocks.save());
      this._regenerate();
      // Файл на диске мог устареть (генератор поменялся) — тогда он «грязный», сохранится заново.
      if (this.gen.code !== data.text) this.savedBlocks = "";
    } else {
      this.gen = null;
    }
    this._renderMode();
    this.setView(this.mode === "blocks" ? "blocks" : "python");
    $("ed-file").value = name;
    $("ed-project").textContent = projectName(name);
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
    const { text, blocks } = this._payload(this.file.name);
    try {
      const res = await api.saveScript(this.file.name, text, blocks);
      this.savedText = text;
      if (blocks) this.savedBlocks = JSON.stringify(blocks.workspace);
      this._syntax = res.errors;
      this._updateStatus();
      return true;
    } catch (e) {
      this._status(`Не сохранено: ${e.message}`, "bad");
      return false;
    }
  }

  /** Что сохранять под именем `name`: текст `.py` и (в режиме «Блоки») файл блоков. */
  _payload(name) {
    if (this.mode !== "blocks") return { text: this.cm.getValue(), blocks: null };
    const workspace = this.blocks.save();
    const gen = this.mod.generateBlocks(workspace, { file: blocksName(name) });
    return { text: gen.code, blocks: { format: 1, mode: "blocks", workspace } };
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
    const { text, blocks } = this._payload(name); // в файл, переведённый в Python, сервер блоки не пишет (409)
    try {
      await api.saveScript(name, text, blocks);
    } catch (e) {
      alert(`Не сохранено: ${e.message}`);
      return false;
    }
    await this._loadScripts();
    await this.openFile(name);
    return true;
  }

  /** Открыть скрипт по имени (например, копию проекта из меню). */
  async openScript(name) {
    await this._ready;
    await this._loadScripts();
    await this._switchFile(name);
  }

  // ------------------------------------------------------------ отмена, проект (M7c)

  /** ↶ / ↷: в режиме блоков — история Blockly, в Python — CodeMirror. */
  undo(redo) {
    if (this.mode === "blocks" && this.blocks) this.blocks.undo(redo);
    else if (this.cm && !this.cm.getOption("readOnly")) {
      if (redo) this.cm.redo();
      else this.cm.undo();
      this.cm.focus();
    }
  }

  /** Ошибки текущего кода для предупреждения при экспорте (блоки и `ast` на сервере). */
  async _problems() {
    if (this.mode === "blocks") {
      this._regenerate();
      if (this.gen.errors.length) return this.gen.errors.map((e) => e.message);
    }
    try {
      const res = await api.checkScript(this._payload(this.file.name).text);
      return res.errors.map((e) => `строка ${e.line}: ${e.message}`);
    } catch {
      return [];
    }
  }

  /** «⬇ Экспорт проекта»: скачать `<имя>.swarm` (с ошибками — после подтверждения). */
  async exportProject() {
    if (!this.file) return;
    const problems = await this._problems();
    if (problems.length) {
      const more = problems.length > 1 ? ` (и ещё ${problems.length - 1})` : "";
      const ok = await ask(`Проект с ошибками: ${problems[0]}${more}.\n\nТакой проект откроется, но матч `
        + "с ним не запустится, пока ошибки не исправлены. Всё равно экспортировать?",
      { title: "Экспорт проекта", ok: "Экспортировать" });
      if (!ok) return;
    }
    const { text, blocks } = this._payload(this.file.name);
    const project = makeProject({ name: this.file.name, mode: this.mode, code: text, blocks: blocks?.workspace });
    const url = URL.createObjectURL(new Blob([projectText(project)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name}${PROJECT_EXT}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    this._status(`⬇ ${a.download} — в папке загрузок браузера`, "ok");
  }

  /** «📂 Открыть проект…»: `.swarm` → новый свой скрипт (с блоками), после предупреждения. */
  async openProjectFile(file) {
    let project;
    try {
      project = parseProject(await file.text());
    } catch (e) {
      alert(`${file.name}: ${e.message}`);
      return;
    }
    const trusted = await confirmForeignCode([project.code],
      (text) => ask(text, { title: "Чужой код", ok: "Открыть", cancel: "Отмена" }));
    if (!trusted) return;
    if (this.dirty && !confirm(`В ${this.file.name} есть несохранённые правки. Открыть проект без сохранения?`)) return;
    await this._loadScripts();
    const taken = (n) => this.scripts.some((s) => s.name === n) || /^(example_|template\.py$)/.test(n);
    let name = `${project.name}.py`;
    if (taken(name)) {
      let k = 2;
      while (taken(`${project.name}_${k}.py`)) k += 1;
      const answer = prompt(`Скрипт ${name} уже есть. Под каким именем открыть проект?`, `${project.name}_${k}.py`);
      if (answer === null) return;
      name = answer.trim().endsWith(".py") ? answer.trim() : `${answer.trim()}.py`;
      if (!NAME_RE.test(name) || taken(name)) {
        alert(`Имя ${name} не подходит или занято: латинские буквы, цифры и _, в конце .py`);
        return;
      }
    }
    const blocks = project.mode === "blocks" ? { format: 1, mode: "blocks", workspace: project.blocks } : null;
    try {
      await api.saveScript(name, project.code, blocks);
    } catch (e) {
      alert(`Проект не открыт: ${e.message}`);
      return;
    }
    await this._loadScripts();
    await this.openFile(name);
    this._status(`📂 проект ${project.name} открыт как ${name}`, "ok");
  }

  // ------------------------------------------------------------ серия (M7c)

  async startSeries() {
    if (!this.file) return;
    this._showStartError(null);
    if (!(await this._readyToRun())) return;
    const opts = await askSeries({ n: 10, seed: this.panel.build().seed, note: `Таблица — по улью 1 (${this.file.name}).` });
    if (!opts) return;
    try {
      const info = await this.h.startSeries(this.panel.seriesBody(opts));
      this.lastSeries = info.id;
      $("match-series-table").hidden = false;
    } catch (e) {
      this._showStartError(`Серия не запущена: ${e.message}`, e.data);
      if (this._startError) this._jumpToError();
    }
  }

  onSeriesClosed(id) {
    if (id) this.lastSeries = id;
    $("match-series-table").hidden = !this.lastSeries;
  }

  // ------------------------------------------------------------ блоки (M7b)

  _ensureBlocks() {
    if (this.blocks) return;
    this.blocks = new this.mod.BlocksEditor($("ed-blocks"), { onChange: () => this._scheduleRegen() });
  }

  _scheduleRegen() {
    clearTimeout(this._regenTimer);
    this._regenTimer = setTimeout(() => this._regenerate(), 150);
  }

  /** Python из блоков → во вкладку Python (только чтение); ошибки — на блоки. */
  _regenerate() {
    if (this.mode !== "blocks" || !this.file) return;
    clearTimeout(this._regenTimer);
    this.gen = this.blocks.generate(blocksName(this.file.name));
    if (this.cm.getValue() !== this.gen.code) {
      const scroll = this.cm.getScrollInfo();
      this.cm.setValue(this.gen.code); // вызовет проверку ast на сервере (lint)
      this.cm.scrollTo(scroll.left, scroll.top);
    }
    this.blocks.showProblems(this.gen);
    this._updateStatus();
  }

  setView(view) {
    if (view === "blocks" && this.mode !== "blocks") view = "python";
    this.view = view;
    $("ed-blocks").hidden = view !== "blocks";
    $("ed-code").hidden = view !== "python";
    $("ed-tab-blocks").classList.toggle("active", view === "blocks");
    $("ed-tab-python").classList.toggle("active", view === "python");
    if (view === "blocks") this.blocks.resize();
    else this.cm.refresh();
  }

  _renderMode() {
    const blocks = this.mode === "blocks";
    const tabBlocks = $("ed-tab-blocks");
    tabBlocks.disabled = !blocks;
    tabBlocks.title = blocks ? "Собирать программу из блоков"
      : this.blocksFile ? "Скрипт переведён в Python — блоки больше не обновляют его"
        : "Этот скрипт написан на Python. Блоки — в новом скрипте («Новый…»)";
    $("ed-to-python").hidden = !blocks || this.file?.readonly;
    $("ed-code").classList.toggle("generated", blocks);
    $("ed-mode-note").textContent = blocks ? "Python собирается из блоков (только чтение)"
      : this.blocksFile ? "переведён из блоков в Python" : "";
  }

  /** Переход в Python (DECISIONS №50): предупреждение, подтверждение; блоки остаются в файле. */
  async toPython() {
    if (this.mode !== "blocks" || !this.file || this.file.readonly) return;
    const name = this.file.name;
    const ok = confirm(
      `Перейти на Python?\n\nДальше ${name} пишется только на Python. Блоки больше не будут обновлять этот файл, `
      + "и вернуться к ним для этого скрипта нельзя (они останутся в "
      + `${blocksName(name)}, но код из них больше не собирается).\n\nПродолжить?`);
    if (!ok) return;
    this._regenerate();
    const workspace = this.blocks.save();
    try {
      await api.saveScript(name, this.gen.code, { format: 1, mode: "python", workspace });
    } catch (e) {
      this._status(`Не получилось: ${e.message}`, "bad");
      return;
    }
    this.mode = "python";
    this.blocksFile = { format: 1, mode: "python", workspace };
    this.savedText = this.gen.code;
    this.gen = null;
    this.cm.setOption("readOnly", false);
    this._renderMode();
    this.setView("python");
    this.cm.focus();
    await this._loadScripts();
    this._updateStatus();
    this.cm.performLint();
  }

  async _createBlocksScript(name) {
    const workspace = this.mod.starterWorkspace();
    const gen = this.mod.generateBlocks(workspace, { file: blocksName(name) });
    await api.saveScript(name, gen.code, { format: 1, mode: "blocks", workspace });
  }

  /** Новый скрипт из блоков (режим по умолчанию для новых скриптов, DECISIONS №51). */
  async newBlocksScript() {
    if (!this.mod.BlocksEditor) return;
    if (this.dirty && !confirm(`В ${this.file.name} есть несохранённые правки. Создать новый скрипт без сохранения?`)) return;
    let name = prompt("Имя нового скрипта из блоков (латиница, цифры и _, в конце .py):", "my_blocks.py");
    if (name === null) return;
    name = name.trim();
    if (!name.endsWith(".py")) name += ".py";
    if (!NAME_RE.test(name)) {
      alert("Имя: латинские буквы, цифры и _, начинается с буквы, в конце .py — например, my_blocks.py");
      return;
    }
    const existing = this.scripts.find((s) => s.name === name);
    if (existing?.readonly) {
      alert(`${name} — справочный файл, выберите другое имя`);
      return;
    }
    if (existing && !confirm(`${name} уже есть. Заменить его новым скриптом из блоков?`)) return;
    try {
      await this._createBlocksScript(name);
    } catch (e) {
      alert(`Не создано: ${e.message}`);
      return;
    }
    await this._loadScripts();
    await this.openFile(name);
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
    const g = this.mode === "blocks" ? this.gen : null;
    if (g?.errors.length) this._status(`✖ ${g.errors[0].message}${g.errors.length > 1 ? ` (ещё ${g.errors.length - 1})` : ""}`, "bad");
    else if (err && g) this._status(`✖ ошибка Python в блоке: ${err.message}`, "bad");
    else if (err) this._status(`✖ строка ${err.line}: ${err.message}`, "bad");
    else if (g?.warnings.length) {
      this._status(`⚠ ${g.warnings[0].message}${this.dirty ? " · ● не сохранено" : ""}`, "warn");
    }
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
    const onBlocks = [];
    for (const e of errors) if (e.block) onBlocks.push({ block: e.block, message: `Python: ${e.message}` });
    for (const r of this.runErrors) {
      if (r.file !== this.file?.name) continue;
      const line = r.line - 1;
      if (line < 0 || line >= this.cm.lineCount()) continue;
      const message = `Ошибка во время матча (${r.team}): ${r.message}`;
      out.push({ from: CM.Pos(line, 0), to: CM.Pos(line, this.cm.getLine(line).length), severity: "warning", message });
      const block = this.mode === "blocks" ? this.mod.blockAtLine(text, r.line) : null;
      if (block) onBlocks.push({ block, message });
    }
    if (this.mode === "blocks" && this.gen) this.blocks.showProblems(this.gen, onBlocks);
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
    if (this.mode === "blocks") {
      const p = this.gen?.errors[0] || this._syntax?.[0] || this._startError || this.gen?.warnings[0];
      if (p?.block && this.blocks.focus(p.block)) {
        this.setView("blocks");
        return;
      }
    }
    const err = this._syntax?.[0] || this._startError;
    if (!err) return;
    if (err.script && err.script !== this.file?.name) {
      this.openFile(err.script).then(() => this.goto(err.line, err.col));
    } else this.goto(err.line, err.col);
  }

  _showStartError(text, data) {
    this._startError = data && (data.line || data.block) ? data : null;
    const el = $("match-error");
    el.hidden = !text;
    el.textContent = text ? `${text}${this._startError ? " — нажмите, чтобы перейти к строке" : ""}` : "";
  }

  // ------------------------------------------------------------ матч

  /** Перед матчем и серией: блоки без ошибок, правки сохранены. */
  async _readyToRun() {
    if (this.mode === "blocks") {
      // Проверка по порядку (DECISIONS №56): сначала блоки, потом — ast на сервере.
      this._regenerate();
      if (this.gen.errors.length) {
        this._showStartError(`В блоках есть ошибки: ${this.gen.errors[0].message}`, { block: this.gen.errors[0].block });
        this._jumpToError();
        return false;
      }
    }
    return !this.dirty || this.save();
  }

  async start() {
    if (!this.file) return;
    this._showStartError(null);
    if (!(await this._readyToRun())) return;
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
    // Вьюер слева, редактор справа: `--ew` — ширина редактора (как и до M7c, раскладка
    // из localStorage подходит без пересчёта).
    drag($("ed-split"), (e) => {
      const w = Math.min(Math.max(window.innerWidth - e.clientX, 360), window.innerWidth - 320);
      root.setProperty("--ew", `${w}px`);
      this.blocks?.resize();
    });
    drag($("dock-split"), (e) => {
      const h = Math.min(Math.max(window.innerHeight - e.clientY, 160), window.innerHeight - 200);
      root.setProperty("--dh", `${h}px`);
    });
  }
}
