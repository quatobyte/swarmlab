// Пересобрать `.py` из файла блоков без браузера (M7b): тем же генератором, что и редактор.
//   node tools\blocks_to_py.mjs examples\bees\example_blocks.blocks.json   → example_blocks.py рядом
//   node tools\blocks_to_py.mjs <файл.blocks.json> --check                 → код 1, если .py устарел
// Нужен Node.js ≥ 18. Ошибки блоков печатаются; .py пишется и с ними (как в редакторе).

import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";

import { generate } from "../web/js/modules/bees/blocks_gen.js";

const [file, flag] = process.argv.slice(2);
if (!file || !file.endsWith(".blocks.json")) {
  console.error("использование: node tools/blocks_to_py.mjs <имя>.blocks.json [--check]");
  process.exit(2);
}
const data = JSON.parse(readFileSync(file, "utf8"));
if (data.mode !== "blocks") {
  console.error(`${file}: скрипт переведён в Python — блоки его не обновляют`);
  process.exit(2);
}
const res = generate(data.workspace, { file: basename(file) });
for (const e of res.errors) console.error(`ошибка в блоке ${e.block}: ${e.message}`);
for (const w of res.warnings) console.error(`предупреждение в блоке ${w.block}: ${w.message}`);
const out = file.replace(/\.blocks\.json$/, ".py");
let current = "";
try {
  current = readFileSync(out, "utf8");
} catch {
  current = "";
}
if (flag === "--check") {
  if (current !== res.code) {
    console.error(`${out} устарел: node tools/blocks_to_py.mjs ${file}`);
    process.exit(1);
  }
  console.log(`${out} совпадает с блоками`);
} else {
  writeFileSync(out, res.code, "utf8");
  console.log(`записан ${out}`);
}
process.exit(res.errors.length ? 1 : 0);
