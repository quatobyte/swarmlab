// Лог программы (DECISIONS №106): трассировка → одна запись, слова для игрока.
// Запуск: node tests/web/log_unit.mjs
import assert from "node:assert/strict";

globalThis.window = globalThis;
const { LogGrouper, baseName } = await import("../../web/js/core/logparse.js");
const { ERRORS_RU } = await import("../../web/js/modules/bees/missions_ru.js");
const { ERRORS_PY, LOG_RU, describeCore, describeError, describeRepeat, whoOf } = await import("../../web/js/modules/bees/log_ru.js");
const { blockLabel } = await import("../../web/js/modules/bees/blocks_editor.js");

const feed = (lines) => {
  const g = new LogGrouper();
  return [...lines.flatMap((l) => g.push(l)), ...g.flush()];
};

assert.equal(baseName("C:\\Users\\me\\swarmlab\\examples\\bees\\tutorial.py"), "tutorial.py");
assert.equal(baseName("/home/me/tutorial.py"), "tutorial.py");

// Ошибка во время матча (как пишет player_host.format_error) — одна запись, без кода и стрелок.
const err = feed([
  "Пчёлы готовы",
  "Ошибка: Пчела forager id=0, тик 5. На следующем тике loop() начнётся сначала",
  "Traceback (most recent call last):",
  '  File "C:\\Users\\me\\examples\\bees\\tutorial.py", line 15, in loop',
  "    self.collect(self.explore())  # block:UZl@?Lq~-o4bSiv?14lD",
  "    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^",
  "TypeError: collect: куда? Нужен цветок или точка, а получено None",
  "    отступ после ошибки — это уже print игрока",
]);
assert.equal(err.length, 3);
assert.deepEqual(err[0], { kind: "line", text: "Пчёлы готовы" });
assert.equal(err[1].kind, "error");
assert.deepEqual(err[1].frames, [{ file: "tutorial.py", line: 15 }]);
assert.match(err[1].message, /^TypeError: collect/);
assert.equal(err[2].kind, "line");
for (const r of err) assert.doesNotMatch(JSON.stringify(r), /block:|~~~|Traceback/);

// Строка «Ошибка: …» без трассировки — это мог напечатать сам игрок: остаётся строкой.
assert.deepEqual(feed(["Ошибка: цветов нет", "ищу дальше"]),
  [{ kind: "line", text: "Ошибка: цветов нет" }, { kind: "line", text: "ищу дальше" }]);

// Ошибка загрузки (SyntaxError): кадр из самого исключения, стрелка «^» скрыта.
const load = feed([
  "Скрипт tutorial.py не загрузился",
  '  File "/x/tutorial.py", line 3',
  "    if x",
  "        ^",
  "SyntaxError: expected ':'",
]);
assert.equal(load.length, 1);
assert.deepEqual(load[0].frames, [{ file: "tutorial.py", line: 3 }]);

// Ошибка, собранная из двух пакетов лога, — тоже одна запись.
const g = new LogGrouper();
assert.deepEqual(g.push("Ошибка: Улей, тик 3"), []);
assert.deepEqual(g.push("Traceback (most recent call last):"), []);
assert.deepEqual(g.push('  File "/x/t.py", line 9, in loop'), []);
const [hiveErr] = g.push("ZeroDivisionError: division by zero");
assert.equal(hiveErr.kind, "error");

// Кто ошибся.
assert.equal(whoOf("Ошибка: Пчела forager id=0, тик 5"), "Сборщик #0");
assert.equal(whoOf("Ошибка: Пчела scout id=12, тик 5"), "Разведчик #12");
assert.equal(whoOf("Ошибка: finally (Пчела scout id=2)"), "Разведчик #2");
assert.equal(whoOf("Ошибка: Улей, тик 3"), "Улей");
assert.equal(whoOf("Скрипт tutorial.py не загрузился"), LOG_RU.who.load);

// Слова: в блоках — совет вместо текста Python; в Python — текст ошибки и совет второй строкой.
const inBlocks = describeError(err[1], { blocks: true });
assert.equal(inBlocks.who, "Сборщик #0");
assert.match(inBlocks.text, /ничто/);
assert.equal(inBlocks.detail, null);
const inPython = describeError(err[1], { blocks: false });
assert.match(inPython.text, /^TypeError: collect/);
assert.notEqual(inPython.detail, inBlocks.text);
// Незнакомая ошибка в блоках — её текст без имени класса Python.
const odd = describeError({ title: "Ошибка: Улей, тик 1", message: "MyOwnError: что-то своё" }, { blocks: true });
assert.equal(odd.text, "что-то своё");

// Совет в Python — словами кода (None, if), без блоков и гнёзд; ключи — те же, что у ERRORS_RU.
assert.match(inPython.detail, /None/);
for (const [k, text] of Object.entries(ERRORS_PY)) {
  assert.ok(k in ERRORS_RU, k);
  assert.doesNotMatch(text, /блок|гнезд|«если|«ничто»|повторять, пока/i, k);
}
assert.match(describeCore("[ядро] x — раннер перезапускается (№1)", { blocks: true }).text, /повторять, пока/);
assert.match(describeCore("[ядро] x — раннер перезапускается (№1)").text, /while/);

// Повтор ошибки.
assert.deepEqual(describeRepeat("Та же ошибка (TypeError, строка 15) уже 10 раз. Последний: Пчела forager id=3, тик 120"),
  { who: "Сборщик #3", line: 15, text: "та же ошибка повторилась уже 10 раз" });
assert.equal(describeRepeat("Пчёлы готовы"), null);

// Строки ядра: служебные скрыты, остальные — простыми словами без «раннера» и «self».
assert.equal(describeCore("Пчёлы готовы"), undefined);
assert.equal(describeCore("[ядро] запуск раннера: C:\\Users\\me\\tutorial.py"), null);
assert.equal(describeCore("[ядро] скрипт не загрузился:"), null);
assert.equal(describeCore('[stderr] Traceback (most recent call last):'), null);
for (const line of [
  "[ядро] тик 40 пропущен: код улья не ответил за 500 мс при бюджете 20 мс — бесконечный цикл без команд в loop()? (2 подряд, всего 2)",
  "[ядро] тик 41 пропущен: раннер не работает (3 подряд, всего 9)",
  "[ядро] тик 7: код работал 31.0 мс при бюджете 20 мс — команды тика отброшены (превышений: 3)",
  "[ядро] 3 тика подряд без ответа — раннер перезапускается (№1); всё, что пчёлы хранили в self, потеряно",
  "[ядро] 3 тика подряд без ответа; лимит перезапусков (20) исчерпан — улей отключён, пчёлы продолжают последние команды",
  "[ядро] раннер завершился: код 1",
  "[ядро] раннер завершился при запуске: код 1",
  "[ядро] битый ответ раннера отброшен: bad frame",
  "[сервер] … и ещё 120 строк (полный лог — в папке logs/)",
]) {
  const said = describeCore(line);
  assert.ok(said && said.text, line);
  assert.doesNotMatch(said.text, /раннер|мс при бюджете|\{/, line);
  assert.doesNotMatch(describeCore(line, { blocks: true }).text, /раннер|self|loop\(\)|while|мс при бюджете|\{/, line);
}
assert.match(describeCore("[ядро] тик 40 пропущен: код улья не ответил (2 подряд, всего 2)").text, /подряд: 2\./);
assert.equal(describeCore("[ядро] раннер завершился: код 1").level, "err");

// Имена блоков для лога: подпись из словаря, гнёзда — «…».
assert.equal(blockLabel("bees_Collector_collect"), "собирать нектар с …");
assert.equal(blockLabel("bees_ask_Collector_collect"), "груз полный после сбора с …");
assert.equal(blockLabel("controls_if"), null);
// Подпись есть у каждого блока API (иначе в логе было бы «блок «null»»).
const { BLOCKS_API } = await import("../../web/js/modules/bees/blocks_api.js");
for (const b of BLOCKS_API.blocks) assert.ok(blockLabel(b.type), b.type);

console.log("ok");
