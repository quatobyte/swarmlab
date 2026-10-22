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


class MyForager(Forager):
    def step(self, s: Sensors):
`;
const HOUSE = `from swarmlab.bees.api import *


class Base(HouseBee):
    pass


class MyHouse(Base):
    def step(self, s):
`;

const probes = {
  "s.me.": HEAD + "        s.me.",
  "self.": HEAD + "        self.",
  "self.co": HEAD + "        self.co",
  "flower=": HEAD + "        flower = s.nearest_flower(min_nectar=0.3)\n        flower.",
  "for": HEAD + "        for e in s.enemies:\n            e.",
  "index": HEAD + "        s.flowers[0].pos.",
  "selfattr": HEAD + "        self.target = s.nearest_flower()\n        self.target.",
  "hive": "def hive_step(hive):\n    hive.",
  "counts": "def hive_step(hive):\n    hive.counts.",
  "house": HOUSE + "        s.",
  "houseself": HOUSE + "        self.",
  "global": HEAD + "        For",
  "super": HEAD + "        super().",
};
const out = {};
for (const [k, text] of Object.entries(probes)) {
  const res = hint(fakeCm(text));
  out[k] = res ? res.list.map((x) => x.m.name) : [];
}
out.markdown = renderMarkdown("# Т\n\n| a | b |\n|---|---|\n| `x<y` | **ж** |\n\n```\nprint(1)\n```\n- один\n- два");
console.log(JSON.stringify(out));
