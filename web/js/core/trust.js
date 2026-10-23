// Предупреждение о чужом коде (M7c, DECISIONS №65). Код из проекта выполняется на этом
// компьютере: раннер отделяет его от симуляции, но не от системы. Перед первым запуском
// браузер спрашивает и запоминает sha256 текста кода; изменённый файл спросит снова.
// Это честное предупреждение, а не защита. Без DOM: работает и под Node (тесты).

export const TRUST_KEY = "swarmlab.trusted";
export const TRUST_TEXT = "Код из этого проекта выполнится на вашем компьютере. "
  + "Открывайте только проекты от тех, кому доверяете.";
const MAX_REMEMBERED = 500;

/** sha256 текста (UTF-8) в hex — так же считает сервер (`code_sha256`). */
export async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function load(storage) {
  try {
    const list = JSON.parse(storage?.getItem(TRUST_KEY) || "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export async function isTrusted(code, storage) {
  return load(storage).includes(await sha256Hex(code));
}

export async function trust(code, storage) {
  const hash = await sha256Hex(code);
  const list = load(storage).filter((h) => h !== hash);
  list.push(hash);
  try {
    storage?.setItem(TRUST_KEY, JSON.stringify(list.slice(-MAX_REMEMBERED)));
  } catch {
    /* хранилище недоступно — спросим в следующий раз снова */
  }
}

/**
 * Спросить один раз на содержимое: `codes` — тексты кода проектов, `ask(text)` → Promise<bool>.
 * Все уже знакомые — `true` без вопроса; иначе вопрос, и при согласии коды запоминаются.
 */
export async function confirmForeignCode(codes, ask, storage = globalThis.localStorage) {
  const unknown = [];
  for (const code of codes) if (!(await isTrusted(code, storage))) unknown.push(code);
  if (!unknown.length) return true;
  if (!(await ask(TRUST_TEXT))) return false;
  for (const code of unknown) await trust(code, storage);
  return true;
}
