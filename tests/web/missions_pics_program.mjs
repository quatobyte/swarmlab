// Обучение (M11): программа, собранная только по картинкам заданий, — как её собрал бы игрок.
// Запуск: node tests/web/missions_pics_program.mjs N → Python-код программы к миссии N (1–4)
// в stdout (tests/bees/test_tutorial.py играет им миссию на настоящем движке).
//   миссия 1 — «Первая программа» (m1_program);
//   с миссии 2 — сборщик из «Сборщик слушает» + «лететь домой» в конце, разведчик «Разведчик зовёт»;
//   с миссии 3 — «Программа улья» с картинки; с миссии 4 — «Разведчиков — сколько нужно» в её начале.
import { generate } from "../../web/js/modules/bees/blocks_gen.js";
import { MISSIONS, editorSetup } from "../../web/js/modules/bees/missions.js";
import { PICTURES, inProgram } from "../../web/js/modules/bees/missions_pics.js";

const n = Number(process.argv[2]);
const copy = (x) => JSON.parse(JSON.stringify(x));
const vars = new Map();
/** Верхний блок картинки внутри программы своего типа; переменные — в общий список. */
function top(name) {
  const ws = copy(inProgram(PICTURES[name]));
  for (const v of ws.variables || []) vars.set(v.id, v);
  const { x, y, ...b } = ws.blocks.blocks[0];
  return b;
}
const last = (b) => (b.next ? last(b.next.block) : b);
const body = (program) => program.inputs.DO.block;

let collector = top("m1_program");
const tops = [];
if (n >= 2) {
  collector = top("m2_listen");
  last(body(collector)).next = { block: { type: "bees_Bee_go_home" } };
  tops.push(top("m2_scout"));
}
if (n >= 3) {
  const hive = top("m3_hive");
  if (n >= 4) {
    const scouts = body(top("m4_scouts"));
    last(scouts).next = { block: body(hive) };
    hive.inputs.DO.block = scouts;
  }
  tops.push(hive);
}
const ws = {
  blocks: { languageVersion: 0, blocks: [collector, ...tops].map((b, i) => ({ ...b, x: 10, y: 10 + 300 * i })) },
  variables: [...vars.values()],
};
const mission = MISSIONS.find((m) => m.id === n);
const g = generate(ws, { file: "tutorial.blocks.json", emptyKinds: editorSetup(mission).blocks.emptyKinds });
if (g.errors.length) throw new Error(JSON.stringify(g.errors));
process.stdout.write(g.code);
