// REST-клиент сервера (ARCHITECTURE §7).

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
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
  saveScript: (name, text) => request("PUT", `/api/scripts/${encodeURIComponent(name)}`, { text }),
  checkScript: (text) => request("POST", "/api/scripts/check", { text }),
  help: () => request("GET", "/api/help"),
};
