// Обучение пчёл (M11, DECISIONS №104): картинки из блоков для окна задания.
//
// Картинка — рабочая область Blockly (тот же JSON, что в файле блоков): её рисует
// `renderBlocks` из blocks_editor.js настоящими блоками, только для чтения. Подписи к
// картинкам — в missions_ru.js (`examples`), ключ — имя картинки.
//   kind — в чьей программе живёт пример (`collector`, `scout`, `hive`): картинка-фрагмент без
//          блока программы проверяется в тестах внутри программы этого типа.

const VARS = {
  flower: "цветок", message: "сообщение", place: "место", best: "лучший", target: "цель", f: "ц",
};
const varId = (key) => `pic_var_${key}`;

/** Команды подряд: каждая следующая — в `next` предыдущей. */
function chain(...stmts) {
  const list = stmts.filter(Boolean);
  for (let i = list.length - 2; i >= 0; i--) list[i] = { ...list[i], next: { block: list[i + 1] } };
  return list[0] || null;
}
const slot = (block) => ({ block });
const inputs = (map) => Object.fromEntries(Object.entries(map).filter(([, v]) => v).map(([k, v]) => [k, slot(v)]));

const get = (key) => ({ type: "variables_get", fields: { VAR: { id: varId(key) } } });
const set = (key, value) => ({ type: "variables_set", fields: { VAR: { id: varId(key) } }, inputs: inputs({ VALUE: value }) });
const num = (n) => ({ type: "math_number", fields: { NUM: n } });
const txt = (s) => ({ type: "text", fields: { TEXT: s } });
const nul = () => ({ type: "logic_null" });
const no = () => ({ type: "logic_boolean", fields: { BOOL: "FALSE" } });
const cmp = (a, op, b) => ({ type: "logic_compare", fields: { OP: op }, inputs: inputs({ A: a, B: b }) });
const and = (a, b) => ({ type: "logic_operation", fields: { OP: "AND" }, inputs: inputs({ A: a, B: b }) });
const iff = (cond, ...body) => ({ type: "controls_if", inputs: inputs({ IF0: cond, DO0: chain(...body) }) });
/** «если … иначе …»: `body` и `other` — списки команд. */
const ifElse = (cond, body, other) => ({
  type: "controls_if", extraState: { hasElse: true }, inputs: inputs({ IF0: cond, DO0: chain(...body), ELSE: chain(...other) }),
});
const each = (key, list, ...body) => ({
  type: "controls_forEach", fields: { VAR: { id: varId(key) } }, inputs: inputs({ LIST: list, DO: chain(...body) }),
});
/** Блок API: `api("Hive_hatch", {}, {kind: "Collector"})`. */
const api = (name, ins = {}, fields = undefined) => ({
  type: `bees_${name}`, ...(fields ? { fields } : {}), ...(Object.keys(ins).length ? { inputs: inputs(ins) } : {}),
});
const found = () => api("ask_Bee_explore");
const bee = (kind, ...body) => ({ type: "bees_program_bee", fields: { KIND: kind }, inputs: inputs({ DO: chain(...body) }) });
const hive = (...body) => ({ type: "bees_program_hive", inputs: inputs({ DO: chain(...body) }) });

/** Рабочая область картинки: верхние блоки и переменные, которые в них встречаются. */
function picture(kind, ...tops) {
  const used = new Set();
  const walk = (b) => {
    if (!b || typeof b !== "object") return;
    if (b.fields?.VAR?.id) used.add(b.fields.VAR.id);
    for (const v of Object.values(b.inputs || {})) walk(v.block);
    walk(b.next?.block);
  };
  tops.forEach(walk);
  return {
    kind,
    workspace: {
      blocks: { languageVersion: 0, blocks: tops.map((b, i) => ({ ...b, x: 10, y: 10 + i * 200 })) },
      variables: Object.keys(VARS).filter((k) => used.has(varId(k))).map((k) => ({ name: VARS[k], id: varId(k) })),
    },
  };
}

/** Фрагмент: команды подряд без блока программы. */
const frag = (kind, ...stmts) => picture(kind, chain(...stmts));

const notNothing = (key) => cmp(get(key), "NEQ", nul());
const honeyAtLeast = (n) => cmp(api("Hive_honey"), "GTE", num(n));

export const PICTURES = {
  // Миссия 1: как вкладывать блоки и первая программа целиком.
  m1_command: picture("collector", bee("collector", api("Bee_go_home"))),
  m1_value: frag("collector", set("flower", found())),
  m1_program: picture("collector", bee("collector",
    set("flower", found()),
    iff(notNothing("flower"), api("Collector_collect", { target: get("flower") })),
    api("Bee_go_home"))),

  // Миссия 2: разведчик зовёт, сборщик слушает.
  m2_scout: picture("scout", bee("scout",
    set("flower", found()),
    iff(notNothing("flower"), api("Bee_go_home"), api("Agent_say", { word: txt("flowers"), place: get("flower") })))),
  // Сборщик запоминает место из зова: есть место — собирать там, иначе искать самому, как в миссии 1.
  m2_listen: frag("collector",
    set("place", nul()),
    each("message", api("Agent_heard"),
      iff(cmp(api("Message_word", { obj: get("message") }), "EQ", txt("flowers")),
        set("place", api("Message_where", { obj: get("message") })))),
    ifElse(notNothing("place"),
      [api("Collector_collect", { target: get("place") })],
      [set("flower", found()), iff(notNothing("flower"), api("Collector_collect", { target: get("flower") }))])),

  // Миссия 3: улей выводит сборщика, когда мёда хватает.
  m3_hive: picture("hive", hive(
    iff(honeyAtLeast(12), api("Hive_hatch", {}, { kind: "Collector" })),
    api("Agent_wait", { seconds: num(5) }))),

  // Миссия 4: разведчиков — не больше нужного.
  m4_scouts: frag("hive", iff(
    and(cmp(api("Hive_count", {}, { kind: "Scout" }), "LT", num(2)), honeyAtLeast(4)),
    api("Hive_hatch", {}, { kind: "Scout" }))),

  // Миссия 5: разведчик осматривает цветы, сборщик садится на названный.
  m5_scout: frag("scout",
    api("Bee_fly_to", { target: get("flower") }),
    set("best", nul()),
    each("f", api("Bee_flowers"),
      iff(cmp(api("Flower_spider", { obj: get("f") }), "EQ", no()), set("best", get("f"))))),
  m5_collector: frag("collector",
    api("Bee_fly_to", { target: get("place") }),
    set("target", nul()),
    each("f", api("Bee_flowers"),
      iff(cmp(api("Point_distance", { obj: api("Flower_pos", { obj: get("f") }), other: get("place") }), "LT", num(0.5)),
        set("target", get("f")))),
    iff(notNothing("target"), api("Collector_collect", { target: get("target") }))),

  // Миссия 7: предел роя.
  m7_cap: frag("hive", iff(
    cmp(api("Hive_count", {}, { kind: "Collector" }), "LT", num(8)),
    iff(honeyAtLeast(4), api("Hive_hatch", {}, { kind: "Collector" })))),
};

/** Картинка внутри программы своего типа — так тесты проверяют фрагменты генератором. */
export function inProgram(pic) {
  const tops = pic.workspace.blocks.blocks;
  if (tops.some((b) => b.type.startsWith("bees_program_"))) return pic.workspace;
  // Верхние блоки фрагмента идут подряд — как если бы их вложили в программу.
  const body = tops.map(({ x, y, ...b }) => b);
  const top = pic.kind === "hive" ? hive(...body) : bee(pic.kind, ...body);
  return { ...pic.workspace, blocks: { languageVersion: 0, blocks: [{ ...top, x: 10, y: 10 }] } };
}
