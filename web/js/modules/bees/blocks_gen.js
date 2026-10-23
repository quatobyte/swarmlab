// Генерация Python из блоков пчёл (M7b, DECISIONS №50, 53, 55, 56, 62).
//
// Вход — JSON рабочей области Blockly (`Blockly.serialization.workspaces.save`), выход — текст
// `.py` и всё, что нужно редактору: какому блоку принадлежит каждая строка (комментарий
// `# block:<id>`), какие блоки не подключены, какие программы — дубликаты, ошибки и
// предупреждения на блоках. Blockly здесь не нужен: модуль работает и в браузере, и под Node
// (тесты), результат зависит только от JSON.

import { BLOCKS_API } from "./blocks_api.js";
import { MESSAGES as M } from "./blocks_ru.js";

/** Типы программ пчёл (порядок в коде) и их классы в api.py. */
export const BEE_KINDS = ["scout", "forager", "guard", "house"];
const BASE_CLASS = { scout: "Scout", forager: "Forager", guard: "Guard", house: "HouseBee" };
const USER_CLASS = { scout: "MyScout", forager: "MyForager", guard: "MyGuard", house: "MyHouse" };
const ALL_SUBJECTS = [...BEE_KINDS, "hive"];

const API = new Map(BLOCKS_API.blocks.map((b) => [b.type, b]));

/** Тип блока → {desc, ask, full} для блоков API; `null` — не блок API. */
export function apiBlock(type) {
  let t = type;
  const full = t.endsWith("__full");
  if (full) t = t.slice(0, -"__full".length);
  const ask = t.startsWith("bees_ask_");
  if (ask) t = `bees_${t.slice("bees_ask_".length)}`;
  const desc = API.get(t);
  return desc ? { desc, ask, full } : null;
}

// Приоритеты операций Python (как в генераторе Blockly): меньше — сильнее связывает.
const O = {
  ATOMIC: 0, MEMBER: 2, EXP: 3, UNARY: 4, MUL: 5, ADD: 6, REL: 11, NOT: 12, AND: 13, OR: 14,
  COND: 15, NONE: 99,
};

const PY_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def",
  "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is",
  "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
  "match", "case", "type",
]);
/** Имена, которые генератор использует сам, — переменной или процедуре их не дать. */
const RESERVED = new Set([
  "self", "s", "hive", "wait", "math", "random", "print", "len", "range", "int", "float", "str", "abs",
  "min", "max", "round", "list", "dict", "hive_step", "HIVE_ID", "_", "Scout", "Forager", "Guard",
  "HouseBee", "Hive", "Sensors", "HouseSensors", ...Object.values(USER_CLASS),
]);
const IDENT = /^[\p{L}_][\p{L}\p{N}_]*$/u;

const MATH_CONST = {
  PI: "math.pi", E: "math.e", GOLDEN_RATIO: "(1 + math.sqrt(5)) / 2", SQRT2: "math.sqrt(2)",
  SQRT1_2: "math.sqrt(1.0 / 2)", INFINITY: "float('inf')",
};

// ------------------------------------------------------------------ обход JSON

function child(block, name) {
  const inp = block.inputs?.[name];
  const b = inp ? inp.block || inp.shadow : null;
  return b && enabled(b) ? b : null;
}

function next(block) {
  const b = block.next?.block;
  return b && enabled(b) ? b : null;
}

function enabled(block) {
  if (block.enabled === false) return false;
  const reasons = block.disabledReasons || [];
  return reasons.every((r) => r === "ORPHANED_BLOCK");
}

function field(block, name) {
  return block.fields?.[name];
}

function checked(block, name) {
  const v = field(block, name);
  return v === true || v === "TRUE";
}

/** Все включённые блоки поддерева (вместе со следующими по цепочке). */
function* walk(block) {
  for (let b = block; b; b = next(b)) {
    yield b;
    for (const name of Object.keys(b.inputs || {})) {
      const c = child(b, name);
      if (c) yield* walk(c);
    }
  }
}

function fmt(template, args) {
  return template.replace(/\{(\w+)\}/g, (_, k) => (k in args ? String(args[k]) : `{${k}}`));
}

function numLiteral(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return n > 0 ? "float('inf')" : n < 0 ? "-float('inf')" : "0";
  return String(n);
}

function pyString(s) {
  return JSON.stringify(String(s ?? ""));
}

function where(kinds) {
  return kinds.map((k) => M.programWhere[k] || k).join(", ");
}

// ------------------------------------------------------------------ генератор

class Gen {
  constructor(ws, file) {
    this.ws = ws || {};
    this.file = file;
    this.errors = [];
    this.warnings = [];
    this.orphans = [];
    this.duplicates = [];
    this.lines = []; // {text, block}
    this.imports = new Set();
    this.modules = new Set();
    this.varNames = new Map(); // id → имя Python
    for (const v of this.ws.variables || []) this.varNames.set(v.id, v.name);
    this.procs = new Map(); // имя Blockly → сведения о процедуре
    this.lineRaw = null;
  }

  error(block, message) {
    if (!this.errors.some((e) => e.block === block.id && e.message === message)) {
      this.errors.push({ block: block.id, message });
    }
  }

  warn(block, message) {
    if (!this.warnings.some((e) => e.block === block.id && e.message === message)) {
      this.warnings.push({ block: block.id, message });
    }
  }

  // -------------------------------------------------------------- имена

  pyName(raw, block) {
    const name = String(raw ?? "").trim().replace(/[\s-]+/g, "_"); // «найти цветок» → найти_цветок
    if (!IDENT.test(name) || PY_KEYWORDS.has(name)) {
      this.error(block, fmt(M.badName, { name: raw }));
    } else if (RESERVED.has(name) || /^_swarmlab/.test(name)) {
      this.error(block, fmt(M.reservedName, { name: raw }));
    }
    return name || "_";
  }

  varName(block, fieldName = "VAR") {
    const f = field(block, fieldName);
    const raw = typeof f === "object" && f !== null ? (this.varNames.get(f.id) ?? f.name) : f;
    const name = this.pyName(raw, block);
    if (this.procNames?.has(name)) this.error(block, fmt(M.nameClash, { name: raw }));
    return name;
  }

  // -------------------------------------------------------------- разбор верхнего уровня

  run() {
    const tops = [...(this.ws.blocks?.blocks || [])]
      .filter((b) => enabled(b))
      .sort((a, b) => (a.y ?? 0) - (b.y ?? 0) || (a.x ?? 0) - (b.x ?? 0));
    const programs = new Map(); // тип → блок
    const defs = [];
    for (const b of tops) {
      if (b.type === "bees_program_bee" || b.type === "bees_program_hive") {
        const kind = b.type === "bees_program_hive" ? "hive" : field(b, "KIND");
        if (!ALL_SUBJECTS.includes(kind)) {
          this.error(b, fmt(M.unknownBlock, { type: `${b.type}:${kind}` }));
          continue;
        }
        if (programs.has(kind)) {
          this.duplicates.push(b.id);
          this.warn(b, fmt(M.duplicate, { kind: M.programWhere[kind] }));
          continue;
        }
        programs.set(kind, b);
      } else if (b.type === "procedures_defnoreturn" || b.type === "procedures_defreturn") {
        defs.push(b);
      } else {
        this.orphans.push(b.id); // не подключён ни к программе, ни к процедуре — не код и не ошибка
      }
    }

    this.analyzeProcs(defs);

    const body = [];
    const emitTop = (fn) => {
      if (body.length) body.push({ text: "" }, { text: "" });
      const start = this.lines.length;
      fn();
      body.push(...this.lines.splice(start));
    };
    for (const d of defs) emitTop(() => this.genProc(d));
    for (const kind of ALL_SUBJECTS) {
      const p = programs.get(kind);
      if (p) emitTop(() => this.genProgram(p, kind));
    }

    const head = [
      { text: `# ${fmt(M.header, { file: this.file })}` },
      { text: `# ${M.header2}` },
      { text: `# ${M.header3}` },
      { text: "" },
    ];
    for (const m of [...this.modules].sort()) head.push({ text: `import ${m}` });
    if (this.modules.size) head.push({ text: "" });
    if (this.imports.size) {
      head.push({ text: `from swarmlab.bees.api import ${[...this.imports].sort().join(", ")}` });
    }
    if (body.length) head.push({ text: "" }, { text: "" });
    const all = [...head, ...body];
    return {
      code: `${all.map((l) => (l.block ? `${l.text}  # block:${l.block}` : l.text)).join("\n")}\n`,
      lines: all.map((l) => l.block || null),
      orphans: this.orphans,
      duplicates: this.duplicates,
      errors: this.errors,
      warnings: this.warnings,
      ok: this.errors.length === 0,
    };
  }

  // -------------------------------------------------------------- процедуры: контекст, ожидание, рекурсия

  analyzeProcs(defs) {
    this.procNames = new Set();
    for (const d of defs) {
      const raw = field(d, "NAME");
      const info = {
        block: d, raw, name: this.pyName(raw, d), returns: d.type === "procedures_defreturn",
        params: (d.extraState?.params || []).map((p) => ({ raw: p.name, name: this.pyName(p.name, d) })),
        subjects: [...ALL_SUBJECTS], waits: false, calls: [], conflict: null,
      };
      this.procs.set(raw, info);
      this.procNames.add(info.name);
    }
    // Что использует каждая процедура сама по себе.
    for (const info of this.procs.values()) {
      const d = info.block;
      const roots = [child(d, "STACK"), child(d, "RETURN")].filter(Boolean);
      for (const r of roots) {
        for (const b of walk(r)) {
          const a = apiBlock(b.type);
          if (a) {
            const before = info.subjects;
            info.subjects = before.filter((k) => a.desc.subjects.includes(k));
            if (!info.subjects.length && !info.conflict) {
              info.conflict = { block: b, a: where(before), b: where(a.desc.subjects) };
            }
            if ((a.desc.waitable && (a.ask || checked(b, "WAIT"))) || a.desc.yields) info.waits = true;
          } else if (b.type === "procedures_callnoreturn" || b.type === "procedures_callreturn") {
            info.calls.push({ name: b.extraState?.name, block: b });
          }
        }
      }
    }
    // Вызовы: контекст и ожидание наследуются от вызываемых (до неподвижной точки — циклы допустимы).
    for (let changed = true; changed;) {
      changed = false;
      for (const info of this.procs.values()) {
        for (const c of info.calls) {
          const callee = this.procs.get(c.name);
          if (!callee) continue;
          const subj = info.subjects.filter((k) => callee.subjects.includes(k));
          if (subj.length !== info.subjects.length) {
            if (!subj.length && !info.conflict) {
              info.conflict = { block: c.block, a: where(info.subjects), b: where(callee.subjects) };
            }
            info.subjects = subj;
            changed = true;
          }
          if (callee.waits && !info.waits) {
            info.waits = true;
            changed = true;
          }
        }
      }
    }
    for (const info of this.procs.values()) {
      if (info.conflict) this.error(info.conflict.block, fmt(M.procMixed, info.conflict));
      // Как вызывать: пчела — (self, s, …), улей — (hive, …), без контекста — (…).
      const bees = info.subjects.filter((k) => k !== "hive");
      info.style = info.subjects.includes("hive") ? (bees.length ? "none" : "hive") : "bee";
      if (!info.subjects.length) info.style = "none";
    }
    // Рекурсия (DECISIONS №55): предупреждение на вызове, который замыкает цикл.
    const reach = (from, target, seen = new Set(), path = []) => {
      if (from === target) return path;
      if (seen.has(from)) return null;
      seen.add(from);
      for (const c of this.procs.get(from)?.calls || []) {
        const r = reach(c.name, target, seen, [...path, c.name]);
        if (r) return r;
      }
      return null;
    };
    for (const info of this.procs.values()) {
      for (const c of info.calls) {
        if (!this.procs.has(c.name)) continue;
        const path = reach(c.name, info.raw);
        if (path) {
          this.warn(c.block, fmt(M.recursion, { name: info.raw, path: [info.raw, c.name, ...path].join(" → ") }));
        }
      }
    }
  }

  // -------------------------------------------------------------- функции верхнего уровня

  /** Контекст функции: для кого она, её переменные, глубина циклов. */
  fnContext(kinds, opts = {}) {
    return { kinds, loop: 0, proc: opts.proc || null, assigned: new Set(opts.params || []), reads: [] };
  }

  collectAssigned(ctx, roots) {
    for (const r of roots) {
      for (const b of walk(r)) {
        if (["variables_set", "controls_forEach", "controls_for"].includes(b.type)) {
          ctx.assigned.add(this.varName(b));
        }
      }
    }
  }

  checkReads(ctx) {
    for (const { block, name, raw } of ctx.reads) {
      if (!ctx.assigned.has(name)) this.warn(block, fmt(M.unsetVariable, { name: raw }));
    }
  }

  genProgram(p, kind) {
    const doBlock = child(p, "DO");
    const ctx = this.fnContext([kind]);
    this.collectAssigned(ctx, [doBlock].filter(Boolean));
    if (kind === "hive") {
      this.emit(0, "def hive_step(hive):", p);
      this.body(ctx, doBlock, 1, p);
    } else {
      this.imports.add(BASE_CLASS[kind]);
      this.emit(0, `class ${USER_CLASS[kind]}(${BASE_CLASS[kind]}):`, p);
      this.emit(1, "def step(self, s):", p);
      this.body(ctx, doBlock, 2, p);
    }
    this.checkReads(ctx);
  }

  genProc(d) {
    const info = this.procs.get(field(d, "NAME"));
    const lead = info.style === "bee" ? ["self", "s"] : info.style === "hive" ? ["hive"] : [];
    const params = info.params.map((p) => p.name);
    const ctx = this.fnContext(info.subjects.length ? info.subjects : ALL_SUBJECTS, { proc: info, params });
    const stack = child(d, "STACK");
    const ret = child(d, "RETURN");
    this.collectAssigned(ctx, [stack, ret].filter(Boolean));
    this.emit(0, `def ${info.name}(${[...lead, ...params].join(", ")}):`, d);
    if (stack) this.stmts(ctx, stack, 1);
    if (info.returns) {
      const v = ret ? this.expr(ctx, ret, O.NONE) : "None";
      this.emit(1, `return ${v}`, d);
    } else if (!stack) {
      this.emit(1, "pass", d);
    }
    this.checkReads(ctx);
  }

  // -------------------------------------------------------------- строки

  emit(indent, text, block) {
    const id = this.lineRaw || block?.id || null;
    this.lineRaw = null;
    this.lines.push({ text: "    ".repeat(indent) + text, block: id });
  }

  body(ctx, first, indent, owner) {
    if (first) this.stmts(ctx, first, indent);
    else this.emit(indent, "pass", owner);
  }

  stmts(ctx, first, indent) {
    for (let b = first; b; b = next(b)) this.stmt(ctx, b, indent);
  }

  /** Значение входа; пустой обязательный вход — ошибка на блоке и `None` в коде. */
  val(ctx, block, name, order, required = true) {
    const c = child(block, name);
    if (!c) {
      if (required) this.error(block, fmt(M.emptyInput, { input: M.inputNames[name] || name }));
      return "None";
    }
    return this.expr(ctx, c, order);
  }

  // -------------------------------------------------------------- операторы

  stmt(ctx, b, ind) {
    const a = apiBlock(b.type);
    if (a) {
      const [code] = this.apiCode(ctx, b, a);
      const waitIt = a.desc.yields || (a.desc.waitable && checked(b, "WAIT"));
      this.emit(ind, waitIt ? `yield ${code}` : code, b);
      return;
    }
    switch (b.type) {
      case "controls_if": {
        const n = b.extraState?.elseIfCount || 0;
        for (let i = 0; i <= n; i++) {
          const cond = this.val(ctx, b, `IF${i}`, O.NONE);
          this.emit(ind, `${i ? "elif" : "if"} ${cond}:`, b);
          this.body(ctx, child(b, `DO${i}`), ind + 1, b);
        }
        if (b.extraState?.hasElse) {
          this.emit(ind, "else:", b);
          this.body(ctx, child(b, "ELSE"), ind + 1, b);
        }
        return;
      }
      case "controls_repeat_ext":
      case "controls_repeat": {
        const times = b.type === "controls_repeat"
          ? numLiteral(field(b, "TIMES")) : this.val(ctx, b, "TIMES", O.NONE);
        const n = /^\d+$/.test(times) ? times : `int(${times})`;
        this.emit(ind, `for _ in range(${n}):`, b);
        this.loopBody(ctx, b, "DO", ind);
        return;
      }
      case "controls_whileUntil": {
        const until = field(b, "MODE") === "UNTIL";
        const cond = this.val(ctx, b, "BOOL", until ? O.NOT : O.NONE);
        this.emit(ind, `while ${until ? `not ${cond}` : cond}:`, b);
        this.loopBody(ctx, b, "DO", ind);
        return;
      }
      case "controls_forEach": {
        const v = this.varName(b);
        const list = this.val(ctx, b, "LIST", O.NONE);
        this.emit(ind, `for ${v} in ${list}:`, b);
        this.loopBody(ctx, b, "DO", ind);
        return;
      }
      case "controls_for": {
        const v = this.varName(b);
        const from = this.val(ctx, b, "FROM", O.NONE);
        const to = this.val(ctx, b, "TO", O.ADD);
        const by = child(b, "BY") ? this.val(ctx, b, "BY", O.NONE) : "1";
        const intOf = (x) => (/^-?\d+$/.test(x) ? x : `int(${x})`);
        const end = /^-?\d+$/.test(to) ? String(Number(to) + 1) : `int(${to}) + 1`;
        this.emit(ind, `for ${v} in range(${intOf(from)}, ${end}${by === "1" ? "" : `, ${intOf(by)}`}):`, b);
        this.loopBody(ctx, b, "DO", ind);
        return;
      }
      case "controls_flow_statements":
        if (!ctx.loop) this.error(b, M.flowOutside);
        this.emit(ind, field(b, "FLOW") === "CONTINUE" ? "continue" : "break", b);
        return;
      case "variables_set": {
        const v = this.varName(b);
        this.emit(ind, `${v} = ${this.val(ctx, b, "VALUE", O.NONE)}`, b);
        return;
      }
      case "math_change": {
        const v = this.readVar(ctx, b);
        this.emit(ind, `${v} += ${this.val(ctx, b, "DELTA", O.NONE)}`, b);
        return;
      }
      case "text_print":
        this.emit(ind, `print(${this.val(ctx, b, "TEXT", O.NONE)})`, b);
        return;
      case "lists_getIndex":
        this.emit(ind, this.listGet(ctx, b, true)[0], b);
        return;
      case "lists_setIndex":
        this.emit(ind, this.listSet(ctx, b), b);
        return;
      case "procedures_callnoreturn":
      case "procedures_callreturn": {
        const [code, waits] = this.callCode(ctx, b);
        this.emit(ind, waits ? `yield from ${code}` : code, b);
        return;
      }
      case "procedures_ifreturn": {
        if (!ctx.proc) {
          this.error(b, M.returnOutside);
          return;
        }
        const cond = this.val(ctx, b, "CONDITION", O.NONE);
        this.emit(ind, `if ${cond}:`, b);
        if (ctx.proc.returns) {
          const v = child(b, "VALUE") ? this.val(ctx, b, "VALUE", O.NONE) : "None";
          this.emit(ind + 1, `return ${v}`, b);
        } else this.emit(ind + 1, "return", b);
        return;
      }
      case "bees_python_line": {
        const code = String(field(b, "CODE") ?? "").replace(/[\r\n]+/g, " ").trim();
        if (!code) this.error(b, M.emptyCode);
        this.emit(ind, code || "pass", b);
        return;
      }
      case "bees_dict_set": {
        const d = this.val(ctx, b, "dict", O.MEMBER);
        const k = this.val(ctx, b, "key", O.NONE);
        this.emit(ind, `${d}[${k}] = ${this.val(ctx, b, "value", O.NONE)}`, b);
        return;
      }
      default:
        this.error(b, fmt(M.unknownBlock, { type: b.type }));
        this.emit(ind, "pass", b);
    }
  }

  loopBody(ctx, b, name, ind) {
    ctx.loop += 1;
    this.body(ctx, child(b, name), ind + 1, b);
    ctx.loop -= 1;
  }

  // -------------------------------------------------------------- выражения

  /** Код выражения в скобках, если оно связывает слабее, чем нужно снаружи. */
  expr(ctx, b, outer) {
    const [code, inner] = this.exprOrder(ctx, b);
    const wrap = inner > outer || (inner === outer && inner !== O.ATOMIC && inner !== O.MEMBER
      && inner !== O.NONE);
    return wrap ? `(${code})` : code;
  }

  readVar(ctx, b) {
    const name = this.varName(b);
    const f = field(b, "VAR");
    ctx.reads.push({ block: b, name, raw: typeof f === "object" && f ? (this.varNames.get(f.id) ?? f.name) : f });
    return name;
  }

  exprOrder(ctx, b) {
    const a = apiBlock(b.type);
    if (a) {
      const [code, order] = this.apiCode(ctx, b, a);
      return a.ask ? [`(yield ${code})`, O.ATOMIC] : [code, order];
    }
    switch (b.type) {
      case "logic_boolean":
        return [field(b, "BOOL") === "FALSE" ? "False" : "True", O.ATOMIC];
      case "logic_null":
        return ["None", O.ATOMIC];
      case "logic_compare": {
        const op = { EQ: "==", NEQ: "!=", LT: "<", LTE: "<=", GT: ">", GTE: ">=" }[field(b, "OP")] || "==";
        const A = child(b, "A");
        const B = child(b, "B");
        const isNull = (x) => x?.type === "logic_null";
        if ((op === "==" || op === "!=") && (isNull(A) || isNull(B))) {
          const other = isNull(A) ? "B" : "A";
          const v = this.val(ctx, b, other, O.REL);
          return [`${v} ${op === "==" ? "is" : "is not"} None`, O.REL];
        }
        return [`${this.val(ctx, b, "A", O.REL)} ${op} ${this.val(ctx, b, "B", O.REL)}`, O.REL];
      }
      case "logic_operation": {
        const and = field(b, "OP") !== "OR";
        const ord = and ? O.AND : O.OR;
        return [`${this.val(ctx, b, "A", ord)} ${and ? "and" : "or"} ${this.val(ctx, b, "B", ord)}`, ord];
      }
      case "logic_negate":
        return [`not ${this.val(ctx, b, "BOOL", O.NOT)}`, O.NOT];
      case "logic_ternary":
        return [`${this.val(ctx, b, "THEN", O.COND)} if ${this.val(ctx, b, "IF", O.COND)} else ${this.val(ctx, b, "ELSE", O.COND)}`, O.COND];
      case "math_number": {
        const s = numLiteral(field(b, "NUM"));
        return [s, s.startsWith("-") ? O.UNARY : O.ATOMIC];
      }
      case "math_arithmetic": {
        const [op, ord] = {
          ADD: ["+", O.ADD], MINUS: ["-", O.ADD], MULTIPLY: ["*", O.MUL], DIVIDE: ["/", O.MUL], POWER: ["**", O.EXP],
        }[field(b, "OP")] || ["+", O.ADD];
        return [`${this.val(ctx, b, "A", ord)} ${op} ${this.val(ctx, b, "B", ord)}`, ord];
      }
      case "math_single": {
        const op = field(b, "OP");
        if (op === "NEG") return [`-${this.val(ctx, b, "NUM", O.UNARY)}`, O.UNARY];
        if (op === "POW10") return [`10 ** ${this.val(ctx, b, "NUM", O.EXP)}`, O.EXP];
        if (op === "ABS") return [`abs(${this.val(ctx, b, "NUM", O.NONE)})`, O.MEMBER];
        this.modules.add("math");
        const fn = { ROOT: "sqrt", LN: "log", LOG10: "log10", EXP: "exp" }[op] || "sqrt";
        return [`math.${fn}(${this.val(ctx, b, "NUM", O.NONE)})`, O.MEMBER];
      }
      case "math_trig": {
        this.modules.add("math");
        const op = field(b, "OP");
        const x = this.val(ctx, b, "NUM", O.MUL);
        if (["SIN", "COS", "TAN"].includes(op)) return [`math.${op.toLowerCase()}(math.radians(${x}))`, O.MEMBER];
        return [`math.degrees(math.${op.toLowerCase()}(${x}))`, O.MEMBER];
      }
      case "math_constant": {
        const c = MATH_CONST[field(b, "CONSTANT")] || "math.pi";
        if (c.includes("math.")) this.modules.add("math");
        return [c, c.includes(" ") ? O.MUL : O.MEMBER];
      }
      case "math_round": {
        const op = field(b, "OP");
        const x = this.val(ctx, b, "NUM", O.NONE);
        if (op === "ROUND") return [`round(${x})`, O.MEMBER];
        this.modules.add("math");
        return [`math.${op === "ROUNDUP" ? "ceil" : "floor"}(${x})`, O.MEMBER];
      }
      case "math_modulo":
        return [`${this.val(ctx, b, "DIVIDEND", O.MUL)} % ${this.val(ctx, b, "DIVISOR", O.MUL)}`, O.MUL];
      case "math_constrain":
        return [`min(max(${this.val(ctx, b, "VALUE", O.NONE)}, ${this.val(ctx, b, "LOW", O.NONE)}), ${this.val(ctx, b, "HIGH", O.NONE)})`, O.MEMBER];
      case "math_random_int":
        this.modules.add("random");
        return [`random.randint(${this.val(ctx, b, "FROM", O.NONE)}, ${this.val(ctx, b, "TO", O.NONE)})`, O.MEMBER];
      case "math_random_float":
        this.modules.add("random");
        return ["random.random()", O.MEMBER];
      case "text":
        return [pyString(field(b, "TEXT")), O.ATOMIC];
      case "text_join": {
        const n = b.extraState?.itemCount ?? 0;
        const parts = [];
        for (let i = 0; i < n; i++) {
          const c = child(b, `ADD${i}`);
          if (!c) continue;
          const v = this.val(ctx, b, `ADD${i}`, O.NONE);
          parts.push(c.type === "text" ? v : `str(${v})`);
        }
        if (!parts.length) return ['""', O.ATOMIC];
        return [parts.join(" + "), parts.length > 1 ? O.ADD : O.MEMBER];
      }
      case "lists_create_empty":
        return ["[]", O.ATOMIC];
      case "lists_create_with": {
        const n = b.extraState?.itemCount ?? 0;
        const items = [];
        for (let i = 0; i < n; i++) items.push(this.val(ctx, b, `ADD${i}`, O.NONE, false));
        return [`[${items.join(", ")}]`, O.ATOMIC];
      }
      case "lists_length":
        return [`len(${this.val(ctx, b, "VALUE", O.NONE)})`, O.MEMBER];
      case "lists_isEmpty":
        return [`not len(${this.val(ctx, b, "VALUE", O.NONE)})`, O.NOT];
      case "lists_getIndex":
        return this.listGet(ctx, b, false);
      case "variables_get":
        return [this.readVar(ctx, b), O.ATOMIC];
      case "procedures_callreturn":
      case "procedures_callnoreturn": {
        const [code, waits] = this.callCode(ctx, b);
        return waits ? [`(yield from ${code})`, O.ATOMIC] : [code, O.MEMBER];
      }
      case "bees_python_expr": {
        const code = String(field(b, "CODE") ?? "").replace(/[\r\n]+/g, " ").trim();
        if (!code) this.error(b, M.emptyCode);
        this.lineRaw ||= b.id; // синтаксическая ошибка в этой строке — скорее всего, здесь
        return [code ? `(${code})` : "None", O.ATOMIC];
      }
      case "bees_dict_get":
        return [`${this.val(ctx, b, "dict", O.MEMBER)}.get(${this.val(ctx, b, "key", O.NONE)})`, O.MEMBER];
      case "bees_literal_Kind":
      case "bees_literal_Weather":
      case "bees_literal_Task":
        return [pyString(field(b, "VALUE")), O.ATOMIC];
      default:
        this.error(b, fmt(M.unknownBlock, { type: b.type }));
        return ["None", O.ATOMIC];
    }
  }

  // -------------------------------------------------------------- блоки API

  apiCode(ctx, b, { desc }) {
    const bad = ctx.proc ? [] : ctx.kinds.filter((k) => !desc.subjects.includes(k));
    if (bad.length) this.error(b, fmt(M.wrongSubject, { where: where(bad) }));
    if (desc.api === "HIVE_ID" || desc.member === "function") this.imports.add(desc.name);
    let target = "";
    if (desc.target === "obj") target = this.val(ctx, b, "obj", O.MEMBER);
    else if (desc.target) target = desc.target;
    const ref = target ? `${target}.${desc.name}` : desc.name;
    if (desc.member === "field" || desc.member === "property" || desc.member === "const") return [ref, O.MEMBER];
    const args = [];
    // Необязательные — по имени (`fly_to(x, y, speed=3)`); у `wait(5)` — по порядку, как в примерах.
    let gap = desc.member !== "function";
    for (const p of desc.params) {
      let code = null;
      if (p.options) {
        const v = field(b, p.name);
        if (v !== undefined && v !== null) code = pyString(v);
      } else if (child(b, p.name)) {
        code = this.val(ctx, b, p.name, O.NONE);
      }
      if (code === null) {
        if (p.required) {
          this.error(b, fmt(M.emptyInput, { input: p.name }));
          args.push("None");
        } else gap = true;
        continue;
      }
      if (p.vararg) args.push(`*${code.startsWith("(") || /^[\w.]+$|^\[.*\]$/.test(code) ? code : `(${code})`}`);
      else if (p.required || !gap) args.push(code);
      else args.push(`${p.name}=${code}`);
    }
    return [`${ref}(${args.join(", ")})`, O.MEMBER];
  }

  callCode(ctx, b) {
    const raw = b.extraState?.name;
    const info = this.procs.get(raw);
    if (!info) {
      this.error(b, fmt(M.unknownProc, { name: raw }));
      return ["None", false];
    }
    if (!ctx.proc) {
      const bad = ctx.kinds.filter((k) => !info.subjects.includes(k));
      if (bad.length) this.error(b, fmt(M.procWrongSubject, { name: raw, where: where(bad) }));
    }
    const lead = info.style === "bee" ? ["self", "s"] : info.style === "hive" ? ["hive"] : [];
    if (ctx.proc && info.style !== "none" && ctx.proc.style !== info.style) {
      this.error(b, fmt(M.procWrongSubject, { name: raw, where: where(ctx.kinds) }));
    }
    const args = info.params.map((_, i) => this.val(ctx, b, `ARG${i}`, O.NONE));
    return [`${info.name}(${[...lead, ...args].join(", ")})`, info.waits];
  }

  // -------------------------------------------------------------- списки (номера с 1, как в Blockly)

  listIndex(ctx, b, where_) {
    if (where_ === "FIRST") return "0";
    if (where_ === "LAST") return "-1";
    const at = this.val(ctx, b, "AT", O.ADD);
    if (where_ === "FROM_END") return /^\d+$/.test(at) ? `-${at}` : `-${this.val(ctx, b, "AT", O.UNARY)}`;
    return /^\d+$/.test(at) ? String(Number(at) - 1) : `${at} - 1`;
  }

  listGet(ctx, b, asStatement) {
    const mode = field(b, "MODE") || "GET";
    const where_ = field(b, "WHERE") || "FROM_START";
    const list = this.val(ctx, b, "VALUE", O.MEMBER);
    if (where_ === "RANDOM") this.modules.add("random");
    if (mode === "GET" && !asStatement) {
      if (where_ === "RANDOM") return [`random.choice(${list})`, O.MEMBER];
      return [`${list}[${this.listIndex(ctx, b, where_)}]`, O.MEMBER];
    }
    const idx = where_ === "RANDOM" ? `random.randrange(len(${list}))`
      : where_ === "LAST" ? "" : this.listIndex(ctx, b, where_);
    return [`${list}.pop(${idx})`, O.MEMBER];
  }

  listSet(ctx, b) {
    const mode = field(b, "MODE") || "SET";
    const where_ = field(b, "WHERE") || "FROM_START";
    const list = this.val(ctx, b, "LIST", O.MEMBER);
    const v = this.val(ctx, b, "TO", O.NONE);
    if (where_ === "RANDOM") this.modules.add("random");
    if (mode === "INSERT") {
      if (where_ === "LAST") return `${list}.append(${v})`;
      const idx = where_ === "RANDOM" ? `random.randrange(len(${list}) + 1)` : this.listIndex(ctx, b, where_);
      return `${list}.insert(${idx}, ${v})`;
    }
    const idx = where_ === "RANDOM" ? `random.randrange(len(${list}))` : this.listIndex(ctx, b, where_);
    return `${list}[${idx}] = ${v}`;
  }
}

/**
 * Сгенерировать Python из рабочей области.
 * @param {object} workspace JSON `Blockly.serialization.workspaces.save`
 * @param {{file?: string}} opts имя файла блоков — для шапки
 * @returns {{code: string, lines: (string|null)[], orphans: string[], duplicates: string[],
 *   errors: {block: string, message: string}[], warnings: {block: string, message: string}[], ok: boolean}}
 */
export function generate(workspace, opts = {}) {
  return new Gen(workspace, opts.file || "blocks.json").run();
}

/** Id блока по строке сгенерированного кода (с 1) — из комментария `# block:<id>`. */
export function blockAtLine(code, line) {
  const text = code.split("\n")[line - 1] || "";
  const m = /# block:(\S+)\s*$/.exec(text);
  return m ? m[1] : null;
}
