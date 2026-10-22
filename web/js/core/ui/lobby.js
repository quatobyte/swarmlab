// Стартовое окно: новый матч, идущие матчи, реплеи с сервера и с диска.

import { api } from "../api.js";

const $ = (id) => document.getElementById(id);

function fmtSize(bytes) {
  return bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1e3))} КБ`;
}

function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const STATE_RU = {
  starting: "запускается", running: "идёт", paused: "пауза",
  finished: "закончен", stopped: "остановлен", error: "ошибка",
};

export class Lobby {
  /** handlers: {startMatch(body), openLive(id), openReplay(id, name), openFile(file)} */
  constructor(handlers) {
    this.h = handlers;
    this.el = $("lobby");
    this.configs = [];
    $("lobby-start").addEventListener("click", () => this._start());
    $("lobby-match").addEventListener("change", () => this._describe());
    $("lobby-file").addEventListener("change", (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (f) this.h.openFile(f);
    });
  }

  async show() {
    this.el.hidden = false;
    this.error(null);
    await Promise.all([this._loadConfigs(), this._loadLive(), this._loadReplays()]);
  }

  hide() {
    this.el.hidden = true;
  }

  error(text) {
    const el = $("lobby-error");
    el.hidden = !text;
    el.textContent = text || "";
  }

  async _loadConfigs() {
    try {
      this.configs = await api.configs();
    } catch (e) {
      this.error(`Сервер недоступен: ${e.message}`);
      return;
    }
    const sel = $("lobby-match");
    const prev = sel.value;
    sel.innerHTML = "";
    for (const c of this.configs) {
      const opt = document.createElement("option");
      opt.value = c.name;
      opt.textContent = `${c.name} — ${c.profile ?? "?"}, ${c.duration_s ?? "?"} с`;
      sel.appendChild(opt);
    }
    if (prev) sel.value = prev;
    this._describe();
  }

  _describe() {
    const c = this.configs.find((x) => x.name === $("lobby-match").value);
    $("lobby-match-desc").textContent = c ? c.description : "";
    $("lobby-seed").placeholder = c && c.seed != null ? `из файла: ${c.seed}` : "из файла";
  }

  async _loadLive() {
    let list = [];
    try {
      list = await api.matches();
    } catch {
      return;
    }
    const live = list.filter((m) => !["finished", "stopped", "error"].includes(m.state));
    $("lobby-live-section").hidden = live.length === 0;
    const box = $("lobby-live");
    box.innerHTML = "";
    for (const m of live) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="name"></span><span class="muted small"></span>`;
      row.querySelector(".name").textContent = `${m.match} · seed ${m.seed}`;
      row.querySelector(".muted").textContent =
        `${STATE_RU[m.state] || m.state}, ${fmtTime(m.time)} из ${fmtTime(m.duration_s)}`;
      const btn = document.createElement("button");
      btn.className = "btn primary";
      btn.textContent = "Смотреть";
      btn.onclick = () => this.h.openLive(m.id);
      row.appendChild(btn);
      box.appendChild(row);
    }
  }

  async _loadReplays() {
    const box = $("lobby-replays");
    let list = [];
    try {
      list = await api.replays();
    } catch {
      box.innerHTML = `<p class="muted small">Список реплеев недоступен.</p>`;
      return;
    }
    box.innerHTML = list.length ? "" : `<p class="muted small">Реплеев пока нет — запустите матч.</p>`;
    for (const r of list.slice(0, 12)) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="name"></span><span class="muted small"></span>`;
      row.querySelector(".name").textContent = r.id;
      row.querySelector(".muted").textContent = `${fmtSize(r.size)} · ${r.modified.replace("T", " ")}`;
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = "Открыть";
      btn.onclick = () => this.h.openReplay(r.id, r.name);
      row.appendChild(btn);
      box.appendChild(row);
    }
  }

  async _start() {
    const body = { match: $("lobby-match").value, speed: Number($("lobby-speed").value) };
    const seed = $("lobby-seed").value.trim();
    if (seed !== "") body.seed = Number(seed);
    try {
      const live = (await api.matches()).filter((m) => ["starting", "running", "paused"].includes(m.state));
      if (live.length && !confirm(`Сейчас идёт матч ${live[0].match}. Остановить его и запустить новый?`)) return;
      $("lobby-start").disabled = true;
      await this.h.startMatch(body);
    } catch (e) {
      this.error(e.message);
    } finally {
      $("lobby-start").disabled = false;
    }
  }
}

export { fmtTime, STATE_RU };
