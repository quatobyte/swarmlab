// Лог программы (DECISIONS №106): строки лога → записи, как их увидит игрок.
// Запуск: node tests/web/log_check.mjs <файл лога> → JSON [{kind, who, text, detail, blockText, line}]
import { readFileSync } from "node:fs";

globalThis.window = globalThis;
const { LogGrouper } = await import("../../web/js/core/logparse.js");
const { describeCore, describeError, describeRepeat } = await import("../../web/js/modules/bees/log_ru.js");

const g = new LogGrouper();
const out = [];
const lines = readFileSync(process.argv[2], "utf-8").split(/\r?\n/);
for (const rec of [...lines.flatMap((l) => g.push(l)), ...g.flush()]) {
  if (rec.kind === "error") {
    const py = describeError(rec, { blocks: false });
    const bl = describeError(rec, { blocks: true });
    const fr = rec.frames[rec.frames.length - 1] || {};
    out.push({ kind: "error", who: py.who, text: py.text, detail: py.detail, blockText: bl.text,
      file: fr.file || null, line: fr.line || null, message: rec.message });
    continue;
  }
  const rep = describeRepeat(rec.text);
  if (rep) {
    out.push({ kind: "repeat", ...rep });
    continue;
  }
  const core = describeCore(rec.text);
  if (core === null) continue;
  out.push(core ? { kind: "core", ...core } : { kind: "line", text: rec.text });
}
process.stdout.write(JSON.stringify(out));
