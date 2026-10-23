// Модальные окна поверх всего: вопрос с двумя кнопками и параметры серии матчей (M7c).

function modal(build) {
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "modal-back";
    const box = document.createElement("div");
    box.className = "modal";
    back.appendChild(box);
    const done = (value) => {
      back.remove();
      window.removeEventListener("keydown", onKey, true);
      resolve(value);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        done(null);
      }
    };
    window.addEventListener("keydown", onKey, true);
    build(box, done);
    document.body.appendChild(back);
    box.querySelector("[autofocus], .btn.primary")?.focus();
  });
}

function button(label, cls, onClick) {
  const b = document.createElement("button");
  b.className = `btn ${cls}`;
  b.textContent = label;
  b.onclick = onClick;
  return b;
}

/** Вопрос: `true` — согласие (кнопка `ok`), `false` — отмена. */
export async function ask(text, { title = "", ok = "Да", cancel = "Отмена", danger = false } = {}) {
  const res = await modal((box, done) => {
    if (title) {
      const h = document.createElement("h3");
      h.textContent = title;
      box.appendChild(h);
    }
    const p = document.createElement("p");
    p.className = "modal-text";
    p.textContent = text;
    const row = document.createElement("div");
    row.className = "modal-actions";
    row.append(button(cancel, "", () => done(false)), button(ok, danger ? "primary danger" : "primary", () => done(true)));
    box.append(p, row);
  });
  return res === true;
}

/** Параметры серии: `{n, start_seed, jobs}` или `null` (отмена). */
export function askSeries({ n = 10, seed = null, note = "" } = {}) {
  return modal((box, done) => {
    box.innerHTML = `
      <h3>Серия матчей</h3>
      <p class="modal-text small muted">Один и тот же матч на разных условиях: seed идут подряд от начального.
        Все реплеи и таблица сохраняются в <code>replays/series/</code>.${note ? ` ${note}` : ""}</p>
      <div class="match-form">
        <label for="sd-n">Матчей</label>
        <input id="sd-n" type="number" min="2" max="50" step="1" autofocus>
        <label for="sd-seed">Начальный seed</label>
        <input id="sd-seed" type="number" min="0" step="1" placeholder="случайный">
        <label for="sd-jobs">Одновременно</label>
        <select id="sd-jobs"><option value="">авто (ядер − 1)</option><option>1</option><option>2</option>
          <option>3</option><option>4</option></select>
      </div>
      <p class="error small" id="sd-error" hidden></p>`;
    const q = (id) => box.querySelector(`#${id}`);
    q("sd-n").value = String(n);
    if (seed !== null && seed !== undefined) q("sd-seed").value = String(seed);
    const row = document.createElement("div");
    row.className = "modal-actions";
    const go = () => {
      const count = Math.floor(Number(q("sd-n").value));
      if (!(count >= 2 && count <= 50)) {
        q("sd-error").hidden = false;
        q("sd-error").textContent = "Матчей в серии — от 2 до 50";
        return;
      }
      const s = q("sd-seed").value.trim();
      const jobs = q("sd-jobs").value;
      done({ n: count, start_seed: s === "" ? null : Math.max(0, Math.floor(Number(s))), jobs: jobs ? Number(jobs) : null });
    };
    row.append(button("Отмена", "", () => done(null)), button("▶ Запустить серию", "primary", go));
    box.appendChild(row);
    box.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
  });
}
