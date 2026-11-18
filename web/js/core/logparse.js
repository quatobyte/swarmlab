// Лог программы команды: трассировка Python → одна запись об ошибке (DECISIONS №106).
//
// Раннер пишет ошибку несколькими строками: заголовок («Ошибка: …» или «Скрипт … не загрузился»),
// «Traceback (most recent call last):», кадры `File "…", line N`, строки кода с пометками и
// стрелками `~~~^^^`, в конце — строка исключения. Игроку из этого нужно только «кто», «где» и
// «что»: `LogGrouper` собирает такие строки в запись `{kind: "error", title, frames, message}`,
// остальные строки отдаёт как есть (`{kind: "line", text}`). Модуль здесь не нужен: формат
// трассировки — Python. Без DOM — проверяется под Node (tests/web/logparse_unit.mjs).

const TITLE = /^(?:Ошибка: |Скрипт \S.* не загрузился)/;
const TRACEBACK = /^Traceback \(most recent call last\):/;
const FRAME = /^\s*File "(.+)", line (\d+)/;
const EXCEPTION = /^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning))\b(?::.*)?$/;

/** Имя файла из пути (Windows и POSIX). */
export function baseName(path) {
  return String(path || "").split(/[\\/]/).pop();
}

export class LogGrouper {
  constructor() {
    this.cur = null; // собираемая ошибка: {title, frames}
  }

  /** Строка лога → готовые записи (обычно одна или ни одной, пока ошибка собирается). */
  push(text) {
    const out = [];
    if (this.cur) {
      if (TRACEBACK.test(text)) return out;
      const frame = FRAME.exec(text);
      if (frame) {
        this.cur.frames.push({ file: baseName(frame[1]), line: Number(frame[2]) });
        return out;
      }
      if (EXCEPTION.test(text)) {
        out.push({ kind: "error", ...this.cur, message: text });
        this.cur = null;
        return out;
      }
      if (/^\s/.test(text) || text === "") return out; // код строки и стрелки под ним
      out.push(this._close()); // ошибка оборвалась без строки исключения
    }
    const frame = FRAME.exec(text);
    if (TITLE.test(text) || TRACEBACK.test(text) || frame) {
      this.cur = { title: TITLE.test(text) ? text : "", frames: [] };
      if (frame) this.cur.frames.push({ file: baseName(frame[1]), line: Number(frame[2]) });
      return out;
    }
    if (EXCEPTION.test(text)) out.push({ kind: "error", title: "", frames: [], message: text });
    else out.push({ kind: "line", text });
    return out;
  }

  /** Недособранная ошибка — записью без строки исключения (конец лога, новая строка не из неё). */
  flush() {
    return this.cur ? [this._close()] : [];
  }

  _close() {
    const { title, frames } = this.cur;
    this.cur = null;
    // Строка «Ошибка: …» без трассировки — это мог напечатать и сам игрок: оставляем как есть.
    if (!frames.length) return { kind: "line", text: title };
    return { kind: "error", title, frames, message: "" };
  }
}
