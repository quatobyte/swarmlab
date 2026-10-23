// Проверка блоков под Node (без браузера и без Blockly) для tests/web/test_blocks.py.
//   node blocks_check.mjs gen <файл.blocks.json> [имя.blocks.json]   — генерация одного файла
//   node blocks_check.mjs catalog                                   — каждый блок в программе
//   node blocks_check.mjs ru                                        — словарь и панель блоков
// Печатает JSON.

import { readFileSync } from "node:fs";
import { basename } from "node:path";

import { BLOCKS_API } from "../../web/js/modules/bees/blocks_api.js";
import { toolbox } from "../../web/js/modules/bees/blocks_editor.js";
import { apiBlock, generate } from "../../web/js/modules/bees/blocks_gen.js";
import {
  API_RU, BUILTIN_ADVANCED, BUILTIN_BEGINNER, CUSTOM_RU, LITERALS,
} from "../../web/js/modules/bees/blocks_ru.js";

const [mode, ...args] = process.argv.slice(2);
let n = 0;
const id = (p) => `${p}_${++n}`;
const num = (v) => ({ block: { type: "math_number", id: id("num"), fields: { NUM: v } } });
const getVar = (v) => ({ block: { type: "variables_get", id: id("get"), fields: { VAR: { id: v } } } });

/** Значение для входа с проверкой типов `check`. */
function valueFor(check) {
  if (!check || check.includes("Number")) return num(1);
  if (check.includes("Boolean")) return { block: { type: "logic_boolean", id: id("bool"), fields: { BOOL: "TRUE" } } };
  if (check.includes("Array")) return { block: { type: "lists_create_with", id: id("list"), extraState: { itemCount: 1 }, inputs: { ADD0: num(1) } } };
  if (check.includes("String")) return { block: { type: "text", id: id("text"), fields: { TEXT: "forager" } } };
  return getVar("v_obj");
}

/** Блок API со всеми входами из подписи. */
function apiInstance(type) {
  const { desc, full } = apiBlock(type);
  const ru = API_RU[desc.api];
  const label = full ? ru.full : ru.label;
  const names = [...label.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
  const b = { type, id: id(type), fields: {}, inputs: {} };
  for (const name of names) {
    if (name === "obj") {
      b.inputs.obj = getVar("v_obj");
      continue;
    }
    const p = desc.params.find((x) => x.name === name);
    if (p.options) b.fields[name] = p.options[0];
    else b.inputs[name] = valueFor(p.check);
  }
  if (desc.waitable && desc.output === null && !type.startsWith("bees_ask_")) b.fields.WAIT = true;
  return b;
}

/** Встроенные и свои (не из api.py) блоки — по одному экземпляру. */
function builtinInstances() {
  const v = "v_x";
  const B = (type, extra = {}) => ({ type, id: id(type), ...extra });
  const stmt = [
    B("controls_if", { extraState: { elseIfCount: 1, hasElse: true }, inputs: {
      IF0: { block: B("logic_boolean", { fields: { BOOL: "TRUE" } }) }, DO0: { block: B("text_print", { inputs: { TEXT: num(1) } }) },
      IF1: { block: B("logic_negate", { inputs: { BOOL: { block: B("logic_null") } } }) },
      ELSE: { block: B("text_print", { inputs: { TEXT: { block: B("text", { fields: { TEXT: "ж" } }) } } }) } } }),
    B("controls_repeat_ext", { inputs: { TIMES: num(3), DO: { block: B("controls_flow_statements", { fields: { FLOW: "BREAK" } }) } } }),
    B("controls_whileUntil", { fields: { MODE: "UNTIL" }, inputs: { BOOL: { block: B("logic_compare", { fields: { OP: "GTE" }, inputs: { A: getVar(v), B: num(3) } }) },
      DO: { block: B("math_change", { fields: { VAR: { id: v } }, inputs: { DELTA: num(1) } }) } } }),
    B("controls_forEach", { fields: { VAR: { id: v } }, inputs: { LIST: { block: B("lists_create_empty") },
      DO: { block: B("controls_flow_statements", { fields: { FLOW: "CONTINUE" } }) } } }),
    B("controls_for", { fields: { VAR: { id: v } }, inputs: { FROM: num(1), TO: num(10), BY: num(2) } }),
    B("lists_setIndex", { fields: { MODE: "INSERT", WHERE: "LAST" }, inputs: { LIST: getVar("v_list"), TO: num(1) } }),
    B("lists_setIndex", { fields: { MODE: "SET", WHERE: "FROM_END" }, inputs: { LIST: getVar("v_list"), AT: num(1), TO: num(2) } }),
    B("lists_getIndex", { extraState: { isStatement: true }, fields: { MODE: "REMOVE", WHERE: "RANDOM" }, inputs: { VALUE: getVar("v_list") } }),
    B("bees_dict_set", { inputs: { dict: getVar("v_obj"), key: { block: B("text", { fields: { TEXT: "k" } }) }, value: num(1) } }),
    B("bees_python_line", { fields: { CODE: "pass" } }),
  ];
  const values = [
    B("logic_operation", { fields: { OP: "OR" }, inputs: { A: { block: B("logic_boolean", { fields: { BOOL: "FALSE" } }) }, B: { block: B("logic_boolean", { fields: { BOOL: "TRUE" } }) } } }),
    B("logic_ternary", { inputs: { IF: { block: B("logic_boolean", { fields: { BOOL: "TRUE" } }) }, THEN: num(1), ELSE: num(2) } }),
    B("math_arithmetic", { fields: { OP: "POWER" }, inputs: { A: num(2), B: { block: B("math_arithmetic", { fields: { OP: "MINUS" }, inputs: { A: num(3), B: num(-1) } }) } } }),
    ...["ROOT", "ABS", "NEG", "LN", "LOG10", "EXP", "POW10"].map((op) => B("math_single", { fields: { OP: op }, inputs: { NUM: num(4) } })),
    ...["SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN"].map((op) => B("math_trig", { fields: { OP: op }, inputs: { NUM: num(0.5) } })),
    ...["PI", "E", "GOLDEN_RATIO", "SQRT2", "SQRT1_2", "INFINITY"].map((c) => B("math_constant", { fields: { CONSTANT: c } })),
    ...["ROUND", "ROUNDUP", "ROUNDDOWN"].map((op) => B("math_round", { fields: { OP: op }, inputs: { NUM: num(1.5) } })),
    B("math_modulo", { inputs: { DIVIDEND: num(7), DIVISOR: num(3) } }),
    B("math_constrain", { inputs: { VALUE: num(7), LOW: num(0), HIGH: num(3) } }),
    B("math_random_int", { inputs: { FROM: num(1), TO: num(6) } }),
    B("math_random_float"),
    B("text_join", { extraState: { itemCount: 3 }, inputs: { ADD0: { block: B("text", { fields: { TEXT: "a\"b\\n" } }) }, ADD1: num(1) } }),
    B("lists_create_with", { extraState: { itemCount: 2 }, inputs: { ADD0: num(1), ADD1: num(2) } }),
    B("lists_length", { inputs: { VALUE: getVar("v_list") } }),
    B("lists_isEmpty", { inputs: { VALUE: getVar("v_list") } }),
    ...["FIRST", "LAST", "FROM_START", "FROM_END", "RANDOM"].map((w) => B("lists_getIndex", { fields: { MODE: "GET", WHERE: w }, inputs: { VALUE: getVar("v_list"), AT: num(2) } })),
    B("lists_getIndex", { fields: { MODE: "GET_REMOVE", WHERE: "FROM_START" }, inputs: { VALUE: getVar("v_list"), AT: getVar(v) } }),
    B("bees_dict_get", { inputs: { dict: getVar("v_obj"), key: { block: B("text", { fields: { TEXT: "k" } }) } } }),
    B("bees_python_expr", { fields: { CODE: "1 + 2" } }),
    ...Object.keys(LITERALS).map((lit) => B(`bees_literal_${lit}`, { fields: { VALUE: Object.keys(LITERALS[lit])[0] } })),
  ];
  return { stmt, values };
}

/** Цепочка операторов из списка блоков. */
function chain(blocks) {
  for (let i = 0; i < blocks.length - 1; i++) blocks[i].next = { block: blocks[i + 1] };
  return blocks.length ? { block: blocks[0] } : undefined;
}

function program(kind, body) {
  const vars = [
    variablesSet("v_obj", { block: { type: "logic_null", id: id("null") } }),
    variablesSet("v_list", { block: { type: "lists_create_with", id: id("l"), extraState: { itemCount: 2 }, inputs: { ADD0: num(1), ADD1: num(2) } } }),
    variablesSet("v_x", num(0)),
  ];
  const type = kind === "hive" ? "bees_program_hive" : "bees_program_bee";
  return { type, id: id(`prog_${kind}`), x: 0, y: n * 10, fields: kind === "hive" ? {} : { KIND: kind }, inputs: { DO: chain([...vars, ...body]) } };
}

function variablesSet(v, value) {
  return { type: "variables_set", id: id("set"), fields: { VAR: { id: v } }, inputs: { VALUE: value } };
}

const VARIABLES = [{ name: "obj", id: "v_obj" }, { name: "lst", id: "v_list" }, { name: "x", id: "v_x" }];

function catalog() {
  const bySubject = new Map(); // программа → блоки
  const covered = [];
  const types = [];
  for (const desc of BLOCKS_API.blocks) {
    const ru = API_RU[desc.api];
    if (!ru) continue;
    types.push(desc.type);
    if (ru.full && ru.full !== ru.label) types.push(`${desc.type}__full`);
    if (desc.waitable) types.push(desc.type.replace(/^bees_/, "bees_ask_"));
  }
  for (const type of types) {
    const { desc } = apiBlock(type);
    const kind = desc.subjects[0];
    const list = bySubject.get(kind) || [];
    const b = apiInstance(type);
    list.push(b.type.startsWith("bees_ask_") || desc.output !== null ? variablesSet("v_x", { block: b }) : b);
    bySubject.set(kind, list);
    covered.push(type);
  }
  const { stmt, values } = builtinInstances();
  const forager = bySubject.get("forager") || [];
  forager.push(...stmt, ...values.map((b) => variablesSet("v_x", { block: b })));
  bySubject.set("forager", forager);
  const blocks = [...bySubject].map(([kind, body]) => program(kind, body));
  const ws = { blocks: { languageVersion: 0, blocks }, variables: VARIABLES };
  const r = generate(ws, { file: "catalog.blocks.json" });
  const builtin = [...stmt, ...values].map((b) => b.type);
  return { ...r, covered, builtin };
}

function ruReport() {
  const problems = [];
  for (const desc of BLOCKS_API.blocks) {
    const ru = API_RU[desc.api];
    if (!ru) {
      problems.push(`${desc.api}: нет подписи`);
      continue;
    }
    for (const [which, label] of [["label", ru.label], ["full", ru.full]]) {
      if (!label) continue;
      const names = [...label.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
      const valid = new Set([...desc.params.map((p) => p.name), ...(desc.target === "obj" ? ["obj"] : [])]);
      for (const nm of names) if (!valid.has(nm)) problems.push(`${desc.api}.${which}: лишнее {${nm}}`);
      const need = [...desc.params.filter((p) => p.required).map((p) => p.name), ...(desc.target === "obj" ? ["obj"] : [])];
      for (const nm of need) if (!names.includes(nm)) problems.push(`${desc.api}.${which}: нет {${nm}}`);
      if (which === "full") for (const p of desc.params) if (!names.includes(p.name)) problems.push(`${desc.api}.full: нет {${p.name}}`);
      if (!/[а-яё]/i.test(label)) problems.push(`${desc.api}.${which}: подпись не по-русски`);
    }
  }
  const known = new Set(BLOCKS_API.blocks.map((d) => d.api));
  for (const key of Object.keys(API_RU)) if (!known.has(key)) problems.push(`${key}: в словаре, но нет в api.py`);
  for (const [type, ru] of Object.entries(CUSTOM_RU)) if (!/[а-яё]/i.test(ru.label)) problems.push(`${type}: не по-русски`);
  const inToolbox = [];
  const walk = (items) => {
    for (const it of items) {
      if (it.kind === "block") inToolbox.push(it.type);
      if (it.contents) walk(it.contents);
    }
  };
  const tb = toolbox();
  walk(tb.contents);
  const topNames = tb.contents.filter((c) => c.kind === "category").map((c) => c.name);
  return {
    problems,
    api: BLOCKS_API.blocks.map((d) => d.api),
    beginner: BLOCKS_API.blocks.filter((d) => API_RU[d.api]?.beginner).map((d) => d.api),
    toolbox: inToolbox,
    categories: topNames,
    builtin: [...Object.values(BUILTIN_BEGINNER).flat(), ...Object.values(BUILTIN_ADVANCED).flat()],
    labels: Object.fromEntries(Object.entries(API_RU).map(([k, v]) => [k, v.label])),
  };
}

let out;
if (mode === "gen") {
  const data = JSON.parse(readFileSync(args[0], "utf8"));
  out = generate(data.workspace, { file: args[1] || basename(args[0]) });
} else if (mode === "catalog") {
  out = catalog();
} else if (mode === "ru") {
  out = ruReport();
} else {
  console.error("режим: gen | catalog | ru");
  process.exit(2);
}
console.log(JSON.stringify(out));
