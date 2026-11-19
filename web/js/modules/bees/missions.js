// Обучение пчёл (M11, DECISIONS №100): судья миссии — цель, подсказки и итог.
//
// Работает на двух входах с одинаковым смыслом:
//   update(frame)                — кадр живого матча (события delivery/death/birth/weather и
//                                  массивы улья hive_honey, hive_nectar, hive_counts);
//   updateScore(time, rows, ev)  — строки счёта модуля (score().teams) — так тесты судят
//                                  headless-матч тем же кодом (tests/web/missions_check.mjs).
// Сценарий и тексты — missions_ru.js. Ядро (core/ui/tutorial.js) зовёт createTracker и
// показывает подсказки и итог.

import { renderBlocks } from "./blocks_editor.js";
import { MESSAGES } from "./blocks_ru.js";
import { PICTURES } from "./missions_pics.js";
import { CAMPAIGN, ERRORS_RU, HINTS_RU, MISSIONS, RESULT_RU } from "./missions_ru.js";

export { CAMPAIGN, MISSIONS };

const COLORS = ["#f5b700", "#3a86ff", "#e63946"];
const KINDS = { Scout: "scout", Collector: "collector", Hive: "hive" };
const ALL = [1, 2, 3, 4, 5, 6, 7, 8];
const FROM = (n) => ALL.filter((i) => i >= n);

export const fmt = (x) => Number(x || 0).toFixed(1).replace(".", ",");
export const fmtTime = (s) => {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const fill = (tpl, v) => tpl.replace(/\{(\w+)\}/g, (all, k) => (k in v ? String(v[k]) : all));

/**
 * Программа игрока для первой миссии: одна пустая программа сборщика. Программы разведчика и
 * улья редактор добавит, когда их откроет миссия (`editorSetup`, DECISIONS №103).
 */
export function starterWorkspace() {
  return {
    blocks: {
      languageVersion: 0,
      blocks: [{ type: "bees_program_bee", id: "tut_collector", x: 30, y: 30, fields: { KIND: "collector" } }],
    },
  };
}

// ------------------------------------------------------------------ что открыто в редакторе

/** Блоки, которые открывает миссия (типы Blockly; `variables` — категория «Переменные»). */
const NEW_BLOCKS = {
  1: ["bees_ask_Bee_explore", "bees_Collector_collect", "bees_Bee_go_home", "controls_if", "logic_compare",
    "logic_null", "variables"],
  2: ["bees_Agent_say", "bees_Agent_heard", "bees_Message_word", "bees_Message_where", "text", "controls_forEach"],
  3: ["bees_Hive_hatch", "bees_Hive_honey", "bees_Agent_wait", "math_number"],
  4: ["bees_Hive_count", "logic_operation"],
  5: ["bees_Bee_fly_to", "bees_Bee_flowers", "bees_Flower_spider", "bees_Flower_nectar", "bees_Flower_pos",
    "bees_Point_distance", "logic_boolean", "logic_negate", "controls_whileUntil"],
};
/** Программы (блоки-шапки), которые открывает миссия. */
const NEW_PROGRAMS = { 1: ["collector"], 2: ["scout"], 3: ["hive"] };
/** Возможности редактора (их знает ядро: core/ui/editor.js), которые открывает миссия. */
const NEW_FEATURES = { 3: ["logs"], 6: ["python", "help", "project", "free"] };
/** С этой миссии открыт весь редактор: все блоки, «Продвинутые», поиск. */
const FULL_FROM = 6;

const upTo = (table, id) => ALL.filter((i) => i <= id).flatMap((i) => table[i] || []);

/**
 * Что открыто в редакторе в миссии (DECISIONS №103): функции появляются по мере прохождения.
 *   features — возможности редактора ядра;
 *   blocks   — настройка редактора блоков (`BlocksEditor.setup`): открытые блоки (`null` — все),
 *              поиск, программы, которые должны быть в рабочей области, и типы, которым без
 *              блока программы пишется пустая программа (иначе тип жил бы поведением по умолчанию).
 */
export function editorSetup(mission) {
  const full = mission.id >= FULL_FROM;
  return {
    features: upTo(NEW_FEATURES, mission.id),
    blocks: {
      blocks: full ? null : upTo(NEW_BLOCKS, mission.id),
      search: full,
      programs: upTo(NEW_PROGRAMS, mission.id),
      emptyKinds: Object.values(KINDS),
    },
  };
}

// ------------------------------------------------------------------ картинки и ошибки

/** Нарисовать картинку из блоков (`examples[].pic`) в `el`; возвращает «убрать картинку». */
export function illustrate(el, pic) {
  const p = PICTURES[pic];
  return p ? renderBlocks(el, p.workspace) : null;
}

/** Сообщение генератора блоков (`MESSAGES[key]`) → регулярное выражение: `{имя}` — что угодно. */
function messageRe(key) {
  const src = MESSAGES[key].replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\{\w+\}/g, ".+");
  return new RegExp(src);
}

/** Какой совет (`ERRORS_RU`) к какому сообщению: первое совпадение. */
const ERROR_RULES = [
  ...["emptyInput", "wrongSubject", "unsetVariable", "duplicate", "badName"].map((key) => [messageRe(key), key]),
  [/'NoneType' object has no attribute/, "nothingAttr"],
  [/say: первым идёт слово/, "sayWord"],
  [/say: не больше \d+ сообщений/, "sayMany"],
  [/получено None|NoneType/, "nothing"],
  [/нужно (?:обычное )?число/, "needNumber"],
  [/их можно только читать/, "readonly"],
  [/ZeroDivisionError/, "zero"],
  [/UnboundLocalError|NameError/, "unsetVariable"],
  [/не ответил за|бесконечный цикл|работал .* при бюджете|RecursionError/, "slow"],
  [/не загрузился/, "load"],
];

/**
 * Как исправить ошибку: совет к сообщению генератора блоков, к ошибке Python во время матча
 * или к предупреждению ядра. Незнакомая ошибка — общий совет.
 */
export function explainError(message) {
  const text = String(message || "");
  const rule = ERROR_RULES.find(([re]) => re.test(text));
  return ERRORS_RU[rule ? rule[1] : "other"];
}

// ------------------------------------------------------------------ запуск

/** Тело `POST /api/matches`: мир миссии, улей 1 — программа игрока, дальше соперники. */
export function matchRequest(mission, { script, scripts = [] }) {
  const pathOf = (name) => scripts.find((s) => s.name === name)?.path ?? `examples/bees/${name}`;
  const hives = [script, ...mission.rivals.map((r) => r.script)]
    .map((name, i) => `{script: ${JSON.stringify(pathOf(name))}, color: "${COLORS[i]}"}`);
  return {
    match: mission.match, seed: null, overrides: [`hives=[${hives.join(", ")}]`],
    scripts: [script], projects: [], speed: 1,
  };
}

// ------------------------------------------------------------------ код игрока

/**
 * Код по типам: тела классов-наследников Scout, Collector, Hive (с телами процедур, которые
 * они вызывают). Комментарии `# block:` не мешают — проверки ищут вызовы API.
 */
export function programParts(code) {
  const parts = { scout: "", collector: "", hive: "" };
  const defs = {};
  let cur = null;
  let def = null;
  for (const line of String(code || "").split(/\r?\n/)) {
    const cls = /^class\s+\w+\s*\(\s*(?:\w+\.)?(Scout|Collector|Hive)\s*\)\s*:/.exec(line);
    const fn = /^def\s+(\w+)\s*\(/.exec(line);
    if (cls) [cur, def] = [KINDS[cls[1]], null];
    else if (fn) [cur, def] = [null, fn[1]];
    else if (/^\S/.test(line)) [cur, def] = [null, null];
    else if (cur) parts[cur] += `${line}\n`;
    else if (def) defs[def] = `${defs[def] || ""}${line}\n`;
  }
  for (const k of Object.keys(parts)) {
    // Процедуры, вызванные из программы (и из них), — тоже её код.
    const seen = new Set();
    let grew = true;
    while (grew) {
      grew = false;
      for (const [name, body] of Object.entries(defs)) {
        if (!seen.has(name) && new RegExp(`\\b${name}\\s*\\(`).test(parts[k])) {
          seen.add(name);
          parts[k] += body;
          grew = true;
        }
      }
    }
  }
  return parts;
}

/** В программе нет ни одной команды (только `def loop`, `pass`, комментарии). */
export function isEmptyProgram(text) {
  return String(text || "").split("\n")
    .map((l) => l.replace(/#.*$/, "").trim())
    .every((l) => !l || l === "pass" || /^def\s+loop\s*\(\s*self\s*\)\s*:$/.test(l));
}

const CHECKS = {
  collect: (p) => /self\.collect\(/.test(p.collector),
  home: (p) => /self\.go_home\(/.test(p.collector),
  scoutSay: (p) => /self\.say\(/.test(p.scout),
  listen: (p) => /self\.heard\b/.test(p.collector),
  hatch: (p) => /self\.hatch\(\s*Collector\b/.test(p.hive),
  hatchScout: (p) => /self\.hatch\(\s*Scout\b/.test(p.hive) && /self\.count\(\s*Scout\b/.test(p.hive),
  spider: (p) => /\.spider\b/.test(p.scout),
  cap: (p) => /self\.count\(\s*Collector\b/.test(p.hive),
};

/** Приёмы, которые нужны миссии: с первой по эту. */
const NEEDS = {
  1: ["collect", "home"],
  2: ["scoutSay", "listen"],
  3: ["hatch"],
  4: ["hatchScout"],
  5: ["spider"],
  7: ["cap"],
};
export function needsFor(id) {
  return ALL.filter((i) => i <= id).flatMap((i) => NEEDS[i] || []);
}

/** Порог мёда перед выведением сборщика (`self.honey >= N`), если он есть. */
function honeyThreshold(hive) {
  const m = /self\.honey\s*>=?\s*(\d+(?:\.\d+)?)/.exec(hive);
  return m ? Number(m[1]) : null;
}

// ------------------------------------------------------------------ цель

const flying = (t) => t.scout + t.forager;
const lostOf = (t) => t.lostSpider + t.lostEnergy;

/**
 * Решение по цели: `{done, win, why}`. `end` — матч кончился (`{stopped}`); без него —
 * досрочно (цель достигнута, потерь больше допустимого, рой погиб) или по времени.
 */
export function judge(rule, snap, duration, end = null) {
  const me = snap.teams[0];
  if (rule.maxLost != null && lostOf(me) > rule.maxLost) return { done: true, win: false, why: "lost" };
  if (snap.time > 1 && flying(me) + me.house === 0) return { done: true, win: false, why: "dead" };
  if (rule.type === "delivered" && me.delivered >= rule.value - 1e-9) return { done: true, win: true, why: "goal" };
  if (rule.type === "grow" && flying(me) >= rule.bees && me.honey >= rule.honey - 1e-9) {
    return { done: true, win: true, why: "goal" };
  }
  const over = end !== null || snap.time >= duration - 1e-6;
  if (!over) return { done: false };
  if (end?.stopped && snap.time < duration - 1e-6) return { done: true, win: false, why: "stopped" };
  if (rule.type === "beat") {
    const best = Math.max(...snap.teams.slice(1).map((t) => t[rule.metric]));
    return { done: true, win: me[rule.metric] > best, why: "beat" };
  }
  return { done: true, win: false, why: rule.type };
}

// ------------------------------------------------------------------ подсказки

// fix — подсказка о том, что в программе чего-то не хватает: её показывают окном, матч ждёт
// (DECISIONS №103); остальные — короткие сообщения по ходу матча.
const HINTS = [
  { id: "empty", fix: true, m: ALL, when: (c) => c.t > 4 && c.empty.collector },
  { id: "nocollect", fix: true, m: ALL, when: (c) => c.t > 20 && !c.empty.collector && !c.has.collect },
  { id: "nohome", fix: true, m: ALL, when: (c) => c.t > 25 && c.has.collect && !c.has.home && c.deliveries === 0 },
  { id: "first", m: [1], when: (c) => c.deliveries >= 1 },
  { id: "scoutidle", fix: true, m: FROM(2), when: (c) => c.t > 12 && c.empty.scout },
  { id: "far", fix: true, m: [2, 4], when: (c) => c.t > 45 && c.deliveries === 0 && !c.empty.scout && !c.has.scoutSay },
  { id: "nolisten", fix: true, m: FROM(2), when: (c) => c.t > 40 && c.has.scoutSay && !c.has.listen && c.deliveries === 0 },
  { id: "heard", m: [2], when: (c) => c.deliveries >= 1 && c.has.listen && c.has.scoutSay },
  { id: "nohive", fix: true, m: FROM(3), when: (c) => c.t > 20 && !c.has.hatch },
  { id: "born", m: [3], when: (c) => c.births >= 1 },
  { id: "lowhoney", fix: true, m: FROM(3), when: (c) => c.t > 60 && c.has.hatch && c.me.honey < 2 },
  {
    id: "grow", m: [3], when: (c) => flying(c.me) >= Math.ceil((c.rule.bees * 2) / 3),
    vars: (c) => ({ bees: flying(c.me), honey: fmt(c.me.honey), need: c.rule.bees, needHoney: c.rule.honey }),
  },
  { id: "onescout", fix: true, m: [4], when: (c) => c.t > 60 && !c.has.hatchScout },
  {
    id: "fewscouts", fix: true, m: [4], when: (c) => c.t >= c.duration / 2 && c.me.delivered < c.rule.value * 0.45 && c.me.scout < 3,
    vars: (c) => ({ delivered: fmt(c.me.delivered), need: c.rule.value, scouts: c.me.scout }),
  },
  { id: "spider5", fix: true, m: [5], when: (c) => c.spiderDeaths >= 1 },
  { id: "spider", fix: true, m: FROM(6), when: (c) => c.spiderDeaths >= 1 },
  { id: "nocheck", fix: true, m: FROM(5), when: (c) => c.t > 30 && !c.has.spider },
  {
    id: "bigrival", fix: true, m: [6], when: (c) => c.t > 90 && c.me.delivered < c.teams[1].delivered && (c.threshold ?? 0) >= 10,
    vars: (c) => ({ me: fmt(c.me.delivered), rival: fmt(c.teams[1].delivered) }),
  },
  { id: "rain", m: FROM(6), when: (c) => c.weather === "rain" },
  {
    id: "nocap", fix: true, m: [7, 8], when: (c) => c.t > 150 && !c.has.cap && flying(c.me) >= 10,
    vars: (c) => ({ bees: flying(c.me), honey: fmt(c.me.honey) }),
  },
  { id: "half", m: FROM(6), when: (c) => c.t >= c.duration / 2, vars: (c) => c.standing() },
  { id: "late", m: [7, 8], when: (c) => c.t >= c.duration - 120, vars: (c) => c.standing() },
];

// ------------------------------------------------------------------ судья

const emptyTeam = () => ({
  honey: 0, nectar: 0, delivered: 0, scout: 0, forager: 0, house: 0, lostSpider: 0, lostEnergy: 0,
});

export function createTracker(mission, header, code) {
  return new Tracker(mission, header, code);
}

export class Tracker {
  constructor(mission, header, code) {
    this.m = mission;
    this.rule = mission.rule;
    this.duration = Number(header?.duration_s) || 0;
    this.cols = header?.scene?.hive_counts || ["scout", "forager", "house", "in_hive"];
    const parts = programParts(code);
    this.has = Object.fromEntries(Object.entries(CHECKS).map(([k, f]) => [k, f(parts)]));
    this.empty = { scout: isEmptyProgram(parts.scout), collector: isEmptyProgram(parts.collector), hive: isEmptyProgram(parts.hive) };
    this.threshold = honeyThreshold(parts.hive);
    this.teams = [];
    this.time = 0;
    this.c = { deliveries: 0, births: 0, spiderDeaths: 0, energyDeaths: 0, weather: "clear" };
    this.fired = new Set();
  }

  _team(h) {
    while (this.teams.length <= h) this.teams.push(emptyTeam());
    return this.teams[h];
  }

  _events(events) {
    for (const e of events || []) {
      const h = Number(e.hive ?? -1);
      if (e.type === "delivery" && h >= 0) {
        this._team(h).delivered += Number(e.nectar) || 0;
        if (h === 0) this.c.deliveries += 1;
      } else if (e.type === "death" && h >= 0) {
        const t = this._team(h);
        if (e.cause === "spider") t.lostSpider += 1;
        else t.lostEnergy += 1;
        if (h === 0 && e.cause === "spider") this.c.spiderDeaths += 1;
        if (h === 0 && e.cause !== "spider") this.c.energyDeaths += 1;
      } else if (e.type === "birth" && h === 0 && Number(e.time) > 1) {
        this.c.births += 1;
      } else if (e.type === "weather") {
        this.c.weather = e.state;
      }
    }
  }

  /** Кадр живого матча. */
  update(frame) {
    this._events(frame.events);
    const A = frame.arrays || {};
    const n = A.hive_honey?.length || 0;
    const w = this.cols.length;
    for (let h = 0; h < n; h++) {
      const t = this._team(h);
      t.honey = Number(A.hive_honey[h]);
      t.nectar = Number(A.hive_nectar?.[h] ?? 0);
      for (const k of ["scout", "forager", "house"]) {
        const i = this.cols.indexOf(k);
        if (i >= 0 && A.hive_counts) t[k] = Number(A.hive_counts[h * w + i]);
      }
    }
    this.time = Number(frame.time) || 0;
    return this.step();
  }

  /** Строки счёта модуля (`score().teams`): тесты и итог по footer. */
  updateScore(time, rows, events = []) {
    this._events(events);
    this._applyRows(rows);
    this.time = Number(time) || 0;
    return this.step();
  }

  _applyRows(rows) {
    for (const [key, r] of Object.entries(rows || {})) {
      const t = this._team(Number(key));
      for (const k of ["honey", "nectar", "delivered", "scout", "forager", "house"]) {
        if (r[k] !== undefined) t[k] = Number(r[k]);
      }
      if (r.deaths_spider !== undefined) t.lostSpider = Number(r.deaths_spider);
      if (r.deaths_energy !== undefined) t.lostEnergy = Number(r.deaths_energy);
    }
  }

  snapshot() {
    this._team(this.m.rivals.length);
    return { time: this.time, teams: this.teams };
  }

  step() {
    const snap = this.snapshot();
    const out = { progress: this.progress(), hints: this._hints() };
    const st = judge(this.rule, snap, this.duration);
    if (st.done) out.result = this.result(st);
    return out;
  }

  /** Конец матча (footer): счёт модуля — последнее слово. */
  finish(score, stopped = false) {
    if (score?.teams) this._applyRows(score.teams);
    return this.result(judge(this.rule, this.snapshot(), this.duration, { stopped }));
  }

  _metric(t) {
    const k = this.rule.metric || "delivered";
    return `${fmt(t[k])} ${RESULT_RU.metric[k]}`;
  }

  _standing() {
    const k = this.rule.metric || "delivered";
    return this.m.rivals.map((r, i) => `${r.name} — ${fmt(this.teams[i + 1]?.[k])}`).join(", ");
  }

  progress() {
    const me = this._team(0);
    const r = this.rule;
    let text;
    if (r.type === "delivered") text = `Нектара принесено ${fmt(me.delivered)} из ${r.value}`;
    else if (r.type === "grow") text = `Летающих пчёл ${flying(me)} из ${r.bees} · мёда ${fmt(me.honey)} (нужно ≥ ${r.honey})`;
    else text = `У тебя ${this._metric(me)} · ${this._standing()}`;
    if (r.maxLost != null) text += ` · потеряно ${lostOf(me)} из ${r.maxLost} допустимых`;
    return text;
  }

  _ctx() {
    const c = this.c;
    return {
      ...c, t: this.time, duration: this.duration, rule: this.rule, me: this._team(0), teams: this.teams,
      has: this.has, empty: this.empty, threshold: this.threshold,
      standing: () => ({ me: this._metric(this._team(0)), standing: this._standing() }),
    };
  }

  _hints() {
    const ctx = this._ctx();
    const out = [];
    for (const h of HINTS) {
      if (this.fired.has(h.id) || !h.m.includes(this.m.id)) continue;
      if (!h.when(ctx)) continue;
      this.fired.add(h.id);
      out.push({ id: h.id, fix: !!h.fix, text: fill(HINTS_RU[h.id], h.vars ? h.vars(ctx) : {}) });
    }
    return out;
  }

  result(st) {
    const me = this._team(0);
    const stats = fill(RESULT_RU.stats, {
      time: fmtTime(Math.min(this.time, this.duration)), total: fmtTime(this.duration),
      delivered: fmt(me.delivered), honey: fmt(me.honey), bees: flying(me), lost: lostOf(me),
    });
    if (st.win) return { win: true, why: st.why, title: this.m.title, text: this.m.win, stats };
    const r = this.rule;
    const v = {
      lost: lostOf(me), max: r.maxLost, delivered: fmt(me.delivered), need: r.value ?? r.bees,
      bees: flying(me), honey: fmt(me.honey), needHoney: r.honey, me: this._metric(me), standing: this._standing(),
    };
    let text = fill(RESULT_RU[st.why] || RESULT_RU.stopped, v);
    const missing = needsFor(this.m.id).filter((k) => !this.has[k]).map((k) => RESULT_RU.need[k]);
    if (missing.length && st.why !== "stopped") text += ` ${fill(RESULT_RU.missing, { list: missing.join(", ") })}`;
    return { win: false, why: st.why, title: this.m.title, text, stats };
  }
}
