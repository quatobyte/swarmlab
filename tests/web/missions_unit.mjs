// Обучение (M11): подсказки, судья и тексты миссий под Node, без браузера и движка.
// Запуск: node tests/web/missions_unit.mjs — падает на первой ошибке (tests/web/test_missions.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { API_RU, CATEGORIES, CUSTOM_RU } from "../../web/js/modules/bees/blocks_ru.js";
import { generate } from "../../web/js/modules/bees/blocks_gen.js";
import {
  MISSIONS, createTracker, matchRequest, programParts, starterWorkspace,
} from "../../web/js/modules/bees/missions.js";
import { HINTS_RU, RESULT_RU } from "../../web/js/modules/bees/missions_ru.js";

const ref = (name) => readFileSync(new URL(`../bees/tutorial/${name}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const COLS = ["scout", "forager", "house", "in_hive"];
const header = (duration) => ({ duration_s: duration, scene: { hive_counts: COLS } });
const frame = (time, { events = [], honey = [10], counts = [0, 3, 3, 3] } = {}) => ({
  time, events, arrays: { hive_honey: honey, hive_nectar: honey.map(() => 0), hive_counts: counts },
});
const mission = (id) => MISSIONS.find((m) => m.id === id);

/** Прогнать кадры 0…T с шагом 1 с (матч длиной `duration`); события — по секундам. */
function play(id, code, T, { events = {}, honey, counts, duration = 1000 } = {}) {
  const t = createTracker(mission(id), header(duration), code);
  const hints = [];
  let result = null;
  for (let s = 0; s <= T && !result; s++) {
    const r = t.update(frame(s, { events: events[s] || [], honey, counts }));
    for (const h of r.hints) hints.push([s, h]);
    result = r.result || null;
  }
  return { hints, result, tracker: t };
}
const has = (hints, key) => hints.some(([, h]) => h === HINTS_RU[key]);

// Стартовая программа кампании: пустые программы трёх типов, без ошибок генерации.
{
  const g = generate(starterWorkspace(), { file: "tutorial.blocks.json" });
  assert.deepEqual(g.errors, []);
  const parts = programParts(g.code);
  for (const k of ["scout", "collector", "hive"]) assert.match(parts[k], /pass/, k);
  const { hints, result } = play(1, g.code, 180, { duration: 180 });
  assert.ok(has(hints, "empty"), "пустой сборщик — подсказка");
  assert.equal(result.win, false);
  assert.match(result.text, /собирать нектар с/);
}

// Эталон 1: нет подсказок о пустой программе и о «лететь домой»; первая доставка — подсказка.
{
  const delivery = { type: "delivery", hive: 0, bee: 7, nectar: 1.5, time: 30 };
  const { hints, result } = play(1, ref("ref_1.py"), 60, { events: { 30: [delivery] } });
  assert.ok(!has(hints, "empty") && !has(hints, "nohome") && !has(hints, "nocollect"), JSON.stringify(hints));
  assert.ok(has(hints, "first"));
  assert.equal(result, null, "1,5 нектара — цель (5) ещё не достигнута");
  const four = Array.from({ length: 4 }, (_, i) => ({ ...delivery, bee: i, time: 40 }));
  const win = play(1, ref("ref_1.py"), 60, { events: { 30: [delivery], 40: four } });
  assert.equal(win.result.win, true);
  assert.equal(win.result.why, "goal");
}

// Сбор без «лететь домой» — подсказка через 25 с без доставок.
{
  const code = ref("ref_1.py").replace("        self.go_home()\n", "");
  const { hints } = play(1, code, 40);
  assert.ok(has(hints, "nohome"), JSON.stringify(hints));
}

// Миссия 2 программой миссии 1: разведчики без дела, сборщики не долетают.
{
  const { hints } = play(2, ref("ref_1.py"), 60);
  assert.ok(has(hints, "far"), JSON.stringify(hints));
  assert.ok(!has(hints, "scoutidle"), "у разведчика есть команда (wait) — он не пустой");
  const empty = play(2, ref("empty.py"), 20).hints;
  assert.ok(has(empty, "scoutidle"));
}

// Миссия 3: нет «вывести» — подсказка; рост засчитан по летающим пчёлам и мёду.
{
  assert.ok(has(play(3, ref("ref_2.py"), 30).hints, "nohive"));
  assert.ok(!has(play(3, ref("ref_3.py"), 30).hints, "nohive"));
  const grown = play(3, ref("ref_3.py"), 10, { honey: [10.5], counts: [1, 8, 3, 0] });
  assert.equal(grown.result.win, true);
  const poor = play(3, ref("ref_3.py"), 10, { honey: [9.5], counts: [1, 8, 3, 0] });
  assert.equal(poor.result, null, "мёда меньше 10 — ещё не цель");
}

// Миссия 5: первая потеря — подсказка, вторая — поражение сразу.
{
  const death = (bee) => ({ type: "death", hive: 0, bee, cause: "spider", kind: "forager", time: 1 });
  const r = play(5, ref("ref_5.py"), 100, { events: { 20: [death(1)], 50: [death(2)] } });
  assert.ok(has(r.hints, "spider5"));
  assert.equal(r.result.win, false);
  assert.equal(r.result.why, "lost");
  assert.equal(r.tracker.time, 50);
  assert.ok(has(play(5, ref("ref_4.py"), 40).hints, "nocheck"));
  assert.ok(!has(play(5, ref("ref_5.py"), 40).hints, "nocheck"));
}

// Соперник: побеждает больший счёт в конце матча; чужая доставка не засчитывается себе.
{
  const m = mission(6);
  const t = createTracker(m, header(10), ref("ref_5.py"));
  const two = { honey: [5, 5], counts: [1, 3, 3, 0, 1, 3, 3, 0] };
  t.update(frame(5, { ...two, events: [{ type: "delivery", hive: 1, nectar: 3, bee: 1 }] }));
  const r = t.update(frame(10, { ...two, events: [{ type: "delivery", hive: 0, nectar: 1.5, bee: 2 }] }));
  assert.equal(r.result.win, false);
  assert.equal(r.result.why, "beat");
  assert.match(r.result.text, /Соперник — 3,0/);
}

// Процедура, вызванная из программы, — часть её кода.
{
  const code = "def trip(self):\n    self.go_home()\n\n\nclass A(Collector):\n    def loop(self):\n        trip(self)\n";
  assert.match(programParts(code).collector, /go_home/);
}

// Тело запуска: улей 1 — программа игрока, дальше соперники по путям из списка скриптов.
{
  const body = matchRequest(mission(8), {
    script: "tutorial.py", scripts: [{ name: "tutorial.py", path: "examples/bees/tutorial.py" }],
  });
  assert.equal(body.match, "tutorial_8.yaml");
  assert.deepEqual(body.scripts, ["tutorial.py"]);
  assert.match(body.overrides[0], /^hives=\[\{script: "examples\/bees\/tutorial.py"/);
  assert.match(body.overrides[0], /example_rival_hoarder\.py.*example_rival_horde\.py/);
}

// Тексты называют блоки так, как они подписаны в blocks_ru.js.
{
  const words = new Set();
  const label = (s) => s.replace(/\{[^}]+\}/g, "…").trim();
  for (const v of Object.values(API_RU)) {
    words.add(label(v.label));
    if (v.ask) words.add(label(v.ask));
  }
  for (const v of Object.values(CUSTOM_RU)) words.add(label(v.label));
  for (const [name] of Object.values(CATEGORIES)) words.add(name);
  // Не блоки: кнопки, Blockly и значения.
  for (const w of ["↻ Начать заново", "если … то …", "ничего", "Программе пчелы сборщик", "Программа пчелы разведчик",
    "Программу пчелы сборщик", "Программе улья",
    "Программа пчелы сборщик", "Программа улья", "Программе улья", "перебрать все цветы", "Копилка", "Орда",
    "вывести сборщик", "вывести разведчик", "сколько пчёл: сборщик", "сколько пчёл: разведчик"]) words.add(w);
  const texts = [
    ...Object.values(HINTS_RU), ...Object.values(RESULT_RU.need),
    ...MISSIONS.flatMap((m) => [m.fresh, m.goal, ...m.brief]),
  ];
  const bad = [];
  for (const text of texts) {
    for (const [, q] of text.matchAll(/«([^»]+)»/g)) {
      const plain = q.replace(/\s*…$/, " …").replace(/„[^“]*“/g, "…").trim();
      const ok = [...words].some((w) => w === plain || w === q || (w.endsWith("…") && plain.startsWith(w.slice(0, -1).trim()))
        || (plain.endsWith("…") && w.startsWith(plain.slice(0, -1).trim())));
      if (!ok) bad.push(q);
    }
  }
  assert.deepEqual([...new Set(bad)], [], "в текстах обучения блоки названы не так, как в blocks_ru.js");
}

console.log("ok");
