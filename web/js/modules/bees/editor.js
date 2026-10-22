// Часть редактора, которая знает пчёл: подсказки по API и панель матча (M5).
// Общая часть (файлы, сохранение, логи, раскладка) — js/core/ui/editor.js.

import { API_HINTS } from "./api_hints.js";

const CLASSES = API_HINTS.classes;
const PY_KEYWORDS = [
  "False", "None", "True", "and", "as", "assert", "break", "class", "continue", "def", "del", "elif",
  "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
  "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
];
const PY_BUILTINS = [
  "abs", "all", "any", "dict", "enumerate", "float", "int", "isinstance", "len", "list", "max", "min",
  "print", "range", "round", "set", "sorted", "str", "sum", "tuple", "zip", "math", "random", "super",
];
/** Имена переменных, тип которых угадывается без аннотаций (как в шаблоне и примерах). */
const NAME_TYPES = {
  s: "Sensors", hive: "Hive", flower: "Flower", enemy: "Enemy", bee: "BeeInfo", msg: "Message",
  m: "Message", f: "Flower", e: "Enemy", b: "BeeInfo", target: "Enemy", larva: "Larva",
};
const HOUSE_BASES = new Set(["HouseBee"]);

// ------------------------------------------------------------------ типы

/** "Flower | None" → {cls: "Flower"}, "list[Flower]" → {list: "Flower"}. */
function parseType(t) {
  if (!t) return null;
  const parts = t.split("|").map((x) => x.trim()).filter((x) => x && x !== "None");
  const one = parts[0] || "";
  let m = /^(?:list|tuple|Sequence)\[\s*([A-Za-z_]\w*)/.exec(one);
  if (m && CLASSES[m[1]]) return { list: m[1] };
  m = /^([A-Za-z_]\w*)$/.exec(one);
  if (m && CLASSES[m[1]]) return { cls: m[1] };
  return null;
}

function member(cls, name) {
  return CLASSES[cls]?.members.find((x) => x.name === name);
}

/** Шаги цепочки `a.b().c[0]` → [{name, call, index}]. */
function splitChain(expr) {
  const steps = [];
  const re = /([A-Za-z_]\w*)\s*((?:\([^()]*\)|\[[^\[\]]*\])*)\s*(?:\.|$)/y;
  let pos = 0;
  while (pos < expr.length) {
    re.lastIndex = pos;
    const m = re.exec(expr);
    if (!m || m[0].length === 0) return null;
    steps.push({ name: m[1], call: m[2].includes("("), index: m[2].includes("[") });
    pos = re.lastIndex;
  }
  return steps;
}

/**
 * Контекст кода выше курсора: класс игрока (база из API), аннотации параметров текущей
 * функции, присваивания и циклы `for` — чтобы понять, что за объект стоит перед точкой.
 */
class Scope {
  constructor(textBefore) {
    this.lines = textBefore.split("\n");
    this.userBases = {};
    for (const line of this.lines) {
      const m = /^class\s+(\w+)\s*\(\s*([\w.]+)/.exec(line);
      if (m) this.userBases[m[1]] = m[2].split(".").pop();
    }
    this.selfClass = null;
    for (let i = this.lines.length - 1; i >= 0; i--) {
      const m = /^class\s+(\w+)/.exec(this.lines[i]);
      if (m) {
        this.selfClass = this.apiBase(m[1]);
        break;
      }
      if (/^\S/.test(this.lines[i]) && !/^(#|@)/.test(this.lines[i]) && i < this.lines.length - 1) break;
    }
    // Начало текущей функции: последняя строка `def` выше курсора.
    this.fnStart = 0;
    this.params = {};
    for (let i = this.lines.length - 1; i >= 0; i--) {
      const m = /^\s*def\s+\w+\s*\((.*)\)?/.exec(this.lines[i]);
      if (m) {
        this.fnStart = i;
        for (const p of m[1].split(",")) {
          const pm = /^\s*\*{0,2}(\w+)\s*:\s*([^=]+?)\s*(?:=.*)?$/.exec(p);
          if (pm) this.params[pm[1]] = pm[2];
        }
        break;
      }
    }
  }

  apiBase(name, depth = 0) {
    if (CLASSES[name]) return name;
    const base = this.userBases[name];
    return base && depth < 10 ? this.apiBase(base, depth + 1) : null;
  }

  /** Тип переменной `name` в точке курсора. */
  varType(name, depth = 0) {
    if (depth > 6) return null;
    if (name === "self" || name === "super") return this.selfClass ? { cls: this.selfClass } : null;
    if (CLASSES[name]) return { cls: name };
    if (this.params[name]) {
      const t = parseType(this.params[name]);
      if (t) return t;
    }
    // Последнее присваивание или `for name in …` выше курсора (в пределах функции).
    for (let i = this.lines.length - 1; i >= this.fnStart; i--) {
      const line = this.lines[i];
      let m = new RegExp(`^\\s*for\\s+${name}\\s+in\\s+(.+?)\\s*:`).exec(line);
      if (m) {
        const t = this.exprType(m[1].replace(/^(?:sorted|list|reversed)\((.*)\)$/, "$1"), depth + 1);
        if (t?.list) return { cls: t.list };
      }
      m = new RegExp(`^\\s*${name}\\s*(?::\\s*([\\w\\[\\]| .]+))?=(?!=)\\s*(.+)$`).exec(line);
      if (m) {
        const t = (m[1] && parseType(m[1])) || this.exprType(m[2].trim(), depth + 1);
        if (t) return t;
      }
    }
    if (name === "s" && HOUSE_BASES.has(this.selfClass)) return { cls: "HouseSensors" };
    const guess = NAME_TYPES[name];
    return guess ? { cls: guess } : null;
  }

  /** Тип выражения-цепочки (`s.nearest_flower()`, `s.flowers[0]`, `self.my_flower`). */
  exprType(expr, depth = 0) {
    const steps = splitChain(expr.replace(/\s+if\s.*$/, "").trim());
    if (!steps || !steps.length) return null;
    const elem = (t) => (t?.list ? { cls: t.list } : null);
    let t;
    let i;
    const first = steps[0];
    if (first.name === "self" && steps.length > 1 && !member(this.selfClass, steps[1].name)) {
      t = this.selfAttrType(steps[1].name, depth); // своё поле: self.my_flower = …
      if (steps[1].index) t = elem(t);
      i = 2;
    } else {
      t = this.varType(first.name, depth);
      if (first.index) t = elem(t);
      i = 1;
    }
    for (const st of steps.slice(i)) {
      if (!t?.cls) return null;
      const m = member(t.cls, st.name);
      if (!m) return null;
      t = parseType(m.type);
      if (st.index) t = elem(t);
    }
    return t;
  }

  selfAttrType(attr, depth) {
    const re = new RegExp(`^\\s*self\\.${attr}\\s*(?::\\s*([\\w\\[\\]| .]+))?=(?!=)\\s*(.+)$`);
    for (let i = this.lines.length - 1; i >= 0; i--) {
      const m = re.exec(this.lines[i]);
      if (m) {
        const t = (m[1] && parseType(m[1])) || this.exprType(m[2].trim(), depth + 1);
        if (t) return t;
      }
    }
    return null;
  }
}

// ------------------------------------------------------------------ подсказки

function renderMember(el, _self, data) {
  const m = data.m;
  const name = document.createElement("span");
  name.className = "h-name";
  name.textContent = m.name;
  el.appendChild(name);
  if (m.sig) {
    const sig = document.createElement("span");
    sig.className = "h-sig";
    sig.textContent = m.sig;
    el.appendChild(sig);
  }
  if (m.type && m.type !== "None") {
    const ty = document.createElement("span");
    ty.className = "h-type";
    ty.textContent = m.kind === "class" ? "класс" : m.type;
    el.appendChild(ty);
  }
  if (m.doc) {
    const doc = document.createElement("span");
    doc.className = "h-doc";
    doc.textContent = m.doc.length > 90 ? `${m.doc.slice(0, 88)}…` : m.doc;
    el.appendChild(doc);
  }
}

function toHint(m) {
  const call = m.kind === "method" || m.kind === "override" || m.kind === "function";
  const empty = m.sig === "()";
  return { text: call ? `${m.name}(${empty ? ")" : ""}` : m.name, m, render: renderMember };
}

let allMembersCache = null;
function allMembers() {
  if (!allMembersCache) {
    const seen = new Map();
    for (const c of Object.values(CLASSES)) for (const m of c.members) if (!seen.has(m.name)) seen.set(m.name, m);
    allMembersCache = [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }
  return allMembersCache;
}

/** Функция подсказок для CodeMirror show-hint. */
export function hint(cm) {
  const cur = cm.getCursor();
  const line = cm.getLine(cur.line).slice(0, cur.ch);
  const word = /\w*$/.exec(line)[0];
  const from = { line: cur.line, ch: cur.ch - word.length };
  const to = cur;
  const lower = word.toLowerCase();
  const match = (name) => name.toLowerCase().startsWith(lower);

  const dot = /([A-Za-z_][\w]*(?:\s*(?:\([^()]*\)|\[[^\[\]]*\])*\s*\.\s*[A-Za-z_]\w*)*(?:\s*(?:\([^()]*\)|\[[^\[\]]*\])*))\s*\.\s*\w*$/.exec(line);
  let list;
  if (dot) {
    const before = cm.getRange({ line: 0, ch: 0 }, { line: cur.line, ch: 0 }) + line;
    const t = new Scope(before).exprType(dot[1]);
    const members = t?.cls ? CLASSES[t.cls].members : allMembers();
    const isSuper = /^super\s*\(\s*\)$/.test(dot[1]);
    list = members.filter((m) => match(m.name) && (m.kind !== "override" || isSuper)).map(toHint);
  } else {
    if (!word) return null;
    const names = [
      ...API_HINTS.globals.map((g) => ({ name: g.name, kind: g.kind === "class" ? "class" : g.kind, doc: g.doc, type: g.kind === "class" ? "class" : "" })),
      { name: "hive_step", kind: "function", sig: "(hive)", doc: "Решения улья (необязательно): def hive_step(hive: Hive)" },
      ...PY_KEYWORDS.map((k) => ({ name: k, kind: "keyword" })),
      ...PY_BUILTINS.map((k) => ({ name: k, kind: "builtin" })),
    ];
    list = names.filter((m) => match(m.name) && m.name !== word).map((m) => ({ text: m.name, m, render: renderMember }));
  }
  if (!list.length) return null;
  return { list, from, to };
}

// ------------------------------------------------------------------ панель матча

const DEFAULT_COLORS = ["#f5b700", "#3a86ff", "#e63946"];
const HIVE_NAMES = ["Улей 1", "Улей 2", "Улей 3"];

/**
 * Форма матча пчёл: профиль → число ульев, скрипт каждого улья, seed, длительность,
 * переключатели врагов и погоды, скорость. `build()` → тело `POST /api/matches`.
 */
export class MatchPanel {
  constructor(root, { profiles }) {
    this.root = root;
    this.profiles = profiles;
    this.scripts = [];
    this.current = null;
    this.choice = {}; // выбранные соперники по номеру улья
    root.innerHTML = `
      <label for="mf-profile">Профиль</label>
      <select id="mf-profile"></select>
      <div id="mf-hives" style="display: contents"></div>
      <label for="mf-seed">Seed</label>
      <input id="mf-seed" type="number" min="0" step="1" value="42">
      <label for="mf-duration">Длительность</label>
      <select id="mf-duration">
        <option value="60">1 мин</option><option value="120" selected>2 мин</option>
        <option value="180">3 мин</option><option value="300">5 мин</option><option value="600">10 мин</option>
      </select>
      <label>Мир</label>
      <div class="toggles">
        <label><input type="checkbox" id="mf-hornets" checked> шершни</label>
        <label><input type="checkbox" id="mf-spiders" checked> пауки</label>
        <label><input type="checkbox" id="mf-weather" checked> погода</label>
      </div>
      <label for="mf-speed">Скорость</label>
      <select id="mf-speed">
        <option value="0.5">×0.5</option><option value="1" selected>×1</option>
        <option value="2">×2</option><option value="4">×4</option>
      </select>`;
    const q = (id) => root.querySelector(`#${id}`);
    this.el = {
      profile: q("mf-profile"), hives: q("mf-hives"), seed: q("mf-seed"), duration: q("mf-duration"),
      hornets: q("mf-hornets"), spiders: q("mf-spiders"), weather: q("mf-weather"), speed: q("mf-speed"),
    };
    const labels = { small: "Малый", medium: "Средний", large: "Большой" };
    for (const p of profiles) {
      const n = this.hiveCount(p.name);
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = `${labels[p.name] || p.name} — ульев: ${n}`;
      opt.title = p.description || "";
      this.el.profile.appendChild(opt);
    }
    this.el.profile.value = profiles.some((p) => p.name === "medium") ? "medium" : profiles[0]?.name;
    this.el.profile.onchange = () => this.renderHives();
    this.restore();
  }

  hiveCount(profile) {
    const p = this.profiles.find((x) => x.name === profile);
    return p?.config?.bees?.world?.n_hives || 3;
  }

  /** Список скриптов с сервера и открытый в редакторе файл (он — первый улей). */
  setScripts(scripts, current) {
    this.scripts = scripts;
    this.current = current;
    this.renderHives();
  }

  renderHives() {
    const box = this.el.hives;
    for (const sel of box.querySelectorAll("select")) this.choice[sel.dataset.hive] = sel.value;
    box.innerHTML = "";
    const n = this.hiveCount(this.el.profile.value);
    for (let i = 0; i < n; i++) {
      const label = document.createElement("label");
      label.innerHTML = `<span class="hive-dot" style="background:${DEFAULT_COLORS[i]}"></span>${HIVE_NAMES[i]}`;
      const sel = document.createElement("select");
      sel.dataset.hive = String(i);
      for (const s of this.scripts) {
        const opt = document.createElement("option");
        opt.value = s.name;
        opt.textContent = s.name + (s.name === this.current ? " (в редакторе)" : "");
        sel.appendChild(opt);
      }
      const fallback = i === 0 ? this.current
        : (this.scripts.find((s) => s.name === (i === 1 ? "example_basic.py" : "example_smart.py"))
          || this.scripts.find((s) => s.name === "example_basic.py") || this.scripts[0])?.name;
      const want = i === 0 ? this.current : this.choice[i];
      sel.value = this.scripts.some((s) => s.name === want) ? want : fallback;
      label.htmlFor = sel.id = `mf-hive-${i}`;
      box.append(label, sel);
    }
  }

  /** Тело запроса `POST /api/matches` (базовый матч demo.yaml + переопределения). */
  build() {
    const byName = new Map(this.scripts.map((s) => [s.name, s]));
    const hives = [...this.el.hives.querySelectorAll("select")].map((sel, i) => ({
      script: byName.get(sel.value)?.path ?? sel.value, color: DEFAULT_COLORS[i],
    }));
    const names = [...this.el.hives.querySelectorAll("select")].map((sel) => sel.value);
    const flow = hives.map((h) => `{script: ${JSON.stringify(h.script)}, color: "${h.color}"}`).join(", ");
    const overrides = [
      `profile=${this.el.profile.value}`,
      `duration_s=${Number(this.el.duration.value)}`,
      `hives=[${flow}]`,
      `enemies.hornets.enabled=${this.el.hornets.checked}`,
      `enemies.spiders.enabled=${this.el.spiders.checked}`,
      `weather.enabled=${this.el.weather.checked}`,
    ];
    const seed = this.el.seed.value === "" ? null : Math.max(0, Math.floor(Number(this.el.seed.value)));
    this.save();
    return { match: "demo.yaml", seed, overrides, scripts: names, speed: Number(this.el.speed.value) };
  }

  save() {
    const state = {
      profile: this.el.profile.value, seed: this.el.seed.value, duration: this.el.duration.value,
      hornets: this.el.hornets.checked, spiders: this.el.spiders.checked, weather: this.el.weather.checked,
      speed: this.el.speed.value,
      choice: Object.fromEntries([...this.el.hives.querySelectorAll("select")].map((s) => [s.dataset.hive, s.value])),
    };
    try {
      localStorage.setItem("swarmlab.editor.match", JSON.stringify(state));
    } catch {
      /* хранилище недоступно — настройки не запомнятся */
    }
  }

  restore() {
    let st = null;
    try {
      st = JSON.parse(localStorage.getItem("swarmlab.editor.match") || "null");
    } catch {
      st = null;
    }
    if (!st) return;
    if ([...this.el.profile.options].some((o) => o.value === st.profile)) this.el.profile.value = st.profile;
    if (st.seed !== undefined) this.el.seed.value = st.seed;
    if (st.duration) this.el.duration.value = st.duration;
    for (const k of ["hornets", "spiders", "weather"]) if (typeof st[k] === "boolean") this.el[k].checked = st[k];
    if (st.speed) this.el.speed.value = st.speed;
    this.choice = st.choice || {};
    delete this.choice["0"]; // первый улей — всегда файл из редактора
  }
}
