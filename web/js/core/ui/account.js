// Портал (M9a, DECISIONS №91–92): вход и регистрация, профиль, «Мои проекты», «Мои реплеи».
// Публичный режим клиент узнаёт по `GET /api/me`: 200 — вошли, 401 — экран входа,
// 404 — локальный режим (ничего из этого файла не показывается).

import { api, setCsrf } from "../api.js";
import { makeProject, projectText, PROJECT_EXT } from "../project.js";
import { ask } from "./dialog.js";

const $ = (id) => document.getElementById(id);

export function fmtSize(bytes) {
  return bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1e3))} КБ`;
}

function fmtDate(iso) {
  return String(iso || "").replace("T", " ").slice(0, 16);
}

function btn(label, title, onClick, cls = "") {
  const b = document.createElement("button");
  b.className = `btn small ${cls}`.trim();
  b.textContent = label;
  if (title) b.title = title;
  b.onclick = onClick;
  return b;
}

function row(name, meta) {
  const r = document.createElement("div");
  r.className = "row";
  r.innerHTML = '<span class="name"></span><span class="muted small"></span><span class="spacer"></span>';
  r.querySelector(".name").textContent = name;
  r.querySelector(".muted").textContent = meta;
  return r;
}

function download(href, filename) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ====================================================================== вход и регистрация

/** Экран входа и регистрации; `show()` ждёт успешного входа и отдаёт профиль. */
export class AuthScreen {
  constructor() {
    this.el = $("auth");
    this.mode = "login";
    this.resolve = null;
    $("auth-tab-login").onclick = () => this._setMode("login");
    $("auth-tab-register").onclick = () => this._setMode("register");
    $("auth-form").addEventListener("submit", (e) => {
      e.preventDefault();
      this._submit();
    });
  }

  show(message = "") {
    this.el.hidden = false;
    this._error(message, !!message);
    $("auth-password").value = "";
    $("auth-password2").value = "";
    this._setMode(this.mode);
    return new Promise((resolve) => {
      this.resolve = resolve;
    });
  }

  hide() {
    this.el.hidden = true;
  }

  get visible() {
    return !this.el.hidden;
  }

  _setMode(mode) {
    this.mode = mode;
    const reg = mode === "register";
    $("auth-tab-login").classList.toggle("active", !reg);
    $("auth-tab-register").classList.toggle("active", reg);
    $("auth-repeat").hidden = !reg;
    $("auth-submit").textContent = reg ? "Зарегистрироваться" : "Войти";
    $("auth-password").autocomplete = reg ? "new-password" : "current-password";
    $("auth-note").textContent = reg
      ? "Почта — ваш логин, писем не будет. Пароль — не меньше 8 символов; забудете — поможет админ."
      : "Нет аккаунта? Нажмите «Регистрация».";
    (($("auth-email").value ? $("auth-password") : $("auth-email"))).focus();
  }

  _error(text, bad = true) {
    const el = $("auth-error");
    el.hidden = !text;
    el.textContent = text || "";
    el.className = `small ${bad ? "error" : "muted"}`;
  }

  async _submit() {
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;
    if (this.mode === "register" && password !== $("auth-password2").value) {
      this._error("Пароли не совпадают");
      return;
    }
    $("auth-submit").disabled = true;
    try {
      const me = this.mode === "register" ? await api.register(email, password) : await api.login(email, password);
      setCsrf(me.csrf);
      this.hide();
      this.resolve?.(me);
      this.resolve = null;
    } catch (e) {
      this._error(e.message);
    } finally {
      $("auth-submit").disabled = false;
    }
  }
}

// ====================================================================== профиль

/** Окно профиля: смена пароля, архив проектов, удаление аккаунта, выход. */
export function showProfile(me, { onLogout, onDeleted }) {
  const back = document.createElement("div");
  back.className = "modal-back";
  const box = document.createElement("div");
  box.className = "modal profile";
  box.innerHTML = `
    <h3>Профиль</h3>
    <p class="modal-text">Вы вошли как <b class="p-email"></b></p>
    <h4>Сменить пароль</h4>
    <form class="form p-pass">
      <label>Текущий пароль <input type="password" class="p-cur" autocomplete="current-password" required></label>
      <label>Новый пароль <input type="password" class="p-new" autocomplete="new-password" minlength="8" required></label>
      <label>Ещё раз <input type="password" class="p-new2" autocomplete="new-password" required></label>
      <button class="btn" type="submit">Сменить</button>
    </form>
    <p class="small p-pass-msg" hidden></p>
    <h4>Мой код</h4>
    <p class="small muted">Все свои скрипты и проекты одним архивом (.zip с файлами .swarm).</p>
    <button class="btn p-export">⬇ Скачать архив проектов</button>
    <h4>Удалить аккаунт</h4>
    <p class="small muted">Удалятся все ваши скрипты, проекты и реплеи — насовсем. Сначала скачайте архив.</p>
    <form class="form p-del">
      <label>Текущий пароль <input type="password" class="p-del-pass" autocomplete="current-password" required></label>
      <button class="btn danger" type="submit">Удалить аккаунт…</button>
    </form>
    <p class="small error p-del-msg" hidden></p>
    <div class="modal-actions">
      <button class="btn p-logout">Выйти</button>
      <button class="btn primary p-close">Закрыть</button>
    </div>`;
  back.appendChild(box);
  const q = (s) => box.querySelector(s);
  q(".p-email").textContent = me.email;
  const close = () => {
    back.remove();
    window.removeEventListener("keydown", onKey, true);
  };
  const onKey = (e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
    }
  };
  window.addEventListener("keydown", onKey, true);
  const msg = (el, text, bad) => {
    el.hidden = !text;
    el.textContent = text || "";
    el.classList.toggle("error", !!bad);
    el.classList.toggle("muted", !bad);
  };
  q(".p-close").onclick = close;
  q(".p-logout").onclick = async () => {
    close();
    await onLogout();
  };
  q(".p-export").onclick = () => download(api.exportUrl(), "swarmlab-projects.zip");
  q(".p-pass").addEventListener("submit", async (e) => {
    e.preventDefault();
    const el = q(".p-pass-msg");
    if (q(".p-new").value !== q(".p-new2").value) {
      msg(el, "Новые пароли не совпадают", true);
      return;
    }
    try {
      await api.changePassword(q(".p-cur").value, q(".p-new").value);
      for (const s of [".p-cur", ".p-new", ".p-new2"]) q(s).value = "";
      msg(el, "Пароль изменён. На других устройствах нужно войти заново.", false);
    } catch (err) {
      msg(el, err.message, true);
    }
  });
  q(".p-del").addEventListener("submit", async (e) => {
    e.preventDefault();
    const el = q(".p-del-msg");
    const ok = await ask("Удалить аккаунт со всеми скриптами, проектами и реплеями? Вернуть их будет нельзя.\n\n"
      + "Если ещё не скачали архив проектов — нажмите «Отмена» и скачайте.",
    { title: "Удалить аккаунт", ok: "Удалить насовсем", danger: true });
    if (!ok) return;
    try {
      await api.deleteAccount(q(".p-del-pass").value);
      close();
      await onDeleted();
    } catch (err) {
      msg(el, err.message, true);
    }
  });
  document.body.appendChild(back);
  q(".p-cur").focus();
}

// ====================================================================== свои данные в меню

/** «Мои реплеи»: смотреть, сохранить (закрепить), скачать .swr, удалить. */
export function renderMyReplays(box, note, list, usage, { open, refresh, error }) {
  box.innerHTML = list.length ? "" : '<p class="muted small">Реплеев пока нет — запустите матч.</p>';
  if (usage) {
    note.hidden = false;
    note.textContent = `Последние ${usage.keep_last} матчей хранятся сами (до ${usage.unpinned_max_age_days} дней). `
      + `«Сохранить» — навсегда: ${usage.pinned_count} из ${usage.pinned_max_count}, `
      + `${fmtSize(usage.pinned_bytes)} из ${usage.pinned_max_mb} МБ.`;
  }
  for (const r of list) {
    const el = row(`${r.pinned ? "📌 " : ""}${r.id}`, `${fmtSize(r.size)} · ${fmtDate(r.created)}`);
    el.append(
      btn("Смотреть", "Открыть реплей в 3D", () => open(r.id, r.name), "primary"),
      btn(r.pinned ? "Не хранить" : "Сохранить",
        r.pinned ? "Вернуть в обычные: удалится, когда станет старым" : "Хранить, пока не удалите (в пределах квоты)",
        async () => {
          try {
            await api.pinReplay(r.id, !r.pinned);
            await refresh();
          } catch (e) {
            error(e.message);
          }
        }),
      btn("⬇ .swr", "Скачать файл реплея", () => download(api.replayUrl(r.id), r.name)),
      btn("Удалить", "Удалить реплей", async () => {
        if (!(await ask(`Удалить реплей ${r.id}?`, { ok: "Удалить", danger: true }))) return;
        try {
          await api.deleteReplay(r.id);
          await refresh();
        } catch (e) {
          error(e.message);
        }
      }),
    );
    box.appendChild(el);
  }
}

/** Свой скрипт редактора как файл `.swarm` (как «⬇ Экспорт проекта» в редакторе). */
async function downloadScript(name) {
  const data = await api.script(name);
  const mode = data.blocks?.mode === "blocks" ? "blocks" : "python";
  const project = makeProject({ name, mode, code: data.text, blocks: data.blocks?.workspace ?? null,
    created: data.modified });
  const url = URL.createObjectURL(new Blob([projectText(project)], { type: "application/json" }));
  download(url, `${project.name}${PROJECT_EXT}`);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** «Мои проекты»: свои скрипты редактора — открыть, скачать .swarm, удалить. */
export function renderMyScripts(box, scripts, { openInEditor, refresh, error }) {
  const own = scripts.filter((s) => !s.readonly);
  box.innerHTML = own.length ? ""
    : '<p class="muted small">Своих скриптов пока нет — откройте редактор кода.</p>';
  for (const s of own) {
    const el = row(`${s.mode === "blocks" ? "🧩" : "🐍"} ${s.name}`,
      `${s.mode === "blocks" ? "блоки" : "Python"} · ${fmtDate(s.modified)}`);
    el.append(
      btn("Открыть", "Открыть в редакторе", () => openInEditor(s.name), "primary"),
      btn("⬇ .swarm", "Скачать проект", () => downloadScript(s.name).catch((e) => error(e.message))),
      btn("Удалить", "Удалить скрипт", async () => {
        if (!(await ask(`Удалить скрипт ${s.name}? Вернуть его будет нельзя.`, { ok: "Удалить", danger: true }))) return;
        try {
          await api.deleteScript(s.name);
          await refresh();
        } catch (e) {
          error(e.message);
        }
      }),
    );
    box.appendChild(el);
  }
}

/** Кнопки загруженного проекта на портале: скачать `.swarm`, удалить. */
export function projectButtons(p, { refresh, error }) {
  return [
    btn("⬇ .swarm", "Скачать проект", async () => {
      try {
        const data = await api.project(p.name);
        const project = makeProject({ name: data.title, mode: data.mode, code: data.code,
          blocks: data.blocks, created: data.created });
        const url = URL.createObjectURL(new Blob([projectText(project)], { type: "application/json" }));
        download(url, `${p.name}${PROJECT_EXT}`);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) {
        error(e.message);
      }
    }),
    btn("Удалить", "Удалить проект", async () => {
      if (!(await ask(`Удалить проект ${p.name}?`, { ok: "Удалить", danger: true }))) return;
      try {
        await api.deleteProject(p.name);
        await refresh();
      } catch (e) {
        error(e.message);
      }
    }),
  ];
}
