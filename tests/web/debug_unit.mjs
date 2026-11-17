// Инспектор пчелы (M12, DECISIONS №105): снимок программы → слова карточки; строка → блок.
// Запуск: node tests/web/debug_unit.mjs
import assert from "node:assert/strict";

globalThis.window = globalThis;
const { DEBUG_RU, debugRows, describeWait, formatNumber, formatValue } = await import("../../web/js/modules/bees/debug_ru.js");
const { blockAtLine, generate } = await import("../../web/js/modules/bees/blocks_gen.js");
const { PICTURES } = await import("../../web/js/modules/bees/missions_pics.js");

// Значения переменных — словами, как в блоках: «ничто», «истина», «ложь».
assert.equal(formatValue(null), "ничто");
assert.equal(formatValue(true), "истина");
assert.equal(formatValue(false), "ложь");
assert.equal(formatValue(3), "3");
assert.equal(formatValue(2.456), "2.46");
assert.equal(formatNumber(-0.5), "-0.5");
assert.equal(formatValue("flowers"), "«flowers»");
assert.equal(formatValue({ k: "point", x: 10.04, y: -3.26 }), "точка (10, -3.3)");
assert.equal(formatValue({ k: "flower", x: 12, y: 40, nectar: 2.5, spider: null }), "цветок (12, 40), нектар 2.5");
assert.equal(formatValue({ k: "flower", x: 12, y: 40, nectar: 0, spider: true }), "цветок (12, 40), нектар 0, паук!");
assert.equal(formatValue({ k: "flower", x: 1, y: 2, nectar: 3, spider: false }), "цветок (1, 2), нектар 3, паука нет");
assert.equal(formatValue({ k: "bee", x: 1, y: 2, friend: false }), "чужая пчела (1, 2)");
assert.equal(formatValue({ k: "message", word: "flowers", where: [10, 20] }), "сообщение «flowers» про место (10, 20)");
assert.equal(formatValue({ k: "message", word: "go", where: null }), "сообщение «go»");
assert.equal(formatValue({ k: "list", n: 0, items: [] }), "пустой список");
assert.equal(formatValue({ k: "list", n: 8, items: [1, 2] }), "список из 8: 1; 2, …");
assert.equal(formatValue({ k: "list", n: 1, items: [{ k: "list", n: 3, items: [1, 2, 3] }] }), "список из 1: список из 3");
assert.equal(formatValue({ k: "dict", n: 1, items: [["a", 1]] }), "словарь из 1: «a» → 1");
assert.equal(formatValue({ k: "obj", text: "Loud" }), "объект Loud");

// Что делает программа: по команде, которой она ждёт.
const waits = {
  "ищет цветы": ["explore", null],
  "летит к точке (10, 20)": ["fly_to", 10, 20, null],
  "ищет цветы по пути к (10, 20)": ["search", 10, 20, null],
  "собирает нектар с цветка": ["collect", 7, null],
  "летит собирать нектар у (1.5, 2)": ["collect_at", 1.5, 2, null],
  "летит домой": ["go_home", null],
  "заправляется": ["refuel", 80],
  "ждёт 2.5 с": ["wait", 2.5],
  "закончила круг, начинает новый": ["tick"],
};
for (const [text, wait] of Object.entries(waits)) assert.equal(describeWait({ wait }), text);
// Все команды движения модуля названы (имена — из api.py: `_wait_move("имя", …)`).
{
  const { readFileSync } = await import("node:fs");
  const api = readFileSync(new URL("../../src/swarmlab/bees/api.py", import.meta.url), "utf8");
  const moves = [...api.matchAll(/_wait_move\("(\w+)"/g)].map((m) => m[1]);
  assert.ok(moves.length >= 6);
  for (const name of moves) assert.ok(DEBUG_RU.wait[name], `команда ${name} без подписи в инспекторе`);
}
assert.equal(describeWait({ wait: ["wait", 5] }, true), "ждёт 5 с");
assert.equal(describeWait({ wait: ["tick"] }, true), "закончил круг, начинает новый");
assert.equal(describeWait({ wait: null, error: null }), DEBUG_RU.idle);
assert.equal(describeWait({ wait: null, error: { text: "TypeError: x", line: 3 } }), DEBUG_RU.crashed);
assert.equal(describeWait({ wait: ["dance"] }), "dance");

// Карточка целиком.
{
  const snap = {
    line: 17, fn: null, wait: ["collect", 7, null], pass: 3,
    vars: [["цветок", { k: "flower", x: 12, y: 40, nectar: 2.5, spider: null }], ["n", 2]],
    self: [["my_trips", 4]], heard: [{ k: "message", word: "flowers", where: [10, 20] }], error: null,
  };
  assert.deepEqual(debugRows(snap), {
    doing: "собирает нектар с цветка", where: "круг 3 · строка 17",
    vars: [["цветок", "цветок (12, 40), нектар 2.5"], ["n", "2"]], self: [["my_trips", "4"]],
    heard: ["сообщение «flowers» про место (10, 20)"], error: null,
  });
  assert.equal(debugRows(snap, { blockShown: true }).where, "круг 3 · блок подсвечен в редакторе");
  assert.equal(debugRows({ ...snap, fn: "найти" }).where, "круг 3 · в процедуре «найти» · строка 17");
  const failed = debugRows({ line: null, fn: null, wait: null, pass: 0, vars: [], self: [], heard: [],
    error: { text: "TypeError: collect: куда?", line: 15 } });
  assert.equal(failed.doing, DEBUG_RU.crashed);
  assert.deepEqual(failed.error, { text: "TypeError: collect: куда?", line: 15 });
  assert.equal(debugRows(null), null);
}

// Строка кода, на которой ждёт программа, ведёт к блоку: у каждой команды, которая ждёт, в
// сгенерированном коде стоит пометка блока.
{
  // Картинка-пример без id блоков; в редакторе у каждого блока id есть — расставим.
  const ws = JSON.parse(JSON.stringify(PICTURES.m1_program.workspace));
  let n = 0;
  const walk = (b) => {
    if (!b) return;
    b.id = `b${++n}`;
    for (const v of Object.values(b.inputs || {})) walk(v.block);
    walk(b.next?.block);
  };
  ws.blocks.blocks.forEach(walk);
  const code = generate(ws, {}).code;
  const lines = code.split("\n");
  for (const call of ["self.explore()", "self.collect(", "self.go_home()"]) {
    const i = lines.findIndex((l) => l.includes(call));
    assert.ok(i >= 0, call);
    assert.ok(blockAtLine(code, i + 1), `у строки с ${call} нет пометки блока`);
  }
  assert.equal(blockAtLine(code, 1), null);
}

console.log("ok");
