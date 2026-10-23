// Проверка проекта `.swarm` и предупреждения о чужом коде под Node (tests/web/test_project.py).
//   node project_check.mjs export <имя> <mode> <файл.py> [<файл.blocks.json>]  — текст .swarm
//   node project_check.mjs open <файл.swarm>                                   — разбор
//   node project_check.mjs broken                                              — ошибки битых файлов
//   node project_check.mjs trust                                               — сколько раз спросили
// Печатает JSON.

import { readFileSync } from "node:fs";

import { makeProject, parseProject, projectText } from "../../web/js/core/project.js";
import { confirmForeignCode, TRUST_KEY } from "../../web/js/core/trust.js";

const [mode, ...args] = process.argv.slice(2);
const out = (v) => process.stdout.write(JSON.stringify(v));

if (mode === "export") {
  const [name, pmode, py, blocksFile] = args;
  const blocks = blocksFile ? JSON.parse(readFileSync(blocksFile, "utf8")).workspace : null;
  process.stdout.write(projectText(makeProject({ name, mode: pmode, code: readFileSync(py, "utf8"), blocks })));
} else if (mode === "open") {
  out(parseProject(readFileSync(args[0], "utf8")));
} else if (mode === "broken") {
  const good = { format: 1, name: "my_bees", mode: "python", code: "x = 1\n", blocks: null };
  const cases = {
    json: "{not json",
    array: "[1, 2]",
    format: JSON.stringify({ ...good, format: 7 }),
    nocode: JSON.stringify({ ...good, code: undefined }),
    name: JSON.stringify({ ...good, name: "../evil" }),
    mode: JSON.stringify({ ...good, mode: "lisp" }),
    noblocks: JSON.stringify({ ...good, mode: "blocks", blocks: null }),
  };
  const res = {};
  for (const [k, text] of Object.entries(cases)) {
    try {
      parseProject(text);
      res[k] = null;
    } catch (e) {
      res[k] = `${e.constructor.name}: ${e.message}`;
    }
  }
  out(res);
} else if (mode === "trust") {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  let asked = 0;
  const yes = async () => { asked += 1; return true; };
  const no = async () => { asked += 1; return false; };
  const steps = [];
  const step = async (label, codes, ask) => steps.push([label, await confirmForeignCode(codes, ask, storage), asked]);
  await step("first-no", ["print(1)\n"], no); // отказ — не запоминается
  await step("first-yes", ["print(1)\n"], yes);
  await step("same-again", ["print(1)\n"], yes); // тот же код — без вопроса
  await step("changed", ["print(2)\n"], yes); // изменённый — снова вопрос
  await step("both-known", ["print(1)\n", "print(2)\n"], yes);
  await step("one-new", ["print(1)\n", "print(3)\n"], yes);
  out({ steps, stored: JSON.parse(store.get(TRUST_KEY)).length });
}
