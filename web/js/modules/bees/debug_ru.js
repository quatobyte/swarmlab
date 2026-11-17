// Инспектор пчелы (M12, DECISIONS №105): снимок программы от раннера → слова для карточки.
//
// Снимок собирает `swarmlab/bees/debug.py`:
//   {line, fn, wait, pass, vars: [[имя, значение]], self: [[имя, значение]], heard: [значение], error}
// Значение — null, bool, число, строка или {k: "point" | "flower" | "bee" | "message" | "list" |
// "dict" | "obj", …}. Здесь нет DOM: функции проверяются под Node (tests/web/debug_unit.mjs).

export const DEBUG_RU = {
  title: { vars: "Переменные", self: "Запомнила", heard: "Слышит" },
  hiveTitle: "программа улья",
  hiveHint: "Нажми: что сейчас делает программа улья",
  inHive: "в улье",
  pass: "круг {n}",
  line: "строка {n}",
  inProcedure: "в процедуре «{name}»",
  blockShown: "блок подсвечен в редакторе",
  noVars: "пока нет",
  error: "Ошибка",
  nothing: "ничто",
  yes: "истина",
  no: "ложь",
  // Команда, выполнения которой ждёт программа (`wait[0]` — имя команды модуля).
  wait: {
    fly_to: "летит к точке {at}",
    search: "ищет цветы по пути к {at}",
    explore: "ищет цветы",
    go_home: "летит домой",
    refuel: "заправляется",
    collect: "собирает нектар с цветка",
    collect_at: "летит собирать нектар у {at}",
    wait: "ждёт {s} с",
    tick: "закончила круг, начинает новый",
  },
  hiveWait: { wait: "ждёт {s} с", tick: "закончил круг, начинает новый" },
  idle: "программа ещё не запущена",
  crashed: "остановилась из-за ошибки, начнёт программу сначала",
  hiveCrashed: "программа остановилась из-за ошибки, начнётся сначала",
};

const fill = (text, map) => text.replace(/\{(\w+)\}/g, (_, k) => (k in map ? map[k] : `{${k}}`));

/** Число для карточки: целые как есть, дробные — до двух знаков. */
export function formatNumber(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return String(v);
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

const at = (x, y) => `(${formatNumber(Math.round(x * 10) / 10)}, ${formatNumber(Math.round(y * 10) / 10)})`;

/** Значение переменной словами. `depth` — вложенность списков. */
export function formatValue(v, depth = 0) {
  if (v === null || v === undefined) return DEBUG_RU.nothing;
  if (v === true) return DEBUG_RU.yes;
  if (v === false) return DEBUG_RU.no;
  if (typeof v === "number") return formatNumber(v);
  if (typeof v === "string") return `«${v}»`;
  switch (v.k) {
    case "point":
      return `точка ${at(v.x, v.y)}`;
    case "flower": {
      const spider = v.spider === true ? ", паук!" : v.spider === false ? ", паука нет" : "";
      return `цветок ${at(v.x, v.y)}, нектар ${formatNumber(v.nectar)}${spider}`;
    }
    case "bee":
      return `${v.friend ? "своя" : "чужая"} пчела ${at(v.x, v.y)}`;
    case "message":
      return `сообщение «${v.word}»${v.where ? ` про место ${at(v.where[0], v.where[1])}` : ""}`;
    case "list": {
      if (!v.n) return "пустой список";
      const shown = depth > 0 ? [] : v.items.map((x) => formatValue(x, depth + 1));
      const more = v.n > shown.length && shown.length ? ", …" : "";
      return shown.length ? `список из ${v.n}: ${shown.join("; ")}${more}` : `список из ${v.n}`;
    }
    case "dict": {
      if (!v.n) return "пустой словарь";
      const shown = depth > 0 ? [] : v.items.map(([k, x]) => `${formatValue(k, depth + 1)} → ${formatValue(x, depth + 1)}`);
      const more = v.n > shown.length && shown.length ? ", …" : "";
      return shown.length ? `словарь из ${v.n}: ${shown.join("; ")}${more}` : `словарь из ${v.n}`;
    }
    default:
      return `объект ${v.text ?? ""}`.trim();
  }
}

/** Что программа делает сейчас: по команде, которой она ждёт. `hive` — программа улья. */
export function describeWait(snap, hive = false) {
  const w = snap?.wait;
  if (!w) {
    if (snap?.error) return hive ? DEBUG_RU.hiveCrashed : DEBUG_RU.crashed;
    return DEBUG_RU.idle;
  }
  const [name, a, b] = w;
  const text = (hive && DEBUG_RU.hiveWait[name]) || DEBUG_RU.wait[name];
  if (!text) return String(name);
  return fill(text, { at: typeof a === "number" && typeof b === "number" ? at(a, b) : "", s: formatNumber(a) });
}

/**
 * Строки карточки инспектора: {doing, where, vars, self, heard, error}.
 * `blockShown` — выполняемый блок подсвечен в редакторе (иначе показываем номер строки).
 */
export function debugRows(snap, { hive = false, blockShown = false } = {}) {
  if (!snap) return null;
  const where = [];
  if (snap.pass) where.push(fill(DEBUG_RU.pass, { n: snap.pass }));
  if (snap.fn) where.push(fill(DEBUG_RU.inProcedure, { name: snap.fn }));
  if (snap.line != null) where.push(blockShown ? DEBUG_RU.blockShown : fill(DEBUG_RU.line, { n: snap.line }));
  const pairs = (rows) => (rows || []).map(([name, value]) => [String(name), formatValue(value)]);
  return {
    doing: describeWait(snap, hive),
    where: where.join(" · "),
    vars: pairs(snap.vars),
    self: pairs(snap.self),
    heard: (snap.heard || []).map((m) => formatValue(m)),
    error: snap.error ? { text: String(snap.error.text || ""), line: snap.error.line ?? null } : null,
  };
}
