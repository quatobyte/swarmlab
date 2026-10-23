// Точка входа вьюера: лобби → источник кадров (живой матч или реплей) → вьюер модуля.
// Живой режим и реплей рисуются одним кодом: вьюер получает header и sample() от источника.

import { api } from "./api.js";
import { LiveSource } from "./live.js";
import { ReplaySource } from "./replay.js";
import { QUALITY, QUALITY_ORDER, Stage, saveQuality } from "./stage.js";
import { Editor } from "./ui/editor.js";
import { FpsMeter, isTyping } from "./ui/fps.js";
import { Lobby, STATE_RU, fmtTime } from "./ui/lobby.js";
import { SeriesView } from "./ui/series.js";

/** Вьюеры модулей: имя модуля из header.module → загрузчик. */
const MODULES = {
  bees: () => import("../modules/bees/index.js"),
};
const LIVE_SPEEDS = [0.5, 1, 2, 4, 8];
const REPLAY_SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];

const $ = (id) => document.getElementById(id);

const stage = new Stage($("stage"));
const fps = new FpsMeter($("fps"), stage.renderer, () => stage.quality.fps);
stage.afterRender = (dt) => fps.tick(dt);
let session = null;
window.swarmlab = { stage, fps, get session() { return session; } }; // для отладки из консоли

// ------------------------------------------------------------------ сессия

class Session {
  constructor(source, title) {
    this.source = source;
    this.title = title;
    this.viewer = null;
    this.seeking = false;
    source.on("header", (h) => this._onHeader(h));
    source.on("events", (ev) => this.viewer?.onEvents(ev));
    source.on("status", (st) => this._onStatus(st));
    source.on("footer", (f) => this._onFooter(f));
    source.on("end", (f) => this._onFooter(f));
    source.on("seek", () => this.viewer?.reset());
    source.on("close", () => this._onClose());
    source.on("error", (msg) => showBanner(msg, [["Меню", toLobby]]));
    if (source.header) this._onHeader(source.header);
  }

  async _onHeader(header) {
    if (this.viewer) return;
    const load = MODULES[header.module];
    if (!load) {
      showBanner(`Вьюер для модуля «${header.module}» не найден`, [["Меню", toLobby]]);
      return;
    }
    const mod = await load();
    if (this.closed) return;
    this.viewer = mod.createViewer({ stage, header });
    $("info-title").textContent = this.title;
    $("clock-total").textContent = `/ ${fmtTime(header.duration_s)}`;
    setupBar(this);
    hideLoading();
    $("hud").hidden = false;
    for (const r of header.runners || []) {
      // В редакторе ошибка загрузки видна в логах улья (со ссылкой на строку) — без баннера.
      if (!r.ok && !editor.active) showBanner(`Код улья ${r.name} не загрузился:\n${r.error}`, [["Понятно", hideBanner]]);
    }
  }

  _onStatus(st) {
    const badge = $("state-badge");
    badge.textContent = this.source.kind === "replay"
      ? (st.state === "paused" ? "пауза" : "реплей")
      : STATE_RU[st.state] || st.state;
    badge.className = `badge ${st.state}`;
    badge.title = "";
    // RTF — сколько секунд симуляции проходит за секунду реального времени. Если он заметно
    // меньше выбранной скорости, машина не успевает считать матч: пчёлы летают в замедлении.
    const lagging = this.source.kind === "live" && st.state === "running" && st.rtf > 0
      && st.rtf < 0.9 * st.speed;
    if (lagging) {
      badge.textContent = `не успевает: ${st.rtf.toFixed(st.rtf < 1 ? 2 : 1)}× вместо ×${st.speed}`;
      badge.className = "badge lagging";
      badge.title = "Компьютер считает матч медленнее реального времени: за 1 с проходит "
        + `${st.rtf.toFixed(2)} с матча. Пчёлы движутся в замедлении. Помогает графика «Экономное» `
        + "(тяжёлый рендер на встроенной видеокарте отнимает мощность у процессора), "
        + "меньшая скорость или профиль поменьше.";
    }
    this._autoQuality(lagging);
    updatePlayButton(this);
    if (st.state === "starting") showLoading("Сборка мира и запуск кода ульев…");
    if (st.state === "error") {
      hideLoading();
      showBanner(`Матч завершился с ошибкой:\n${st.error || "неизвестная ошибка"}`,
        editor.active ? [["Закрыть", hideBanner]] : [["Меню", toLobby]]);
    }
  }

  /** Живой матч не успевает 3 секунды подряд — упростить графику на уровень (без перезагрузки). */
  _autoQuality(lagging) {
    this.lagCount = lagging ? (this.lagCount || 0) + 1 : 0;
    if (this.lagCount < 3) return;
    this.lagCount = 0;
    const i = QUALITY_ORDER.indexOf(stage.qualityName);
    if (i < 0 || i >= QUALITY_ORDER.length - 1) return;
    const next = QUALITY_ORDER[i + 1];
    stage.setQuality(next);
    $("quality").value = next;
    this.viewer?.notify?.(`⚙️ Симуляция не успевает — графика упрощена до «${QUALITY[next].label}»`);
  }

  _onFooter(footer) {
    if (!footer || this.endShown) return;
    this.endShown = true;
    const stopped = this.source.status?.state === "stopped";
    const text = this.viewer?.describeResult(footer.score, stopped) || (stopped ? "Матч остановлен" : "Матч окончен");
    const toSeries = this.seriesId ? [["📊 Таблица серии", () => { hideBanner(); showSeries(this.seriesId); }]] : [];
    if (editor.active) {
      showBanner(text, [...toSeries, ["↻ Перезапустить", () => { hideBanner(); editor.start(); }], ["Закрыть", hideBanner]]);
      return;
    }
    const actions = [...toSeries];
    if (this.source.kind === "live" && footer.replay) {
      const id = footer.replay.replace(/\.swr$/, "");
      actions.push(["Смотреть реплей", () => openReplay(id, footer.replay)]);
    }
    if (this.source.kind === "replay") actions.push(["Сначала", () => { hideBanner(); this.endShown = false; this.source.seek(0); this.source.resume(); }]);
    actions.push(["Новый матч", toLobby]);
    actions.push(["Закрыть", hideBanner]);
    showBanner(text, actions);
  }

  _onClose() {
    if (this.closed || this.source.footer) return;
    showBanner("Связь с сервером потеряна", [["Меню", toLobby]]);
  }

  update(dt) {
    if (!this.viewer || !this.source.ready) return;
    const s = this.source.sample(dt);
    if (!s) return;
    this.viewer.update(s, dt);
    $("clock").textContent = fmtTime(s.time);
    if (this.source.kind === "replay" && !this.seeking) $("seek").value = String(s.time);
  }

  close() {
    this.closed = true;
    this.source.close();
    this.viewer?.dispose();
    stage.unfollow();
  }
}

stage.onFrame((dt) => session?.update(dt));

// ------------------------------------------------------------------ нижняя панель

function setupBar(s) {
  const src = s.source;
  const speeds = src.kind === "live" ? LIVE_SPEEDS : REPLAY_SPEEDS;
  const box = $("speeds");
  box.innerHTML = "";
  for (const v of speeds) {
    const b = document.createElement("button");
    b.className = "btn speed";
    b.textContent = `×${v}`;
    b.dataset.speed = v;
    b.onclick = () => src.setSpeed(v);
    box.appendChild(b);
  }
  $("timeline").hidden = src.kind !== "replay";
  $("btn-stop").hidden = src.kind !== "live";
  if (src.kind === "replay") {
    const seek = $("seek");
    seek.min = String(src.t0);
    seek.max = String(src.t1);
    seek.oninput = () => {
      s.seeking = true;
      src.seek(Number(seek.value));
    };
    seek.onchange = () => {
      s.seeking = false;
    };
    src.emit("status", { state: "running", speed: src.speed });
  }
  updatePlayButton(s);
}

function updatePlayButton(s) {
  const src = s.source;
  $("btn-play").textContent = src.paused ? "▶" : "⏸";
  for (const b of $("speeds").children) b.classList.toggle("active", Number(b.dataset.speed) === src.speed);
}

function togglePause() {
  if (!session) return;
  const src = session.source;
  if (src.paused || (src.kind === "replay" && src.ended)) src.resume();
  else src.pause();
}

$("btn-play").onclick = togglePause;
$("btn-overview").onclick = () => session?.viewer?.overview();

// Качество графики: разрешение и FPS — сразу; сглаживание — после перезагрузки страницы.
{
  const sel = $("quality");
  for (const name of QUALITY_ORDER) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = `Графика: ${QUALITY[name].label}`;
    sel.appendChild(opt);
  }
  sel.value = stage.qualityName;
  sel.onchange = () => {
    saveQuality(sel.value);
    if (stage.setQuality(sel.value)) location.reload();
  };
}
$("btn-menu").onclick = toLobby;
$("btn-stop").onclick = () => {
  if (session?.source.kind === "live" && confirm("Остановить матч? Реплей сохранится.")) session.source.stop();
};

window.addEventListener("keydown", (e) => {
  if (isTyping(e) || !session?.viewer) return;
  if (e.code === "Space") {
    e.preventDefault();
    togglePause();
  } else if (e.code === "Escape") {
    session.viewer.unfollow();
  } else if (e.code === "KeyH") {
    session.viewer.overview();
  } else if (/^Digit[1-9]$/.test(e.code)) {
    session.viewer.focusHive(Number(e.code.slice(5)) - 1);
  }
});

// Клик по пчеле — «следить» (отличаем клик от перетаскивания камеры).
let down = null;
stage.renderer.domElement.addEventListener("pointerdown", (e) => {
  down = { x: e.clientX, y: e.clientY, t: performance.now() };
});
stage.renderer.domElement.addEventListener("pointerup", (e) => {
  if (!down || e.button !== 0 || !session?.viewer) return;
  const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
  if (moved < 5 && performance.now() - down.t < 400) {
    const r = stage.renderer.domElement.getBoundingClientRect();
    session.viewer.pickAt(e.clientX - r.left, e.clientY - r.top);
  }
  down = null;
});

// ------------------------------------------------------------------ баннер и загрузка

function showBanner(text, actions = []) {
  const el = $("banner");
  el.innerHTML = "";
  const p = document.createElement("div");
  p.className = "banner-text";
  p.textContent = text;
  el.appendChild(p);
  const row = document.createElement("div");
  row.className = "banner-actions";
  for (const [label, fn] of actions) {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = label;
    b.onclick = fn;
    row.appendChild(b);
  }
  el.appendChild(row);
  el.hidden = false;
}

function hideBanner() {
  $("banner").hidden = true;
}

function showLoading(text) {
  $("loading-text").textContent = text;
  $("loading").hidden = false;
}

function hideLoading() {
  $("loading").hidden = true;
}

// ------------------------------------------------------------------ переходы

function begin(source, title, hash) {
  session?.close();
  hideBanner();
  lobby.hide();
  $("hud").hidden = true;
  history.replaceState(null, "", editor.active ? "#editor" : hash ? `#${hash}` : location.pathname);
  session = new Session(source, title);
  editor.setEmpty(false);
}

async function openLive(id) {
  showLoading("Подключение к матчу…");
  begin(new LiveSource(id), `Живой матч · ${id}`, `live=${id}`);
}

async function openReplay(id, name) {
  showLoading("Загрузка реплея…");
  try {
    const src = await ReplaySource.fromUrl(api.replayUrl(id), name || id);
    begin(src, `Реплей · ${id}`, `replay=${id}`);
  } catch (e) {
    hideLoading();
    showBanner(`Не удалось открыть реплей: ${e.message}`, [["Меню", toLobby]]);
  }
}

async function openFile(file) {
  showLoading(`Чтение ${file.name}…`);
  try {
    const src = await ReplaySource.fromFile(file);
    begin(src, `Реплей · ${file.name}`, "");
  } catch (e) {
    hideLoading();
    lobby.error(`Не удалось открыть ${file.name}: ${e.message}`);
  }
}

async function startMatch(body) {
  const info = await api.start(body);
  await openLive(info.id);
}

function toLobby() {
  if (editor.active && editor.dirty && !confirm("В редакторе есть несохранённые правки. Выйти в меню без сохранения?")) return;
  editor.close();
  seriesView.hide();
  session?.close();
  session = null;
  hideBanner();
  hideLoading();
  $("hud").hidden = true;
  history.replaceState(null, "", location.pathname);
  lobby.show();
}

// ------------------------------------------------------------------ серии (M7c)

/** Таблица серии: в меню — поверх страницы, в редакторе — поверх вьюера. */
const seriesView = new SeriesView({
  onWatch: (sid, seed, title) => watchSeriesReplay(sid, seed, title),
  onClose: () => {
    lobby.refreshSeries();
    editor.onSeriesClosed?.(seriesView.id);
  },
});

function seriesContainer() {
  return editor.active ? $("view") : document.body;
}

async function showSeries(id) {
  await seriesView.show(id, seriesContainer());
}

async function startSeries(body) {
  return seriesView.start(body, seriesContainer());
}

async function watchSeriesReplay(sid, seed, title) {
  seriesView.root.hidden = true; // не hide(): таблица вернётся по кнопке, опрос не нужен
  showLoading("Загрузка реплея…");
  try {
    const src = await ReplaySource.fromUrl(api.seriesReplayUrl(sid, seed), `s${seed}.swr`);
    begin(src, title, "");
    session.seriesId = sid;
  } catch (e) {
    hideLoading();
    showBanner(`Не удалось открыть реплей: ${e.message}`, [["Таблица серии", () => { hideBanner(); showSeries(sid); }]]);
  }
}

const lobby = new Lobby({
  startMatch, openLive, openReplay, openFile, startSeries, openSeries: showSeries,
  async openInEditor(name) {
    await openEditor();
    await editor.openScript(name);
  },
});

// ------------------------------------------------------------------ редактор (M5)

const editor = new Editor({
  async start(body) {
    const info = await api.start(body);
    showLoading("Запуск матча…");
    begin(new LiveSource(info.id), `Мой рой · ${info.id}`, "editor");
    editor.attach(session.source);
  },
  stop() {
    if (session?.source.kind === "live") session.source.stop();
  },
  startSeries,
  showSeries,
  exit: toLobby,
});

async function openEditor() {
  lobby.hide();
  history.replaceState(null, "", "#editor");
  try {
    await editor.open();
  } catch (e) {
    editor.close();
    lobby.show();
    lobby.error(`Редактор не открылся: ${e.message}`);
    return;
  }
  editor.setEmpty(!session);
}
$("lobby-editor").onclick = openEditor;

window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  const f = e.dataTransfer?.files?.[0];
  if (!f) return;
  if (/\.swarm$/i.test(f.name)) {
    // Проект: в меню — загрузка в projects/, в редакторе — «Открыть проект…».
    if (editor.active) editor.openProjectFile(f);
    else lobby.uploadProject(f);
  } else openFile(f);
});

// Ссылка вида #live=<id> или #replay=<id> открывает сразу (перезагрузка вкладки).
function route() {
  const m = /^#(live|replay)=(.+)$/.exec(location.hash);
  if (location.hash === "#editor") {
    if (!editor.active) openEditor();
  } else if (m && m[1] === "replay") openReplay(decodeURIComponent(m[2]));
  else if (m && m[1] === "live") {
    api.match(decodeURIComponent(m[2])).then(
      (info) => (["finished", "stopped", "error"].includes(info.state) && info.replay
        ? openReplay(info.replay)
        : openLive(info.id)),
      () => toLobby(),
    );
  } else toLobby();
}
window.addEventListener("hashchange", route);
route();
