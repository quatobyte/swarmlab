// Судья обучающих миссий под Node (M11): тот же web/js/modules/bees/missions.js, что в браузере.
// Построчный протокол (tests/bees/test_tutorial.py):
//   первая строка  {mission, duration, code}          — миссия, длительность матча, код игрока;
//   дальше строки  {time, rows, end?, stopped?}       — счёт модуля (score().teams) раз в секунду;
//   ответ на каждую — {done, win, why, progress, hints}.  end — конец матча (итог по счёту).
import { createInterface } from "node:readline";
import { MISSIONS, createTracker } from "../../web/js/modules/bees/missions.js";

let tracker = null;
const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  if (!line.trim()) return;
  const msg = JSON.parse(line);
  if (!tracker) {
    const m = MISSIONS.find((x) => x.id === msg.mission);
    if (!m) throw new Error(`нет миссии ${msg.mission}`);
    tracker = createTracker(m, { duration_s: msg.duration }, msg.code);
    process.stdout.write(`${JSON.stringify({ ok: true, rule: m.rule })}\n`);
    return;
  }
  let out;
  if (msg.end) {
    tracker.time = msg.time;
    const r = tracker.finish({ teams: msg.rows }, !!msg.stopped);
    out = { done: true, win: r.win, why: r.why, text: r.text, stats: r.stats, hints: [] };
  } else {
    const r = tracker.updateScore(msg.time, msg.rows);
    out = { done: !!r.result, win: r.result?.win ?? null, why: r.result?.why ?? null, progress: r.progress, hints: r.hints, text: r.result?.text, stats: r.result?.stats };
  }
  process.stdout.write(`${JSON.stringify(out)}\n`);
});
