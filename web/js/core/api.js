// REST-клиент сервера (ARCHITECTURE §7).

async function request(method, path, body, raw = false) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": raw ? "application/octet-stream" : "application/json" } : undefined,
    body: body ? (raw ? body : JSON.stringify(body)) : undefined,
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
};
