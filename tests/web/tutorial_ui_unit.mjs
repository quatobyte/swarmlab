// Жизненный цикл общего учебного UI без движка и браузерных зависимостей.
import assert from "node:assert/strict";
import { Emitter } from "../../web/js/core/playback.js";
import { MissionRun, Progress } from "../../web/js/core/ui/tutorial.js";

const nodes = new Map();
globalThis.document = {
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, { textContent: "", hidden: false });
    return nodes.get(id);
  },
};

const memory = new Map();
const storage = { getItem: (k) => memory.get(k), setItem: (k, v) => memory.set(k, v) };
const missions = Array.from({ length: 8 }, (_, i) => ({ id: i + 1, title: `Mission ${i + 1}` }));
let progress = new Progress(storage);
assert.equal(progress.open(missions, 0), true);
for (let i = 1; i < 8; i++) assert.equal(progress.open(missions, i), false);
for (const i of [-1, 8, NaN, 0.5]) assert.equal(progress.open(missions, i), false);
for (let i = 0; i < 8; i++) {
  assert.equal(progress.open(missions, i), true);
  progress.pass(missions[i].id, "passed");
  progress = new Progress(storage); // перезагрузка сохраняет открытие и переигрывание
  assert.equal(progress.passed(missions[i].id), true);
  assert.equal(progress.open(missions, i), true);
}
assert.equal(new Progress({ getItem: () => "broken" }).passed(1), false);
Object.defineProperty(globalThis, "localStorage", { configurable: true, get() { throw Error("denied"); } });
assert.doesNotThrow(() => new Progress());
assert.doesNotThrow(() => new Progress({ getItem() { throw Error("denied"); } }).pass(1));

let updates = 0, finishes = 0, results = 0;
const campaign = {
  CAMPAIGN: { script: "tutorial.py" }, MISSIONS: missions,
  createTracker: () => ({
    update: () => { updates++; return { progress: "1/5" }; },
    finish: () => { finishes++; return { win: false }; },
  }),
};
const run = new MissionRun(campaign, 0, { result: () => results++ });
const source = () => Object.assign(new Emitter(), { header: {}, status: { state: "running" } });
const old = source(), current = source();
run.attach(old, "saved code");
run.attach(current, "new code");
old.emit("frame", {});
old.emit("footer", { score: {} });
assert.equal(updates + finishes + results, 0, "прошлая попытка не влияет на новую");
current.emit("frame", {});
assert.equal(updates, 1);
assert.equal(nodes.get("mission-progress").textContent, "1/5");
current.emit("footer", { score: {} });
current.emit("footer", { score: {} });
assert.equal(finishes, 1);
assert.equal(results, 1, "повторный footer не выдаёт второй итог");

run.attach(current, "saved code");
run.dispose();
current.emit("frame", {});
current.emit("footer", { score: {} });
assert.equal(updates, 1, "закрытая миссия не обрабатывает кадры");
const errors = [];
const errorOptions = [];
run.startError = (message, show, options) => { errors.push(message); errorOptions.push(options); };
run.attach(current, "saved code");
current.emit("status", { state: "error", error: "worker failed" });
assert.equal(errors.at(-1), "worker failed");
assert.equal(results, 1, "ошибка сервера не засчитывает прохождение");
run.attach(current, "saved code");
current.emit("close", {});
assert.match(errors.at(-1), /Программа сохранена/);
assert.equal(errorOptions.at(-1).advice, false, "разрыв связи не обвиняет блоки программы");
assert.match(errorOptions.at(-1).title, /Матч прерван/);
assert.equal(results, 1);

// Редактор снимает ограничения сразу при выходе, сохраняя рабочую область.
globalThis.window = { CodeMirror: {} };
const { Editor } = await import("../../web/js/core/ui/editor.js");
const classes = new Set(["mission", "lock-python"]);
document.body = { classList: {
  remove: (name) => classes.delete(name),
  toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
} };
const editor = new Editor({});
let disposed = 0, settings = "restricted", resizes = 0;
editor.mission = { dispose: () => disposed++ };
editor.blocks = { setup: (spec) => { settings = spec; }, resize: () => resizes++ };
editor.clearMission();
assert.equal(disposed, 1);
assert.equal(editor.mission, null);
assert.equal(settings, null);
assert.equal(classes.has("mission"), false);
assert.equal(classes.has("lock-python"), false);
assert.equal(resizes, 1);

// Новый пользователь не наследует открытый файл прошлого аккаунта.
let opened;
const { DEFAULT_MODULE } = await import("../../web/js/modules/registry.js");
const userDefault = `my_${DEFAULT_MODULE ?? "agents"}.py`;
editor._loadScripts = async () => { editor.scripts = [{ name: userDefault }]; };
editor.openFile = async (name) => { opened = name; };
editor.reloadUser = true;
await editor._openUserFile();
assert.equal(opened, userDefault);
assert.equal(editor.reloadUser, false);

// Ошибка построения запроса и повторный Ctrl+Enter не оставляют запуск заблокированным.
editor.file = { name: "tutorial.py" };
editor._showStartError = (message) => { if (message) errors.push(message); };
editor._readyToRun = async () => true;
editor.panel = { build() { throw Error("invalid match"); } };
editor._jumpToError = () => {};
await editor.start();
assert.match(errors.at(-1), /invalid match/);
assert.equal(editor.starting, false);
assert.equal(nodes.get("match-start").disabled, false);
let ready;
editor._readyToRun = () => new Promise((resolve) => { ready = resolve; });
let requests = 0;
editor.panel = { build: () => ({}) };
editor.h.start = async () => requests++;
const pending = editor.start();
await editor.start();
ready(true);
await pending;
assert.equal(requests, 1);
console.log("ok");
