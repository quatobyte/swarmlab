// Проект `.swarm` (M7c, DECISIONS №63): только рой — один скрипт улья, без настроек матча.
// JSON {format: 1, name, created, mode: "blocks" | "python", code, blocks: {рабочая область} | null}.
// Чистые функции без DOM: работают и под Node (tests/web/project_check.mjs).
// Те же проверки формата — на сервере (src/swarmlab/server/projects.py).

export const PROJECT_FORMAT = 1;
export const PROJECT_EXT = ".swarm";
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const WIN_RESERVED = new Set(["con", "prn", "aux", "nul",
  ...[1, 2, 3, 4, 5, 6, 7, 8, 9].flatMap((i) => [`com${i}`, `lpt${i}`])]);

/** Ошибка формата файла проекта (сообщение — для человека). */
export class ProjectError extends Error {}

/** `my_bees.py` → `my_bees`. */
export function projectName(scriptName) {
  return String(scriptName).replace(/\.py$/, "");
}

/** Местное время без часового пояса: `2026-10-23T12:00:00`. */
function localIso(date) {
  const p = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:`
    + `${p(date.getMinutes())}:${p(date.getSeconds())}`;
}

/** Объект проекта из скрипта редактора. `blocks` — рабочая область (только в режиме блоков). */
export function makeProject({ name, mode, code, blocks = null, created = null }) {
  const blockMode = mode === "blocks";
  return {
    format: PROJECT_FORMAT,
    name: projectName(name),
    created: created || localIso(new Date()),
    mode: blockMode ? "blocks" : "python",
    code,
    blocks: blockMode ? blocks : null,
  };
}

/** Текст файла `.swarm`. */
export function projectText(project) {
  return `${JSON.stringify(project, null, 1)}\n`;
}

/** Разобрать и проверить файл проекта; ошибка — `ProjectError` с понятным текстом. */
export function parseProject(text) {
  let data;
  try {
    data = JSON.parse(String(text).replace(/^﻿/, ""));
  } catch (e) {
    throw new ProjectError(`Это не файл проекта .swarm: битый JSON (${e.message})`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new ProjectError("Это не файл проекта .swarm: нужен объект JSON");
  }
  if (data.format !== PROJECT_FORMAT) {
    throw new ProjectError(`Неизвестный формат проекта ${JSON.stringify(data.format ?? null)}: `
      + `эта версия SwarmLab открывает только format ${PROJECT_FORMAT}`);
  }
  if (typeof data.code !== "string") throw new ProjectError("В проекте нет кода (поле code)");
  if (typeof data.name !== "string" || !NAME_RE.test(data.name) || WIN_RESERVED.has(data.name.toLowerCase())) {
    throw new ProjectError(`Недопустимое имя проекта ${JSON.stringify(data.name ?? null)}: только латинские `
      + "буквы, цифры и _, начинается с буквы (например, my_bees)");
  }
  if (data.mode !== "blocks" && data.mode !== "python") {
    throw new ProjectError(`Неизвестный режим проекта ${JSON.stringify(data.mode ?? null)}: нужен blocks или python`);
  }
  const blocks = data.mode === "blocks" ? data.blocks : null;
  if (data.mode === "blocks" && (!blocks || typeof blocks !== "object" || Array.isArray(blocks))) {
    throw new ProjectError("Проект в режиме блоков, но блоков в нём нет (поле blocks)");
  }
  return {
    format: PROJECT_FORMAT,
    name: data.name,
    created: typeof data.created === "string" ? data.created : null,
    mode: data.mode,
    code: data.code.replace(/\r\n/g, "\n"),
    blocks,
  };
}
