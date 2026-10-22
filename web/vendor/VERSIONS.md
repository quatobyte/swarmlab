# Сторонние библиотеки вьюера (vendored)

Лежат в репозитории, чтобы вьюер работал без интернета и без сборщика (DECISIONS №17, №44).
Скачаны из реестра npm (`registry.npmjs.org`) 17.10.2026; файлы не менялись.

| Библиотека | Версия | Файлы | Источник в пакете | Лицензия |
|---|---|---|---|---|
| three.js | 0.186.1 | `three/three.module.js`, `three/three.core.js` | `build/` | MIT (`three/LICENSE`) |
| three.js addons | 0.186.1 | `three/addons/controls/OrbitControls.js`, `three/addons/utils/BufferGeometryUtils.js` | `examples/jsm/` | MIT |
| fzstd | 0.1.1 | `fzstd/fzstd.js` | `esm/index.mjs` | MIT (`fzstd/LICENSE`) |
| CodeMirror 5 | 5.65.21 | `codemirror/lib/codemirror.{js,css}`, `mode/python/python.js`, аддоны `hint/show-hint.{js,css}`, `lint/lint.{js,css}`, `edit/matchbrackets.js`, `edit/closebrackets.js`, `comment/comment.js`, `selection/active-line.js`, тема `theme/material-darker.css` | те же пути в пакете | MIT (`codemirror/LICENSE`) |

sha256 тарболов npm:

- `three-0.186.1.tgz` — `8cd068708ea44f2c73c944b1cead2ba2f0d5c15c8fc194e5700f4e4f4a033fe7`
- `fzstd-0.1.1.tgz` — `5ed2ee2d3439067be211d0093292c708a831045372342c897437e5a4997c45c5`
- `codemirror-5.65.21.tgz` — `b26d9d7ae0f42e34b44a8f7667d29a3ab0d3df88d0e79c0dad39dc03ba43f6dc` (скачан 19.10.2026)

Аддоны three.js импортируют `'three'` — имя разрешает import map в `web/index.html`.
CodeMirror 5 — UMD-скрипты (глобальный `CodeMirror`), подключаются обычными `<script>` в `index.html` (DECISIONS №46).
Распаковка msgpack — своя (`web/js/core/msgpack.js`, только чтение, ~100 строк).

Обновление: скачать тарбол нужной версии, заменить файлы, поправить таблицу и хеши.
