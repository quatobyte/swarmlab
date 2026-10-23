// Стартовое окно: матч из ульев с примерами и проектами (M7c), проекты .swarm, серии матчей,
// матч из YAML-файла, идущие матчи, реплеи с сервера и с диска.

import { api } from "../api.js";
import { parseProject, ProjectError } from "../project.js";
import { confirmForeignCode } from "../trust.js";
import { ask, askSeries } from "./dialog.js";
import { renderSeriesList } from "./series.js";

const $ = (id) => document.getElementById(id);

/** Часть меню, которая знает модуль (форма матча), — js/modules/<модуль>/editor.js. */
const MODULE_FORMS = {
  bees: () => import("../../modules/bees/editor.js"),
};

function fmtSize(bytes) {
  return bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1e3))} КБ`;
}

function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const STATE_RU = {
  starting: "запускается", running: "идёт", paused: "пауза",
  finished: "закончен", stopped: "остановлен", error: "ошибка",
};

/** Спросить про чужой код проектов (один раз на содержимое, DECISIONS №65). */
export async function trustProjects(names, okLabel = "Запустить") {
  if (!names.length) return true;
  const codes = [];
  for (const name of names) codes.push((await api.project(name)).code);
  return confirmForeignCode(codes, (text) => ask(text, { title: "Чужой код", ok: okLabel, cancel: "Отмена" }));
}

export class Lobby {
  /**
   * handlers: {startMatch(body), openLive(id), openReplay(id, name), openFile(file),
   *            startSeries(body), openSeries(id), openInEditor(scriptName)}
   */
  constructor(handlers) {
    this.h = handlers;
    this.el = $("lobby");
    this.configs = [];
    this.projects = [];
    this.panel = null;
    $("lobby-start").addEventListener("click", () => this._start());
    $("lobby-match").addEventListener("change", () => this._describe());
    $("lobby-watch").addEventListener("click", () => this._watch());
    $("lobby-series").addEventListener("click", () => this._series());
    $("lobby-file").addEventListener("change", (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (f) this.h.openFile(f);
    });
    $("lobby-project-file").addEventListener("change", (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (f) this.uploadProject(f);
    });
  }

  async show() {
    this.el.hidden = false;
    this.error(null);
    await Promise.all([this._loadConfigs(), this._loadLive(), this._loadReplays(), this._loadSeries(),
      this._initForm().then(() => this._loadProjects())]);
  }

  hide() {
    this.el.hidden = true;
  }

  get visible() {
    return !this.el.hidden;
  }

  error(text) {
    const el = $("lobby-error");
    el.hidden = !text;
    el.textContent = text || "";
  }

  _message(text, bad = false) {
    const el = $("lobby-project-msg");
    el.hidden = !text;
    el.textContent = text || "";
    el.className = `small ${bad ? "error" : "muted"}`;
  }

  // ------------------------------------------------------------ форма матча с проектами

  async _initForm() {
    if (this.panel) return;
    try {
      const [mod, profiles] = await Promise.all([MODULE_FORMS.bees(), api.profiles()]);
      this.mod = mod;
      this.panel = new mod.MatchPanel($("lobby-form"), {
        profiles, prefix: "lf", lockFirst: false, randomSeed: true, storageKey: "swarmlab.lobby.match",
      });
    } catch (e) {
      $("lobby-form").innerHTML = "";
      this.error(`Форма матча не загрузилась: ${e.message}`);
    }
  }

  async _loadProjects() {
    const box = $("lobby-projects");
    let scripts = [];
    try {
      [this.projects, scripts] = await Promise.all([api.projects(), api.scripts()]);
    } catch {
      box.innerHTML = '<p class="muted small">Список проектов недоступен.</p>';
      return;
    }
    this.panel?.setSources(this.mod.lobbySources(scripts, this.projects));
    box.innerHTML = this.projects.length ? ""
      : '<p class="muted small">Загруженных проектов нет. Проект — файл .swarm: «⬇ Экспорт проекта» в редакторе.</p>';
    for (const p of this.projects) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = '<span class="name"></span><span class="muted small"></span>';
      row.querySelector(".name").textContent = `${p.mode === "blocks" ? "🧩" : "🐍"} ${p.name}`;
      row.querySelector(".muted").textContent = `${p.mode === "blocks" ? "блоки" : "Python"} · `
        + `${String(p.created || p.uploaded).replace("T", " ").slice(0, 16)}`;
      row.title = `Загружен ${p.uploaded.replace("T", " ")}; sha256 кода ${p.sha256.slice(0, 12)}…`;
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = "Открыть в редакторе";
      btn.title = "Копия проекта станет вашим скриптом в редакторе (с блоками)";
      btn.onclick = () => this._toEditor(p.name);
      row.appendChild(btn);
      box.appendChild(row);
    }
  }

  /** Загрузить файл `.swarm` в `projects/` (кнопка или перетаскивание в окно). */
  async uploadProject(file) {
    this._message(null);
    let text;
    try {
      text = await file.text();
      parseProject(text); // понятная ошибка ещё до сервера
      const res = await api.uploadProject(text);
      this._message(res.status === "same" ? `Такой проект уже загружен: ${res.name}`
        : res.name !== res.title ? `Загружен как ${res.name}: проект ${res.title} с другим содержимым уже есть`
          : `Проект загружен: ${res.name}`);
      await this._loadProjects();
    } catch (e) {
      const why = e instanceof ProjectError ? e.message : `Не загружен: ${e.message}`;
      this._message(`${file.name}: ${why}`, true);
    }
  }

  async _toEditor(name) {
    try {
      if (!(await trustProjects([name], "Открыть"))) return;
      const res = await api.projectToEditor(name);
      await this.h.openInEditor(res.name);
    } catch (e) {
      this.error(`Не открыт: ${e.message}`);
    }
  }

  async _liveOk() {
    const live = (await api.matches()).filter((m) => ["starting", "running", "paused"].includes(m.state));
    return !live.length || confirm(`Сейчас идёт матч ${live[0].match}. Остановить его и запустить новый?`);
  }

  async _watch() {
    if (!this.panel) return;
    this.error(null);
    const btn = $("lobby-watch");
    try {
      if (!(await trustProjects(this.panel.usedProjects()))) return;
      const body = this.panel.build();
      if (!(await this._liveOk())) return;
      btn.disabled = true;
      await this.h.startMatch(body);
    } catch (e) {
      this.error(`Матч не запущен: ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  async _series() {
    if (!this.panel) return;
    this.error(null);
    try {
      if (!(await trustProjects(this.panel.usedProjects()))) return;
      const seed = this.panel.build().seed;
      const opts = await askSeries({ n: 10, seed, note: `Таблица — по улью ${this.panel.focusHive() + 1} (${this.panel.label(this.panel.focusHive())}).` });
      if (!opts) return;
      await this.h.startSeries(this.panel.seriesBody(opts));
    } catch (e) {
      this.error(`Серия не запущена: ${e.message}`);
    }
  }

  async _loadSeries() {
    const box = $("lobby-series-list");
    try {
      renderSeriesList(box, await api.seriesList(), (id) => this.h.openSeries(id));
    } catch {
      box.innerHTML = '<p class="muted small">Список серий недоступен.</p>';
    }
  }

  refreshSeries() {
    if (this.visible) this._loadSeries();
  }

  // ------------------------------------------------------------ матч из YAML, живые, реплеи

  async _loadConfigs() {
    try {
      this.configs = await api.configs();
    } catch (e) {
      this.error(`Сервер недоступен: ${e.message}`);
      return;
    }
    const sel = $("lobby-match");
    const prev = sel.value;
    sel.innerHTML = "";
    for (const c of this.configs) {
      const opt = document.createElement("option");
      opt.value = c.name;
      opt.textContent = `${c.name} — ${c.profile ?? "?"}, ${c.duration_s ?? "?"} с`;
      sel.appendChild(opt);
    }
    if (prev) sel.value = prev;
    this._describe();
  }

  _describe() {
    const c = this.configs.find((x) => x.name === $("lobby-match").value);
    $("lobby-match-desc").textContent = c ? c.description : "";
    $("lobby-seed").placeholder = c && c.seed != null ? `из файла: ${c.seed}` : "из файла";
  }

  async _loadLive() {
    let list = [];
    try {
      list = await api.matches();
    } catch {
      return;
    }
    const live = list.filter((m) => !["finished", "stopped", "error"].includes(m.state));
    $("lobby-live-section").hidden = live.length === 0;
    const box = $("lobby-live");
    box.innerHTML = "";
    for (const m of live) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="name"></span><span class="muted small"></span>`;
      row.querySelector(".name").textContent = `${m.match} · seed ${m.seed}`;
      row.querySelector(".muted").textContent =
        `${STATE_RU[m.state] || m.state}, ${fmtTime(m.time)} из ${fmtTime(m.duration_s)}`;
      const btn = document.createElement("button");
      btn.className = "btn primary";
      btn.textContent = "Смотреть";
      btn.onclick = () => this.h.openLive(m.id);
      row.appendChild(btn);
      box.appendChild(row);
    }
  }

  async _loadReplays() {
    const box = $("lobby-replays");
    let list = [];
    try {
      list = await api.replays();
    } catch {
      box.innerHTML = `<p class="muted small">Список реплеев недоступен.</p>`;
      return;
    }
    box.innerHTML = list.length ? "" : `<p class="muted small">Реплеев пока нет — запустите матч.</p>`;
    for (const r of list.slice(0, 12)) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="name"></span><span class="muted small"></span>`;
      row.querySelector(".name").textContent = r.id;
      row.querySelector(".muted").textContent = `${fmtSize(r.size)} · ${r.modified.replace("T", " ")}`;
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = "Открыть";
      btn.onclick = () => this.h.openReplay(r.id, r.name);
      row.appendChild(btn);
      box.appendChild(row);
    }
  }

  async _start() {
    const body = { match: $("lobby-match").value, speed: Number($("lobby-speed").value) };
    const seed = $("lobby-seed").value.trim();
    if (seed !== "") body.seed = Number(seed);
    try {
      if (!(await this._liveOk())) return;
      $("lobby-start").disabled = true;
      await this.h.startMatch(body);
    } catch (e) {
      this.error(e.message);
    } finally {
      $("lobby-start").disabled = false;
    }
  }
}

export { fmtTime, STATE_RU };
