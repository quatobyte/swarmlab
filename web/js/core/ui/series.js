// Серия матчей (M7c, DECISIONS №66): прогресс, таблица результатов, итог, список прошлых серий.
// Один компонент для меню и редактора. Колонки таблицы и ульи приходят в series.json от ядра
// и модуля — здесь нет знаний о пчёлах. Прогресс — опросом GET /api/series/{id} раз в секунду.

import { api } from "../api.js";

const ERROR_KEYS = ["agent_errors", "missed", "over_budget"];
const DONE_STATES = ["finished", "stopped", "interrupted", "error"];
const STATE_RU = {
  running: "идёт", finished: "закончена", stopped: "остановлена", interrupted: "прервана", error: "ошибка",
};
const POLL_MS = 1000;

export function hasCodeErrors(row) {
  return !!row && (ERROR_KEYS.some((k) => Number(row[k] || 0) > 0) || !!row.load_error);
}

function fmt(v) {
  if (v === undefined || v === null || v === "") return "—";
  if (typeof v === "boolean") return v ? "да" : "нет";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** Окно серии поверх контейнера (меню — вся страница, редактор — вьюер). */
export class SeriesView {
  /** onWatch(seriesId, seed, title) — открыть реплей матча; onClose() — окно закрыто. */
  constructor({ onWatch, onClose } = {}) {
    this.onWatch = onWatch;
    this.onClose = onClose;
    this.id = null;
    this.data = null;
    this.timer = 0;
    this.root = el("div", "series-overlay");
    this.root.hidden = true;
    this.box = el("div", "series-box");
    this.root.appendChild(this.box);
  }

  get open() {
    return !this.root.hidden;
  }

  /** Показать серию `id` в `container`; идущая серия обновляется сама. */
  async show(id, container) {
    if (this.root.parentElement !== container) container.appendChild(this.root);
    this.id = id;
    this.root.hidden = false;
    this.box.innerHTML = '<p class="muted">Загрузка серии…</p>';
    await this.refresh();
  }

  /** Запустить серию (тело POST /api/series) и показать её. */
  async start(body, container) {
    const info = await api.startSeries(body);
    await this.show(info.id, container);
    return info;
  }

  hide() {
    clearTimeout(this.timer);
    this.root.hidden = true;
    this.onClose?.();
  }

  async refresh() {
    clearTimeout(this.timer);
    if (!this.id || this.root.hidden) return;
    try {
      this.data = await api.series(this.id);
    } catch (e) {
      this.box.innerHTML = "";
      this.box.append(el("p", "error", `Серия недоступна: ${e.message}`), this._closeButton());
      return;
    }
    this.render();
    if (!DONE_STATES.includes(this.data.state)) this.timer = setTimeout(() => this.refresh(), POLL_MS);
  }

  _closeButton() {
    const b = el("button", "btn", "Закрыть");
    b.onclick = () => this.hide();
    return b;
  }

  render() {
    const d = this.data;
    const running = !DONE_STATES.includes(d.state);
    const box = this.box;
    box.innerHTML = "";

    const head = el("div", "series-head");
    const title = el("div", "series-title");
    title.append(el("b", "", `Серия · ${d.project}`),
      el("span", "muted small", ` ${d.n} матчей, seed ${d.start_seed}…${d.start_seed + d.n - 1}, `
        + `${d.profile}, ${fmt(d.duration_s)} с`));
    head.appendChild(title);
    head.appendChild(el("span", "spacer"));
    if (running) {
      const stop = el("button", "btn danger", "■ Остановить серию");
      stop.onclick = async () => {
        stop.disabled = true;
        stop.textContent = "Останавливается…";
        try {
          await api.stopSeries(d.id);
        } catch (e) {
          stop.textContent = `Не остановлена: ${e.message}`;
        }
      };
      head.appendChild(stop);
    }
    head.appendChild(this._closeButton());
    box.appendChild(head);

    // Прогресс и ульи
    const status = el("div", "series-status");
    if (running) {
      const current = Math.min(d.n, d.done + Math.max(1, (d.running || []).length));
      status.append(el("span", "badge running", `матч ${current} из ${d.n}`));
      const bar = el("div", "series-bar");
      const fill = el("i");
      fill.style.width = `${(100 * d.done) / d.n}%`;
      bar.appendChild(fill);
      status.appendChild(bar);
    } else {
      status.append(el("span", `badge ${d.state === "finished" ? "running" : "error"}`, STATE_RU[d.state] || d.state));
      status.append(el("span", "muted small", ` сыграно ${d.done} из ${d.n}`));
    }
    box.appendChild(status);
    if (d.error) box.appendChild(el("pre", "error small series-error", d.error));
    const hives = el("div", "series-hives small");
    for (const h of d.hives || []) {
      const row = el("div", h.team === d.team ? "focus" : "");
      const script = String(h.script || "—").split(/[\\/]/).pop();
      row.append(el("b", "", `Улей ${h.team + 1}`), el("span", "", ` ${script}`),
        el("span", "muted", ` · sha256 ${(h.sha256 || "").slice(0, 10)}…`));
      if (h.team === d.team) row.append(el("span", "muted", " · в таблице"));
      hives.appendChild(row);
    }
    box.appendChild(hives);

    // Таблица
    const cols = d.columns || [];
    const s = d.summary || {};
    const wrap = el("div", "series-table-wrap");
    const table = el("table", "series-table");
    const thead = el("tr");
    thead.append(el("th", "", "seed"), ...cols.map((c) => el("th", "", c.title)), el("th", "", ""));
    table.appendChild(thead);
    for (const m of d.matches || []) {
      const row = (m.teams || {})[String(d.team)];
      const tr = el("tr");
      if (m.state !== "finished") tr.className = "match-error";
      else if (hasCodeErrors(row)) tr.className = "code-errors";
      if (m.seed === s.worst_seed) tr.classList.add("worst");
      const seed = el("td", "seed", String(m.seed));
      if (m.seed === s.worst_seed) seed.appendChild(el("span", "tag", "худший"));
      if (m.winner === d.team) seed.appendChild(el("span", "tag win", "победа"));
      if (hasCodeErrors(row)) {
        seed.title = `Ошибки кода: исключений ${row.agent_errors}, пропущено тиков ${row.missed}, `
          + `сверх бюджета ${row.over_budget}${row.load_error ? ", скрипт не загрузился" : ""}`;
      }
      tr.appendChild(seed);
      if (m.state !== "finished") {
        const td = el("td", "muted", "матч не доигран (ошибка процесса)");
        td.colSpan = cols.length;
        td.title = m.error || "";
        tr.appendChild(td);
      } else {
        for (const c of cols) tr.appendChild(el("td", ERROR_KEYS.includes(c.key) && row?.[c.key] ? "bad" : "", fmt(row?.[c.key])));
      }
      const act = el("td");
      if (m.replay) {
        const watch = el("button", "btn small", "Смотреть");
        watch.title = `Открыть реплей s${m.seed}.swr с перемоткой`;
        watch.onclick = () => this.onWatch?.(d.id, m.seed, `Серия ${d.project} · seed ${m.seed}`);
        act.appendChild(watch);
      }
      tr.appendChild(act);
      table.appendChild(tr);
    }
    if ((d.matches || []).length) {
      const tr = el("tr", "means");
      tr.append(el("td", "", "среднее"), ...cols.map((c) => el("td", "", fmt(s.means?.[c.key]))), el("td"));
      table.appendChild(tr);
    }
    wrap.appendChild(table);
    box.appendChild(wrap);
    if (!(d.matches || []).length) box.appendChild(el("p", "muted small", "Первый матч ещё идёт…"));

    const sum = el("div", "series-summary");
    sum.append(el("span", "", `Побед: ${s.wins ?? 0} из ${s.played ?? 0}`),
      el("span", s.with_code_errors ? "bad" : "", `С ошибками кода: ${s.with_code_errors ?? 0}`),
      el("span", "", `Худший seed: ${s.worst_seed ?? "—"}`));
    if (s.worst_seed !== null && s.worst_seed !== undefined) {
      const w = el("button", "btn small", "Смотреть худший");
      w.onclick = () => this.onWatch?.(d.id, s.worst_seed, `Серия ${d.project} · seed ${s.worst_seed}`);
      sum.appendChild(w);
    }
    box.appendChild(sum);
    box.appendChild(el("p", "muted small", `Файлы: replays/series/${d.id}/ — реплеи s<seed>.swr, series.json, `
      + "results.csv (Excel; в pandas — sep=\";\", decimal=\",\")"));
  }
}

/** Список прошлых серий в меню. onOpen(id) — открыть таблицу. */
export function renderSeriesList(box, list, onOpen) {
  box.innerHTML = "";
  if (!list.length) {
    box.appendChild(el("p", "muted small", "Серий пока нет — запустите «Серия…» в форме матча выше."));
    return;
  }
  for (const s of list.slice(0, 30)) {
    const row = el("div", "row");
    row.append(el("span", "name", s.project || s.id));
    const when = String(s.created || "").replace("T", " ").slice(0, 16);
    const res = s.played ? `, побед ${s.wins ?? 0} / с ошибками ${s.with_code_errors ?? 0}` : "";
    row.append(el("span", "muted small",
      `${when} · ${s.done}/${s.n} матчей, seed от ${s.start_seed}${res}`
      + (s.state === "finished" ? "" : ` · ${STATE_RU[s.state] || s.state}`)));
    const b = el("button", "btn", "Таблица");
    b.onclick = () => onOpen(s.id);
    row.appendChild(b);
    box.appendChild(row);
  }
}
