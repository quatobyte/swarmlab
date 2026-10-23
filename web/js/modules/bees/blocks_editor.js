// Блоки пчёл в редакторе (M7b): определения блоков Blockly из blocks_api.js + подписи из
// blocks_ru.js, панель блоков, показ ошибок и предупреждений на блоках.
// Blockly — vendored UMD (`window.Blockly`, DECISIONS №62); генерация Python — blocks_gen.js.

import { BLOCKS_API } from "./blocks_api.js";
import { apiBlock, BEE_KINDS, generate } from "./blocks_gen.js";
import {
  API_RU, BLOCKLY_MSG, BUILTIN_ADVANCED, BUILTIN_BEGINNER, CATEGORIES, CLASS_CATEGORY, CUSTOM_RU, LITERALS, MESSAGES,
} from "./blocks_ru.js";

const B = () => window.Blockly;

/** Подпись `«лететь к x {x} y {y}»` → message/args для Blockly; `{имя}` → `%n`. */
function interpolate(label, argFor) {
  const args = [];
  const message = label.replace(/\{(\w+)\}/g, (_, name) => {
    args.push(argFor(name));
    return `%${args.length}`;
  });
  return { message, args };
}

function hue(cat) {
  return CATEGORIES[cat]?.[1] ?? 0;
}

/** Имя `Literal` из api.py с такими значениями (`["scout", …]` → "Kind"). */
function literalName(options) {
  return Object.entries(BLOCKS_API.literals).find(([, values]) => values.join() === options.join())?.[0];
}

/** Определение блока API (и варианта «удалось: …» для команд, которые можно ждать). */
function apiDefs(desc) {
  const ru = API_RU[desc.api];
  if (!ru) return [];
  const cat = ru.cat || CLASS_CATEGORY[desc.cls] || "move";
  const params = new Map(desc.params.map((p) => [p.name, p]));
  const argFor = (name) => {
    if (name === "obj") return { type: "input_value", name: "obj", check: desc.cls };
    const p = params.get(name);
    if (p?.options) {
      const ruNames = LITERALS[literalName(p.options)] || {};
      return { type: "field_dropdown", name, options: p.options.map((v) => [ruNames[v] || v, v]) };
    }
    return { type: "input_value", name, check: p?.check ?? null };
  };
  const defs = [];
  const variants = [[desc.type, ru.label]];
  if (ru.full && ru.full !== ru.label) variants.push([`${desc.type}__full`, ru.full]);
  for (const [type, label] of variants) {
    const statement = desc.output === null;
    const { message, args } = interpolate(label, argFor);
    const def = {
      type, message0: message, args0: args, inputsInline: true, colour: hue(cat), tooltip: ru.tip || "",
    };
    if (statement) {
      def.previousStatement = null;
      def.nextStatement = null;
      if (desc.waitable) {
        def.message0 += ` ${MESSAGES.waitField} %${args.length + 1}`;
        def.args0 = [...args, { type: "field_checkbox", name: "WAIT", checked: true }];
      }
    } else {
      def.output = desc.output.length ? desc.output : null;
    }
    defs.push(def);
    if (desc.waitable) {
      defs.push({
        ...def, type: type.replace(/^bees_/, "bees_ask_"), message0: `${MESSAGES.askPrefix} ${message}`, args0: args,
        output: "Boolean", previousStatement: undefined, nextStatement: undefined,
      });
    }
  }
  return defs;
}

function customDefs() {
  const kindNames = LITERALS.Kind;
  const R = CUSTOM_RU;
  const defs = [];
  const add = (type, cat, argFor, extra) => {
    const { message, args } = interpolate(R[type].label, argFor);
    defs.push({ type, message0: message, args0: args, colour: hue(cat), tooltip: R[type].tip, inputsInline: true, ...extra });
  };
  add("bees_program_bee", "programs", () => ({
    type: "field_dropdown", name: "KIND", options: BEE_KINDS.map((k) => [kindNames[k], k]),
  }), { message1: "%1", args1: [{ type: "input_statement", name: "DO" }], inputsInline: false });
  add("bees_program_hive", "programs", () => null, {
    message1: "%1", args1: [{ type: "input_statement", name: "DO" }], inputsInline: false,
  });
  add("bees_python_line", "python", () => ({ type: "field_input", name: "CODE", text: "print(s.time)", spellcheck: false }),
    { previousStatement: null, nextStatement: null });
  add("bees_python_expr", "python", () => ({ type: "field_input", name: "CODE", text: "s.me.cargo * 2", spellcheck: false }),
    { output: null });
  add("bees_dict_get", "lists", (n) => ({ type: "input_value", name: n }), { output: null });
  add("bees_dict_set", "lists", (n) => ({ type: "input_value", name: n }), { previousStatement: null, nextStatement: null });
  for (const lit of Object.keys(LITERALS)) {
    const type = `bees_literal_${lit}`;
    add(type, lit === "Task" ? "house" : lit === "Weather" ? "sense" : "hive", () => ({
      type: "field_dropdown", name: "VALUE", options: Object.entries(LITERALS[lit]).map(([v, ru]) => [ru, v]),
    }), { output: "String" });
  }
  return defs;
}

let defined = false;

/** Зарегистрировать блоки пчёл и русский язык Blockly (один раз). */
export function defineBlocks() {
  if (defined) return;
  const Bl = B();
  Object.assign(Bl.Msg, BLOCKLY_MSG);
  const defs = [...customDefs()];
  for (const desc of BLOCKS_API.blocks) defs.push(...apiDefs(desc));
  Bl.common.defineBlocksWithJsonArray(defs);
  defined = true;
}

// ------------------------------------------------------------------ панель блоков

function shadowNum(n) {
  return { shadow: { type: "math_number", fields: { NUM: n } } };
}

function toolboxBlock(type) {
  const a = apiBlock(type);
  const entry = { kind: "block", type };
  if (!a) {
    if (type === "controls_repeat_ext") entry.inputs = { TIMES: shadowNum(3) };
    if (type === "math_random_int") entry.inputs = { FROM: shadowNum(1), TO: shadowNum(10) };
    if (type === "math_arithmetic" || type === "logic_compare") entry.inputs = { A: shadowNum(0), B: shadowNum(0) };
    if (type === "controls_for") entry.inputs = { FROM: shadowNum(1), TO: shadowNum(10), BY: shadowNum(1) };
    return entry;
  }
  const ru = API_RU[a.desc.api] || {};
  const inputs = {};
  for (const p of a.desc.params) {
    if (p.options || !p.check?.includes("Number")) continue;
    const def = ru.shadows?.[p.name] ?? (p.required ? 0 : null);
    if (def !== null) inputs[p.name] = shadowNum(def);
  }
  if (Object.keys(inputs).length) entry.inputs = inputs;
  return entry;
}

/** Панель: стартовый набор по категориям + «Продвинутые» (остальное) + переменные и процедуры. */
export function toolbox() {
  const beginner = {};
  const advanced = {};
  const push = (map, cat, type) => (map[cat] ||= []).push(toolboxBlock(type));
  push(beginner, "programs", "bees_program_bee");
  push(beginner, "programs", "bees_program_hive");
  for (const desc of BLOCKS_API.blocks) {
    const ru = API_RU[desc.api];
    if (!ru) continue;
    const cat = ru.cat || CLASS_CATEGORY[desc.cls] || "move";
    push(ru.beginner ? beginner : advanced, cat, desc.type);
    if (ru.full && ru.full !== ru.label) push(advanced, cat, `${desc.type}__full`);
    if (desc.waitable) push(advanced, cat, desc.type.replace(/^bees_/, "bees_ask_"));
  }
  for (const lit of ["Kind", "Weather", "Task"]) {
    push(lit === "Kind" ? beginner : advanced, lit === "Task" ? "house" : lit === "Weather" ? "sense" : "hive",
      `bees_literal_${lit}`);
  }
  for (const [cat, types] of Object.entries(BUILTIN_BEGINNER)) for (const t of types) push(beginner, cat, t);
  for (const [cat, types] of Object.entries(BUILTIN_ADVANCED)) for (const t of types) push(advanced, cat, t);
  push(advanced, "lists", "bees_dict_get");
  push(advanced, "lists", "bees_dict_set");
  push(advanced, "python", "bees_python_line");
  push(advanced, "python", "bees_python_expr");

  const category = (cat, contents) => ({ kind: "category", name: CATEGORIES[cat][0], colour: hue(cat), contents });
  const order = ["programs", "move", "sense", "objects", "house", "hive", "logic", "loops", "math", "text", "lists"];
  const contents = order.filter((c) => beginner[c]).map((c) => category(c, beginner[c]));
  contents.push({ kind: "category", name: CATEGORIES.variables[0], colour: hue("variables"), custom: "VARIABLE" });
  contents.push({ kind: "category", name: CATEGORIES.procedures[0], colour: hue("procedures"), custom: "PROCEDURE" });
  contents.push({ kind: "sep" });
  const adv = [...order, "python"].filter((c) => advanced[c]).map((c) => category(c, advanced[c]));
  contents.push({ kind: "category", name: CATEGORIES.advanced[0], colour: "#777", contents: adv });
  return { kind: "categoryToolbox", contents };
}

/** Рабочая область нового скрипта: программы сборщика и улья. */
export function starterWorkspace() {
  return {
    blocks: {
      languageVersion: 0,
      blocks: [
        { type: "bees_program_bee", id: "start_forager", x: 30, y: 30, fields: { KIND: "forager" } },
        { type: "bees_program_hive", id: "start_hive", x: 30, y: 260 },
      ],
    },
  };
}

// ------------------------------------------------------------------ редактор блоков

const THEME = {
  name: "swarmlab-dark",
  componentStyles: {
    workspaceBackgroundColour: "#161b22", toolboxBackgroundColour: "#1a1f26", toolboxForegroundColour: "#e6e6e6",
    flyoutBackgroundColour: "#222a33", flyoutForegroundColour: "#ddd", flyoutOpacity: 0.97,
    scrollbarColour: "#555", insertionMarkerColour: "#fff", insertionMarkerOpacity: 0.3,
    cursorColour: "#f5b700",
  },
};

export class BlocksEditor {
  /** onChange() — после каждого изменения рабочей области (не во время перетаскивания). */
  constructor(el, { onChange }) {
    defineBlocks();
    const Bl = B();
    this.Bl = Bl;
    this.ws = Bl.inject(el, {
      toolbox: toolbox(),
      media: "vendor/blockly/media/",
      theme: Bl.Theme.defineTheme(THEME.name, { base: Bl.Themes.Classic, ...THEME }),
      grid: { spacing: 24, length: 2, colour: "#26303b", snap: true },
      zoom: { controls: true, wheel: true, startScale: 0.9, maxScale: 2, minScale: 0.4 },
      trashcan: true,
      sounds: false,
      renderer: "geras",
    });
    this.ws.addChangeListener(Bl.Events.disableOrphans); // неподключённые — серые (DECISIONS №56)
    this.loading = false;
    this.marked = new Set();
    this.ws.addChangeListener((e) => {
      if (this.loading || e.isUiEvent || this.ws.isDragging()) return;
      onChange();
    });
  }

  load(workspace) {
    this.loading = true;
    try {
      this.Bl.Events.disable();
      this.ws.clear();
      this.Bl.serialization.workspaces.load(workspace || starterWorkspace(), this.ws);
    } finally {
      this.Bl.Events.enable();
      this.loading = false;
    }
    // Серость неподключённых после загрузки (события были выключены).
    for (const b of this.ws.getTopBlocks(false)) {
      if (b.previousConnection || b.outputConnection) b.setDisabledReason(true, "ORPHANED_BLOCK");
    }
    this.pendingScroll = true; // к блокам — когда панель станет видимой (до этого размеров нет)
    this.resize();
  }

  /** Левый верхний угол блоков — в левый верхний угол видимой области. */
  scrollToContent() {
    const c = this.ws.getMetricsManager().getContentMetrics();
    this.ws.scroll(-(c.left - 16) * this.ws.scale, -(c.top - 16) * this.ws.scale);
  }

  save() {
    return this.Bl.serialization.workspaces.save(this.ws);
  }

  generate(file) {
    return generate(this.save(), { file });
  }

  resize() {
    this.Bl.svgResize(this.ws);
    if (this.pendingScroll && this.ws.getParentSvg().getBoundingClientRect().width > 0) {
      this.pendingScroll = false;
      // Размеры блоков известны только после отрисовки (Blockly рисует в requestAnimationFrame).
      this.Bl.renderManagement.finishQueuedRenders().then(() => this.scrollToContent());
    }
  }

  /**
   * Показать проблемы на блоках: errors/warnings генератора, дубликаты программ и внешние
   * ошибки (синтаксис `ast`, ошибки во время матча) — `[{block, message}]`.
   */
  showProblems(gen, external = []) {
    const byBlock = new Map();
    const add = (list, level) => {
      for (const p of list) {
        if (!p.block) continue;
        const cur = byBlock.get(p.block) || { level, texts: [] };
        if (level === "error") cur.level = "error";
        if (!cur.texts.includes(p.message)) cur.texts.push(p.message);
        byBlock.set(p.block, cur);
      }
    };
    add(gen.errors, "error");
    add(external, "error");
    add(gen.warnings, "warning");
    const dup = new Set(gen.duplicates);
    for (const id of this.marked) {
      const b = this.ws.getBlockById(id);
      if (!b) continue;
      b.setWarningText(null);
      b.removeClass?.("sl-error");
      b.removeClass?.("sl-warning");
      b.removeClass?.("sl-dup");
    }
    this.marked = new Set();
    for (const [id, p] of byBlock) {
      const b = this.ws.getBlockById(id);
      if (!b) continue;
      b.setWarningText(p.texts.join("\n"));
      b.addClass?.(dup.has(id) ? "sl-dup" : p.level === "error" ? "sl-error" : "sl-warning");
      this.marked.add(id);
    }
  }

  /** Прокрутить к блоку и выделить его. */
  focus(id) {
    const b = this.ws.getBlockById(id);
    if (!b) return false;
    this.ws.centerOnBlock(id);
    b.select();
    return true;
  }
}
