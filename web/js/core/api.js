// REST-клиент сервера (ARCHITECTURE §7, §7.1).
//
// Публичный режим (портал, M9a): сессия — HTTP-only cookie (её ставит сервер), на изменяющих
// запросах сам подставляется заголовок X-CSRF-Token (токен приходит в `GET /api/me` и при
// входе). Ответ 401 — вход кончился: событие `swarmlab:unauthorized` на `window`.

let csrf = null;

/** Токен защиты от подделки запросов текущей сессии (`null` — локальный режим или выход). */
export function setCsrf(token) {
  csrf = token || null;
}

async function request(method, path, body, raw = false) {
  const headers = {};
  if (body) headers["Content-Type"] = raw ? "application/octet-stream" : "application/json";
  if (csrf && method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrf;
  const res = await fetch(path, {
    method,
    headers,
    body: body ? (raw ? body : JSON.stringify(body)) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let data = null;
    try {
      data = (await res.json()).detail ?? null;
      if (data && typeof data === "object" && data.message) detail = data.message;
      else if (data) detail = typeof data === "string" ? data : JSON.stringify(data);
    } catch {
      /* тело не JSON */
    }
    const err = new Error(detail);
    err.status = res.status;
    err.data = data; // структурная ошибка (например, синтаксис скрипта: {script, line, col, message})
    if (res.status === 401 && csrf && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new CustomEvent("swarmlab:unauthorized", { detail: err }));
    }
    throw err;
  }
  return res.json();
}

export const api = {
  configs: () => request("GET", "/api/configs"),
  matches: () => request("GET", "/api/matches"),
  match: (id) => request("GET", `/api/matches/${encodeURIComponent(id)}`),
  start: (body) => request("POST", "/api/matches", body),
  stop: (id) => request("POST", `/api/matches/${encodeURIComponent(id)}/stop`),
  replays: () => request("GET", "/api/replays"),
  replayUrl: (id) => `/api/replays/${encodeURIComponent(id)}`,
  profiles: () => request("GET", "/api/profiles"),
  scripts: () => request("GET", "/api/scripts"),
  script: (name) => request("GET", `/api/scripts/${encodeURIComponent(name)}`),
  saveScript: (name, text, blocks) => request("PUT", `/api/scripts/${encodeURIComponent(name)}`,
    blocks ? { text, blocks } : { text }),
  checkScript: (text) => request("POST", "/api/scripts/check", { text }),
  help: () => request("GET", "/api/help"),
  // Проекты .swarm и серии матчей (M7c).
  projects: () => request("GET", "/api/projects"),
  project: (name) => request("GET", `/api/projects/${encodeURIComponent(name)}`),
  uploadProject: (text) => request("POST", "/api/projects", text, true),
  projectToEditor: (name, target) => request("POST", `/api/projects/${encodeURIComponent(name)}/to-editor`,
    target ? { name: target } : {}),
  seriesList: () => request("GET", "/api/series"),
  series: (id) => request("GET", `/api/series/${encodeURIComponent(id)}`),
  startSeries: (body) => request("POST", "/api/series", body),
  stopSeries: (id) => request("POST", `/api/series/${encodeURIComponent(id)}/stop`),
  seriesReplayUrl: (id, seed) => `/api/series/${encodeURIComponent(id)}/replays/${seed}`,
  // Портал (M9a): только в публичном режиме, в локальном `me()` — 404.
  me: () => request("GET", "/api/me"),
  register: (email, password) => request("POST", "/api/auth/register", { email, password }),
  login: (email, password) => request("POST", "/api/auth/login", { email, password }),
  logout: () => request("POST", "/api/auth/logout"),
  changePassword: (current, next) => request("POST", "/api/me/password", { current, new: next }),
  deleteAccount: (password) => request("DELETE", "/api/me", { password }),
  exportUrl: () => "/api/me/export",
  pinReplay: (id, pinned) => request("POST", `/api/replays/${encodeURIComponent(id)}/pin`, { pinned }),
  deleteReplay: (id) => request("DELETE", `/api/replays/${encodeURIComponent(id)}`),
  deleteScript: (name) => request("DELETE", `/api/scripts/${encodeURIComponent(name)}`),
  deleteProject: (name) => request("DELETE", `/api/projects/${encodeURIComponent(name)}`),
};
