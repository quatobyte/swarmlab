// Модули этой ветки (DECISIONS №98): имя модуля → загрузчики вьюера и части редактора.
// Ядро (js/core/) знает модули только отсюда. В master список пуст; в ветке модуля —
// одна запись его модуля. Файл меняется только в ветке модуля.

// Пример записи в ветке модуля:
//   bees: { viewer: () => import("./bees/index.js"), editor: () => import("./bees/editor.js") },
export const MODULES = {};

/** Модуль редактора и формы матча — первый в списке (в ветке модуля он один). */
export const DEFAULT_MODULE = Object.keys(MODULES)[0] ?? null;

/** Часть редактора модуля по умолчанию (подсказки, форма матча, блоки). */
export async function loadModuleEditor() {
  if (!DEFAULT_MODULE) throw new Error("в этой ветке нет модуля (ядро без модулей — master)");
  return MODULES[DEFAULT_MODULE].editor();
}
