// Блоки пчёл в редакторе (M7b): определения блоков Blockly из blocks_api.js + подписи из
// blocks_ru.js, панель блоков, показ ошибок и предупреждений на блоках.
// Blockly — vendored UMD (`window.Blockly`, DECISIONS №62); генерация Python — blocks_gen.js.

import { BLOCKS_API } from "./blocks_api.js";
import { apiBlock, BEE_KINDS, generate } from "./blocks_gen.js";
import {
  API_RU, BLOCKLY_MSG, BUILTIN_ADVANCED, BUILTIN_BEGINNER, CATEGORIES, CLASS_CATEGORY, CUSTOM_RU, LITERALS, MESSAGES,
  SEARCH_RU,
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

  // toolboxitemid — ключ категории: по нему категория находит иконку и справку (M7c).
  const category = (cat, contents, id = cat) => ({
    kind: "category", name: CATEGORIES[cat][0], colour: hue(cat), contents, toolboxitemid: id,
  });
  const order = ["programs", "move", "sense", "objects", "house", "hive", "logic", "loops", "math", "text", "lists"];
  const contents = [{
    kind: "category", name: SEARCH_RU.category, colour: "#f5b700", custom: SEARCH_CATEGORY,
    toolboxitemid: SEARCH_CATEGORY, hidden: "true",
  }];
  contents.push(...order.filter((c) => beginner[c]).map((c) => category(c, beginner[c])));
  contents.push({ ...category("variables", undefined), custom: "VARIABLE" });
  contents.push({ ...category("procedures", undefined), custom: "PROCEDURE" });
  contents.push({ kind: "sep" });
  const adv = [...order, "python"].filter((c) => advanced[c]).map((c) => category(c, advanced[c], `adv_${c}`));
  contents.push({ ...category("advanced", adv), colour: "#777" });
  for (const c of contents) if (c.contents === undefined) delete c.contents;
  return { kind: "categoryToolbox", contents };
}

/** Все блоки панели (для поиска): `[{entry, category}]`, по категориям, без повторов. */
export function toolboxBlocks(tb = toolbox()) {
  const out = [];
  const seen = new Set();
  const walk = (items, cat) => {
    for (const it of items || []) {
      if (it.kind === "category") walk(it.contents, it.toolboxitemid);
      else if (it.kind === "block" && !seen.has(it.type)) {
        seen.add(it.type);
        out.push({ entry: it, category: cat });
      }
    }
  };
  walk(tb.contents, null);
  return out;
}

/** Динамическая категория «Найдено» (M7c): блоки, чья подпись содержит строку поиска. */
const SEARCH_CATEGORY = "SL_SEARCH";

/** Категория панели с иконкой и справкой при наведении (M7c, в духе MakeCode). */
function defineCategory() {
  const Bl = B();
  if (Bl.__slCategory) return;
  const withIcon = (Base) => class IconCategory extends Base {
    createIconDom_() {
      const icon = document.createElement("span");
      const key = String(this.toolboxItemDef_.toolboxitemid || "").replace(/^adv_/, "");
      icon.className = "sl-cat-icon";
      icon.textContent = key === SEARCH_CATEGORY ? "🔍" : CATEGORIES[key]?.[2] || "•";
      icon.style.background = this.colour_ || "#777";
      return icon;
    }

    createDom_() {
      const dom = super.createDom_();
      const key = String(this.toolboxItemDef_.toolboxitemid || "").replace(/^adv_/, "");
      const tip = CATEGORIES[key]?.[3];
      if (tip && this.rowDiv_) this.rowDiv_.title = tip;
      return dom;
    }
  };
  // Обычная категория и сворачиваемая («Продвинутые» с вложенными категориями).
  for (const Base of [Bl.ToolboxCategory, Bl.CollapsibleToolboxCategory]) {
    Bl.registry.register(Bl.registry.Type.TOOLBOX_ITEM, Base.registrationName, withIcon(Base), true);
  }
  Bl.__slCategory = true;
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
    defineCategory();
    const Bl = B();
    this.Bl = Bl;
    this.el = el;
    this.tb = toolbox();
    this.ws = Bl.inject(el, {
      toolbox: this.tb,
      media: "vendor/blockly/media/",
      theme: Bl.Theme.defineTheme(THEME.name, { base: Bl.Themes.Classic, ...THEME }),
      grid: { spacing: 32, length: 2, colour: "#26303b", snap: true },
      zoom: { controls: true, wheel: true, startScale: 0.75, maxScale: 2, minScale: 0.35 },
      trashcan: true,
      sounds: false,
      // Крупные скруглённые блоки, как в MakeCode (M7c).
      renderer: "zelos",
    });
    this.ws.addChangeListener(Bl.Events.disableOrphans); // неподключённые — серые (DECISIONS №56)
    this.loading = false;
    this.marked = new Set();
    this.hints = [];
    this.ws.addChangeListener((e) => {
      if (!this.loading) this._scheduleHints();
      if (this.loading || e.isUiEvent || this.ws.isDragging()) return;
      onChange();
    });
    this._setupSearch();
  }

  // ------------------------------------------------------------ поиск блока (M7c)

  /** Подписи блоков панели — по тексту блока Blockly (подписи из blocks_ru.js и Blockly.Msg). */
  _searchIndex() {
    if (this.index) return this.index;
    const Bl = this.Bl;
    const headless = new Bl.Workspace();
    this.index = [];
    try {
      for (const { entry } of toolboxBlocks(this.tb)) {
        let text = "";
        try {
          const block = Bl.serialization.blocks.append(entry, headless, { recordUndo: false });
          text = block.toString();
        } catch {
          text = entry.type;
        }
        this.index.push({ entry, text: text.toLowerCase().replace(/\s+/g, " ") });
      }
    } finally {
      headless.dispose();
    }
    return this.index;
  }

  /** Блоки, подпись которых содержит строку (без учёта регистра и «ё»). */
  search(query) {
    const norm = (s) => s.toLowerCase().replace(/ё/g, "е").trim();
    const q = norm(query);
    if (!q) return [];
    return this._searchIndex().filter((x) => norm(x.text).includes(q)).map((x) => x.entry);
  }

  _setupSearch() {
    const box = document.createElement("div");
    box.className = "bl-search";
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = SEARCH_RU.placeholder;
    input.setAttribute("aria-label", SEARCH_RU.placeholder);
    box.appendChild(input);
    this.el.appendChild(box);
    this.searchInput = input;
    this.query = "";
    this.ws.registerToolboxCategoryCallback(SEARCH_CATEGORY, () => {
      const found = this.search(this.query);
      return found.length ? found : [{ kind: "label", text: SEARCH_RU.nothing }];
    });
    let timer = 0;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => this.setQuery(input.value), 120);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        input.value = "";
        this.setQuery("");
      }
    });
  }

  /** Показать «Найдено» с результатами поиска (пустой запрос — спрятать категорию). */
  setQuery(query) {
    this.query = query;
    const toolbox = this.ws.getToolbox();
    const cat = toolbox?.getToolboxItemById(SEARCH_CATEGORY);
    if (!cat) return;
    const on = query.trim() !== "";
    cat.setVisible_(on);
    if (!on) {
      if (toolbox.getSelectedItem() === cat) toolbox.setSelectedItem(null);
      return;
    }
    if (toolbox.getSelectedItem() === cat) toolbox.refreshSelection();
    else toolbox.setSelectedItem(cat);
  }

  // ------------------------------------------------------------ подсказки новичку (M7c)

  _scheduleHints() {
    if (this._hintFrame) return;
    this._hintFrame = requestAnimationFrame(() => {
      this._hintFrame = 0;
      this.updateHints();
    });
  }

  /** «Перетащи сюда команду» в пустых программах (нет блоков внутри DO). */
  updateHints() {
    const empty = this.ws.getTopBlocks(false).filter((b) => (b.type === "bees_program_bee" || b.type === "bees_program_hive")
      && !b.getInputTargetBlock("DO") && !b.isInFlyout);
    const host = this.el.getBoundingClientRect();
    while (this.hints.length < empty.length) {
      const h = document.createElement("div");
      h.className = "bl-hint";
      h.textContent = SEARCH_RU.emptyProgram;
      this.el.appendChild(h);
      this.hints.push(h);
    }
    this.hints.forEach((h, i) => {
      const b = empty[i];
      const r = b?.getSvgRoot()?.getBoundingClientRect();
      const visible = b && r && r.width > 0 && host.width > 0;
      h.hidden = !visible;
      if (!visible) return;
      // Внутрь «рта» блока программы: под строкой заголовка, с отступом от левого края.
      const scale = this.ws.scale;
      h.style.left = `${r.left - host.left + 34 * scale}px`;
      h.style.top = `${r.top - host.top + 52 * scale}px`;
      h.style.fontSize = `${Math.max(11, 15 * scale)}px`;
    });
  }

  /** ↶ / ↷ рабочей области. */
  undo(redo = false) {
    this.ws.undo(redo);
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
    this.ws.clearUndo(); // отмена не уводит в чужой файл
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
    this._scheduleHints();
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
