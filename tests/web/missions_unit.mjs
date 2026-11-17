// Обучение (M11): подсказки, судья и тексты миссий под Node, без браузера и движка.
// Запуск: node tests/web/missions_unit.mjs — падает на первой ошибке (tests/web/test_missions.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BLOCKS_API } from "../../web/js/modules/bees/blocks_api.js";
import { toolbox, toolboxBlocks } from "../../web/js/modules/bees/blocks_editor.js";
import { API_RU, CATEGORIES, CUSTOM_RU, MESSAGES } from "../../web/js/modules/bees/blocks_ru.js";
import { generate } from "../../web/js/modules/bees/blocks_gen.js";
import {
  GENERATOR_ERRORS, MISSIONS, createTracker, editorSetup, errorKind, explainError, matchRequest, programParts,
  starterWorkspace,
} from "../../web/js/modules/bees/missions.js";
import { PICTURES, inProgram } from "../../web/js/modules/bees/missions_pics.js";
import { ERRORS_RU, HINTS_RU, RESULT_RU } from "../../web/js/modules/bees/missions_ru.js";

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
const has = (hints, key) => hints.some(([, h]) => h.id === key && h.text === HINTS_RU[key]);
const fixOf = (hints, key) => hints.find(([, h]) => h.id === key)?.[1].fix;

// Стартовая программа кампании: в блоках — только программа сборщика, но в коде пустые программы
// всех трёх типов (иначе разведчик и улей жили бы поведением по умолчанию, DECISIONS №103).
{
  const ws = starterWorkspace();
  assert.deepEqual(ws.blocks.blocks.map((b) => b.fields?.KIND), ["collector"]);
  const plain = generate(ws, { file: "tutorial.blocks.json" });
  assert.doesNotMatch(plain.code, /MyScout|MyHive/, "без настройки миссии пустых программ нет");
  const g = generate(ws, { file: "tutorial.blocks.json", emptyKinds: editorSetup(mission(1)).blocks.emptyKinds });
  assert.deepEqual(g.errors, []);
  const parts = programParts(g.code);
  for (const k of ["scout", "collector", "hive"]) assert.match(parts[k], /pass/, k);
  const { hints, result } = play(1, g.code, 180, { duration: 180 });
  assert.ok(has(hints, "empty"), "пустой сборщик — подсказка");
  assert.equal(fixOf(hints, "empty"), true, "нет программы — важная подсказка (окно с паузой)");
  assert.equal(result.win, false);
  assert.match(result.text, /собирать нектар с/);
}

// Эталон 1: нет подсказок о пустой программе и о «лететь домой»; первая доставка — подсказка.
{
  const delivery = { type: "delivery", hive: 0, bee: 7, nectar: 1.5, time: 30 };
  const { hints, result } = play(1, ref("ref_1.py"), 60, { events: { 30: [delivery] } });
  assert.ok(!has(hints, "empty") && !has(hints, "nohome") && !has(hints, "nocollect"), JSON.stringify(hints));
  assert.ok(has(hints, "first"));
  assert.equal(fixOf(hints, "first"), false, "радостная подсказка матч не останавливает");
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
  for (const w of ["↻ Начать заново", "▶ Начать миссию", "если … то …", "ничего", "ничто", "присвоить", "повторять, пока", "для каждого элемента", "вернуть", "выйти из цикла",
    "перейти к следующему шагу цикла", "и", "или", "ложь", "цветок", "Памятка", "Свободная игра", "Программе пчелы сборщик", "Программа пчелы разведчик",
    "Программу пчелы сборщик", "Программы пчелы сборщик", "Программу улья", "Программе улья",
    "Программа пчелы сборщик", "Программа улья", "Программе улья", "перебрать все цветы", "Копилка", "Орда",
    "вывести сборщик", "вывести разведчик", "сколько пчёл: сборщик", "сколько пчёл: разведчик"]) words.add(w);
  const texts = [
    ...Object.values(HINTS_RU), ...Object.values(RESULT_RU.need), ...Object.values(ERRORS_RU),
    ...MISSIONS.flatMap((m) => [m.fresh, m.goal, m.watch || "", ...m.brief, ...(m.examples || []).flatMap((e) => [e.title, e.text])]),
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

// Что открыто в редакторе (DECISIONS №103): функции появляются по мере прохождения.
{
  const all = new Set(toolboxBlocks().map((x) => x.entry.type));
  const byMember = new Map(); // член API → типы блоков
  for (const b of BLOCKS_API.blocks) {
    const member = b.api.split(".")[1];
    const types = [b.type, `${b.type}__full`, b.type.replace(/^bees_/, "bees_ask_")].filter((x) => all.has(x));
    byMember.set(member, [...(byMember.get(member) || []), ...types]);
  }
  // Конструкции Python в эталоне → блок, без которого их не собрать.
  const SYNTAX = [
    [/^\s*if\b/m, "controls_if"], [/^\s*for\b/m, "controls_forEach"], [/^\s*while\b/m, "controls_whileUntil"],
    [/\bNone\b/, "logic_null"], [/\b(?:True|False)\b/, "logic_boolean"], [/\b(?:and|or)\b/, "logic_operation"],
    [/(?:==|!=|>=|<=|<|>|\bis\b)/, "logic_compare"], [/"[^"]*"/, "text"], [/\b\d+(?:\.\d+)?\b/, "math_number"],
    [/^\s*\w+ = /m, "variables"],
  ];
  let prev = { features: [], blocks: { blocks: [], programs: [] } };
  for (const m of MISSIONS) {
    const s = editorSetup(m);
    assert.deepEqual(s.blocks.emptyKinds, ["scout", "collector", "hive"], `миссия ${m.id}`);
    for (const f of prev.features) assert.ok(s.features.includes(f), `миссия ${m.id}: «${f}» не закрывается обратно`);
    for (const k of prev.blocks.programs) assert.ok(s.blocks.programs.includes(k), `миссия ${m.id}: программа ${k}`);
    if (s.blocks.blocks === null) {
      assert.equal(s.blocks.search, true, `миссия ${m.id}: весь редактор — с поиском`);
    } else {
      assert.ok(prev.blocks.blocks !== null, `миссия ${m.id}: блоки не закрываются обратно`);
      const open = new Set(s.blocks.blocks);
      for (const t of prev.blocks.blocks) assert.ok(open.has(t), `миссия ${m.id}: блок ${t} не закрывается обратно`);
      for (const t of open) {
        assert.ok(all.has(t) || t === "variables" || t === "procedures", `миссия ${m.id}: нет блока ${t}`);
      }
      // Панель миссии: только открытые блоки, без «Продвинутых».
      const tb = toolbox(s.blocks.blocks);
      assert.deepEqual(new Set(toolboxBlocks(tb).map((x) => x.entry.type)), new Set([...open].filter((t) => all.has(t))));
      assert.ok(!tb.contents.some((c) => c.toolboxitemid === "advanced"));
      assert.equal(tb.contents.some((c) => c.custom === "VARIABLE"), open.has("variables"));
      // Эталон миссии собирается из открытых блоков: каждый вызов API и каждая конструкция.
      // (программы, которые миссия ещё не открыла, в эталоне — заглушки, их не смотрим).
      const parts = programParts(ref(`ref_${m.id}.py`));
      const code = s.blocks.programs.map((k) => parts[k]).join("\n").replace(/^\s*def loop\(self\):$/gm, "");
      for (const [, member] of code.matchAll(/\.([A-Za-z_]\w*)\b/g)) {
        const types = byMember.get(member);
        assert.ok(types, `миссия ${m.id}: в эталоне .${member} — не из API`);
        assert.ok(types.some((t) => open.has(t)), `миссия ${m.id}: для .${member} не открыт ни один блок (${types.join(", ")})`);
      }
      for (const [re, type] of SYNTAX) {
        if (re.test(code)) assert.ok(open.has(type), `миссия ${m.id}: эталону нужен блок ${type}`);
      }
    }
    prev = s;
  }
  assert.deepEqual(editorSetup(mission(1)).features, [], "в первой миссии нет ни лога, ни Python, ни памятки");
  assert.deepEqual(editorSetup(mission(1)).blocks.programs, ["collector"]);
  assert.ok(editorSetup(mission(3)).features.includes("logs"));
  assert.equal(editorSetup(mission(6)).blocks.blocks, null, "с миссии 6 открыт весь редактор");
}

// Картинки-примеры в задании (DECISIONS №104): у каждой страницы есть картинка, картинка собрана
// из блоков, открытых в своей миссии, и генератор принимает её без ошибок.
{
  const used = new Set();
  const types = (b, out = []) => {
    if (!b) return out;
    out.push(b.type);
    for (const v of Object.values(b.inputs || {})) types(v.block, out);
    return types(b.next?.block, out);
  };
  for (const m of MISSIONS) {
    const open = editorSetup(m).blocks.blocks;
    for (const ex of m.examples || []) {
      const pic = PICTURES[ex.pic];
      assert.ok(pic, `миссия ${m.id}: нет картинки ${ex.pic}`);
      assert.ok(ex.title && ex.text, `миссия ${m.id}: у примера ${ex.pic} нет подписи`);
      used.add(ex.pic);
      const g = generate(inProgram(pic), { file: "pic.blocks.json" });
      assert.deepEqual(g.errors, [], `картинка ${ex.pic}: ${JSON.stringify(g.errors)}`);
      assert.match(g.code, new RegExp(`class My${pic.kind[0].toUpperCase()}${pic.kind.slice(1)}\\b`), ex.pic);
      if (open) {
        const allowed = new Set([...open, "bees_program_bee", "bees_program_hive"]);
        if (allowed.has("variables")) ["variables_get", "variables_set"].forEach((t) => allowed.add(t));
        for (const top of pic.workspace.blocks.blocks) {
          for (const t of types(top)) assert.ok(allowed.has(t), `картинка ${ex.pic}: блок ${t} в миссии ${m.id} ещё закрыт`);
        }
      }
    }
  }
  assert.deepEqual(Object.keys(PICTURES).filter((k) => !used.has(k)), [], "картинка без страницы в задании");
  assert.ok(MISSIONS.slice(0, 5).every((m) => m.examples?.length), "в миссиях 1–5 есть пример с картинкой");
  // Первая программа на картинке — рабочая: та же, что эталон миссии 1.
  const code = programParts(generate(PICTURES.m1_program.workspace, {}).code).collector;
  for (const call of ["self.explore()", "self.collect(", "self.go_home()", "is not None"]) assert.ok(code.includes(call), call);
}

// Совет, как исправить ошибку (DECISIONS №104): у каждой ошибки, которую может увидеть игрок, — свой.
{
  const seen = new Set();
  const kind = (message) => {
    const k = errorKind(message);
    assert.equal(explainError(message), ERRORS_RU[k], message);
    seen.add(k);
    return k;
  };
  // Общие советы: годятся только для ошибки, которой нет в списках ниже.
  const FALLBACK = new Set(["other", "typeOther", "value", "attr"]);

  // 1. Редактор блоков: каждое сообщение об ошибке из blocks_ru.js — со своим советом.
  const NOT_ERRORS = new Set(["askPrefix", "fullSuffix", "header", "header2", "header3"]);
  const genKeys = Object.keys(MESSAGES).filter((k) => typeof MESSAGES[k] === "string" && !NOT_ERRORS.has(k));
  assert.deepEqual([...GENERATOR_ERRORS].sort(), [...genKeys].sort(), "у каждого сообщения генератора есть совет");
  for (const key of genKeys) {
    assert.ok(ERRORS_RU[key], `нет совета для сообщения генератора ${key}`);
    assert.equal(kind(`В блоках есть ошибки: ${MESSAGES[key].replace(/\{\w+\}/g, "нечто")}`), key);
  }

  // 2. Команды пчёл и раннер: каждое `raise` с текстом в исходниках — не общий совет.
  const source = (path) => readFileSync(new URL(`../../src/swarmlab/${path}`, import.meta.url), "utf8");
  const raised = (src) => {
    const out = [];
    for (const m of src.matchAll(/raise (\w+)\(/g)) {
      let i = m.index + m[0].length;
      for (let depth = 1; depth > 0 && i < src.length; i++) depth += src[i] === "(" ? 1 : src[i] === ")" ? -1 : 0;
      const call = src.slice(m.index + m[0].length, i - 1);
      const text = [...call.matchAll(/f?"((?:[^"\\]|\\.)*)"/g)].map((x) => x[1]).join("")
        .replace(/\{[^{}]*\}/g, "нечто").replace(/\\"/g, '"');
      if (text) out.push(`${m[1]}: ${text}`);
    }
    return out;
  };
  const api = raised(source("bees/api.py"));
  assert.equal(api.length, 15, "ошибок с текстом в api.py — столько, сколько проверено здесь");
  const runner = [...raised(source("core/program.py")), ...raised(source("bees/player_host.py"))];
  assert.equal(runner.length, 5);
  for (const message of [...api, ...runner]) assert.ok(!FALLBACK.has(kind(message)), `только общий совет: ${message}`);
  // «Ничто» в команде — отдельный совет, каким бы ни было остальное сообщение.
  assert.equal(kind("TypeError: collect: куда? Нужна цель — цветок, пчела, сообщение, точка или x, y; а получено None"), "nothing");
  assert.equal(kind("TypeError: wait: нужно число, а получено None"), "nothing");
  assert.equal(kind("TypeError: fly_to: куда? Нужна цель — цветок, пчела, сообщение, точка или x, y; а получено 'flowers'"), "badTarget");
  assert.equal(kind("TypeError: say: первым идёт слово в кавычках, например say(\"flowers\"), а получено None"), "sayWord");

  // 3. Ядро: все сообщения `[ядро]` из runner_host.py — восемь предупреждений и «запуск раннера»
  // (не ошибка); «тик пропущен» бывает с двумя причинами.
  const CORE = [
    ["раннер завершился при запуске: код 1", "crash"],
    ["скрипт не загрузился:\nTraceback (most recent call last):", "load"],
    ["раннер завершился: код 1", "crash"],
    ["битый ответ раннера отброшен: 'tick'", "game"],
    ["тик 40: код работал 31.5 мс при бюджете 20 мс — команды тика отброшены (превышений: 3)", "budget"],
    ["тик 12 пропущен: код улья не ответил за 200 мс при бюджете 20 мс — бесконечный цикл без команд в loop()? (1 подряд, всего 1)", "slow"],
    ["тик 12 пропущен: раннер не работает (1 подряд, всего 1)", "crash"],
    ["3 тика подряд без ответа; лимит перезапусков (20) исчерпан — улей отключён, пчёлы продолжают последние команды", "disabled"],
    ["3 тика подряд без ответа — раннер перезапускается (№1); всё, что пчёлы хранили в self, потеряно", "restart"],
  ];
  const coreLines = source("core/runner_host.py").match(/"\[ядро\] /g).length;
  assert.equal(coreLines, 9, "сообщений ядра в runner_host.py — столько, сколько проверено здесь");
  for (const [message, key] of CORE) assert.equal(kind(message), key, message);

  // 4. Python и запуск матча: типовые ошибки.
  const PYTHON = [
    ["AttributeError: 'NoneType' object has no attribute 'nectar'", "nothingAttr"],
    ["AttributeError: 'Flower' object has no attribute 'word'", "attr"],
    ["TypeError: '<' not supported between instances of 'NoneType' and 'int'", "nothingValue"],
    ["TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'", "nothingValue"],
    ["TypeError: '<' not supported between instances of 'str' and 'int'", "typeMix"],
    ["TypeError: unsupported operand type(s) for +: 'int' and 'str'", "typeMix"],
    ["TypeError: can only concatenate str (not \"int\") to str", "typeMix"],
    ["TypeError: 'NoneType' object is not iterable", "notList"],
    ["TypeError: 'int' object is not iterable", "notList"],
    ["TypeError: 'NoneType' object is not subscriptable", "nothing"],
    ["TypeError: MyCollector.loop() takes 0 positional arguments but 1 was given", "args"],
    ["TypeError: найти() missing 1 required positional argument: 'x'", "args"],
    ["TypeError: 'int' object is not callable", "typeOther"],
    ["IndexError: list index out of range", "index"],
    ["KeyError: 'x'", "key"],
    ["ZeroDivisionError: division by zero", "zero"],
    ["NameError: name 'цветок' is not defined", "unsetVariable"],
    ["UnboundLocalError: cannot access local variable 'цветок' where it is not associated with a value", "unsetVariable"],
    ["RecursionError: maximum recursion depth exceeded", "deep"],
    ["ValueError: math domain error", "value"],
    ["ModuleNotFoundError: No module named 'numpy'", "import"],
    ["Матч не запущен: tutorial.py, строка 7: Синтаксическая ошибка: invalid syntax", "syntax"],
    ["Матч не запущен: tutorial.py, строка 7: Ошибка отступа: unexpected indent", "indent"],
    ["SyntaxError: invalid syntax", "syntax"],
    ["Матч не запущен: Ошибка конфига: hives: нужен список", "game"],
    ["Матч не запущен: Failed to fetch", "server"],
    ["MemoryError", "other"],
  ];
  for (const [message, key] of PYTHON) assert.equal(kind(message), key, message);

  // Нет советов, до которых не добраться.
  assert.deepEqual(Object.keys(ERRORS_RU).filter((k) => !seen.has(k)), [], "советы без правила");
}

console.log("ok");
