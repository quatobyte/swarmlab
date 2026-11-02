// HUD пчёлок: карточки ульев (место, мёд, нектар, численность по типам), погода и ветер,
// лента событий по-русски, панель пчелы, за которой следит камера.

const $ = (id) => document.getElementById(id);

export const KIND_RU = { scout: "разведчик", forager: "сборщик", house: "домашняя" };
const KIND_SHORT = [["scout", "Р", "разведчики"], ["forager", "С", "сборщики"], ["house", "Д", "домашние"]];
const WEATHER_RU = {
  clear: ["☀️", "Ясно"],
  windy: ["🌬️", "Ветрено"],
  rain: ["🌧️", "Дождь"],
};
const CAUSE_RU = { energy: "без сил", spider: "паук" };
const FEED_MAX = 7;
const FEED_TTL_MS = 14000;

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function fmtT(t) {
  const s = Math.max(0, Math.floor(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export class BeesHud {
  constructor(header) {
    const scene = header.scene;
    this.scene = scene;
    this.colors = scene.hive_colors;
    this.nHives = scene.world.hive_pos.length / 3;
    this.playing = new Set(scene.playing || []);
    this.scripts = {};
    for (const t of header.teams || []) {
      this.scripts[t.team] = t.script ? t.script.split(/[\\/]/).pop() : "";
    }
    this.eliminated = new Set();
    this.feedItems = [];
    this._buildTeams();
    $("feed").innerHTML = "";
    $("follow").hidden = true;
    this._last = 0;
  }

  teamName(h) {
    return `Улей ${h + 1}`;
  }

  teamTag(h) {
    return `<span class="dot" style="--c:${esc(this.colors[h] || "#999")}"></span>${this.teamName(h)}`;
  }

  _buildTeams() {
    const box = $("teams");
    box.innerHTML = "";
    this.cards = [];
    for (let h = 0; h < this.nHives; h++) {
      const el = document.createElement("div");
      el.className = "panel team";
      el.style.setProperty("--c", this.colors[h] || "#999");
      el.innerHTML = `
        <div class="team-head"><span class="team-place"></span><span class="team-name">${this.teamName(h)}</span>
          <span class="team-script" title="${esc(this.scripts[h] || "")}">${esc(this.scripts[h] || "без кода")}</span></div>
        <div class="team-res">
          <span><span class="lbl">мёд</span><b class="honey">0</b></span>
          <span><span class="lbl">нектар</span><b class="nectar">0</b></span>
          <span><span class="lbl">всего</span><b class="alive">0</b></span>
        </div>
        <div class="team-kinds">${KIND_SHORT.map(([k, s, title]) =>
          `<span title="${title}">${s} <b class="k-${k}">0</b></span>`).join("")}</div>
        <div class="honey-bar"><i></i></div>`;
      box.appendChild(el);
      this.cards.push({
        el,
        place: el.querySelector(".team-place"),
        honey: el.querySelector(".honey"),
        nectar: el.querySelector(".nectar"),
        alive: el.querySelector(".alive"),
        kinds: Object.fromEntries(KIND_SHORT.map(([k]) => [k, el.querySelector(`.k-${k}`)])),
        bar: el.querySelector(".honey-bar i"),
      });
    }
  }

  /** Обновить по кадру (раз в ~0.2 с хватает). */
  update(frame, wallNow, cameraDir) {
    if (wallNow - this._last < 200) return;
    this._last = wallNow;
    const A = frame.arrays;
    const honey = A.hive_honey;
    const nectar = A.hive_nectar;
    const counts = A.hive_counts; // (H, столбцы scene.hive_counts): scout, forager, house, in_hive
    const cols = this.scene.hive_counts;
    const width = cols.length;
    const rows = [];
    for (let h = 0; h < this.nHives; h++) {
      let alive = 0;
      for (const [k] of KIND_SHORT) alive += counts[h * width + cols.indexOf(k)];
      if (alive === 0 && this.playing.has(h)) this.eliminated.add(h);
      rows.push({ h, honey: honey[h], alive });
    }
    // Места — как в счёте модуля (BEES_SPEC §8): выбывшие ниже, дальше мёд, затем живые.
    const ranked = rows.filter((r) => this.playing.has(r.h)).sort((a, b) =>
      (this.eliminated.has(a.h) - this.eliminated.has(b.h)) || (b.honey - a.honey) || (b.alive - a.alive) || (a.h - b.h));
    const place = new Map(ranked.map((r, i) => [r.h, i + 1]));
    const maxHoney = Math.max(1, ...rows.map((r) => r.honey));
    for (const r of rows) {
      const card = this.cards[r.h];
      const h = r.h;
      const p = place.get(h);
      card.place.textContent = p ? (p === 1 ? "🥇" : p === 2 ? "🥈" : p === 3 ? "🥉" : `${p}.`) : "";
      card.honey.textContent = honey[h].toFixed(1);
      card.nectar.textContent = nectar[h].toFixed(1);
      card.alive.textContent = String(r.alive);
      for (const [k] of KIND_SHORT) card.kinds[k].textContent = String(counts[h * width + cols.indexOf(k)]);
      card.bar.style.width = `${(100 * honey[h]) / maxHoney}%`;
      const out = this.eliminated.has(h);
      card.el.classList.toggle("out", out);
      if (out) card.place.textContent = "🏳";
    }

    // Погода и ветер (стрелка — относительно направления камеры).
    const states = this.scene.weather_states;
    const ws = states[A.weather[0]] || "clear";
    const [icon, text] = WEATHER_RU[ws] || ["", ws];
    $("weather-icon").textContent = icon;
    $("weather-text").textContent = text;
    const w = A.wind;
    const speed = Math.hypot(w[0], w[1]);
    $("wind-text").textContent = `${speed.toFixed(1)} м/с`;
    if (cameraDir) {
      // ветер в three: (wx, 0, −wy); камера смотрит вдоль f, вправо — r = (−fz, 0, fx)
      const wx = w[0], wz = -w[1];
      const up = wx * cameraDir.x + wz * cameraDir.z;
      const right = wx * -cameraDir.z + wz * cameraDir.x;
      const deg = (Math.atan2(-up, right) * 180) / Math.PI;
      $("wind-arrow").style.transform = `rotate(${deg.toFixed(0)}deg)`;
    }
    $("wind").style.opacity = speed > 0.05 ? "1" : "0.4";
  }

  // ------------------------------------------------------------ лента событий

  onEvents(events) {
    for (const e of events) {
      const msg = this.describe(e);
      if (msg) this.feed(e.time, msg.text, msg.hot);
      if (e.type === "eliminated") this.eliminated.add(e.hive);
    }
  }

  describe(e) {
    const kind = KIND_RU[e.kind] || e.kind;
    switch (e.type) {
      case "death":
        if (e.cause === "spider") return { text: `🕷️ Паук поймал: ${kind}, ${this.teamTag(e.hive)}` };
        if (e.cause === "energy") return { text: `💤 Без сил упал(а): ${kind}, ${this.teamTag(e.hive)}` };
        return { text: `Погиб(ла): ${kind}, ${this.teamTag(e.hive)} (${esc(CAUSE_RU[e.cause] || e.cause)})` };
      case "eliminated": return { text: `🏳️ ${this.teamTag(e.hive)} выбыл из матча`, hot: true };
      case "weather": {
        const [icon, text] = WEATHER_RU[e.state] || ["", e.state];
        return { text: `${icon} Погода: ${text.toLowerCase()}, ветер ${Number(e.wind).toFixed(1)} м/с` };
      }
      default:
        return null; // рождения, доставки, укусы — слишком часты для ленты
    }
  }

  feed(time, html, hot = false) {
    const box = $("feed");
    const last = this.feedItems[0];
    if (last && last.html === html && performance.now() - last.at < 4000) {
      last.count++;
      last.at = performance.now();
      last.el.querySelector(".x").textContent = ` ×${last.count}`;
      return;
    }
    const el = document.createElement("div");
    el.className = `feed-item${hot ? " hot" : ""}`;
    el.innerHTML = `<span class="t">${fmtT(time)}</span>${html}<span class="x"></span>`;
    box.prepend(el);
    const item = { el, html, count: 1, at: performance.now() };
    this.feedItems.unshift(item);
    while (this.feedItems.length > FEED_MAX) this.feedItems.pop().el.remove();
    setTimeout(() => el.classList.add("fade"), FEED_TTL_MS);
    setTimeout(() => {
      el.remove();
      this.feedItems = this.feedItems.filter((x) => x !== item);
    }, FEED_TTL_MS + 700);
  }

  clearFeed() {
    $("feed").innerHTML = "";
    this.feedItems = [];
    this.eliminated.clear();
  }

  // ------------------------------------------------------------ «следить»

  showFollow(info, uid) {
    const el = $("follow");
    if (!info) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    const meter = (cls, f) => `<span class="meter ${cls}"><i style="width:${(100 * f).toFixed(0)}%"></i></span>`;
    el.innerHTML = `<h3>${this.teamTag(info.hive)} · ${KIND_RU[info.kind]} <span class="muted small">#${uid}</span></h3>
      <div class="kv">
        <span>Энергия</span>${meter("", info.energy)}
        ${info.kind === "forager" ? `<span>Груз</span>${meter("cargo", info.cargo)}` : ""}
        <span>Скорость</span><span>${info.speed.toFixed(1)} м/с</span>
        <span>Состояние</span><span>${info.falling ? "падает!" : "летит"}</span>
      </div>`;
  }
}
