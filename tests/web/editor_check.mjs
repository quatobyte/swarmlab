// Проверка подсказок редактора под Node (без браузера): `node editor_check.mjs`.
// Печатает JSON {проба: [имена подсказок]} для tests/web/test_api_hints.py.
// Курсор — в конце текста пробы; код выше — как в файле игрока.

import { renderMarkdown } from "../../web/js/core/ui/markdown.js";
import { hint } from "../../web/js/modules/bees/editor.js";

/** Минимальный двойник CodeMirror: только то, что читает hint(). */
function fakeCm(text) {
  const lines = text.split("\n");
  const cur = { line: lines.length - 1, ch: lines[lines.length - 1].length };
  return {
    getCursor: () => cur,
    getLine: (n) => lines[n],
    getRange: (_from, to) => lines.slice(0, to.line).join("\n") + (to.line ? "\n" : ""),
  };
}

const HEAD = `from swarmlab.bees.api import *


class MyCollector(Collector):
    def loop(self):
`;

const probes = {
  "self.": HEAD + "        self.",
  "self.co": HEAD + "        self.co",
  "flower=": HEAD + "        flower = self.nearest_flower(min_nectar=0.3)\n        flower.",
  "for": HEAD + "        for b in self.bees:\n            b.",
  "heard": HEAD + "        for m in self.heard:\n            m.",
  "index": HEAD + "        self.flowers[0].pos.",
  "selfattr": HEAD + "        self.target = self.nearest_flower()\n        self.target.",
  "hive": "class MyHive(Hive):\n    def loop(self):\n        self.",
  "global": HEAD + "        Col",
  "super": HEAD + "        super().",
};
const out = {};
for (const [k, text] of Object.entries(probes)) {
  const res = hint(fakeCm(text));
  out[k] = res ? res.list.map((x) => x.m.name) : [];
}
out.markdown = renderMarkdown("# Т\n\n| a | b |\n|---|---|\n| `x<y` | **ж** |\n\n```\nprint(1)\n```\n- один\n- два");
console.log(JSON.stringify(out));
