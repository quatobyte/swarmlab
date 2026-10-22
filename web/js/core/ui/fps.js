// Счётчик FPS в углу (клавиша F): кадры в секунду, время кадра, вызовы отрисовки, треугольники.

const KEY = "swarmlab.fps";

export class FpsMeter {
  constructor(el, renderer, limit = () => 60) {
    this.el = el;
    this.renderer = renderer;
    this.limit = limit; // предел FPS по качеству графики
    this.frames = 0;
    this.acc = 0;
    this.worst = 0;
    this.fps = 0;
    let visible = false;
    try {
      visible = localStorage.getItem(KEY) === "1";
    } catch {
      /* без хранилища — по умолчанию скрыт */
    }
    this.setVisible(visible);
    window.addEventListener("keydown", (e) => {
      if (e.code === "KeyF" && !e.ctrlKey && !e.metaKey && !isTyping(e)) this.setVisible(!this.visible);
    });
  }

  setVisible(v) {
    this.visible = v;
    this.el.hidden = !v;
    try {
      localStorage.setItem(KEY, v ? "1" : "0");
    } catch {
      /* не важно */
    }
  }

  /** Вызывать после отрисовки каждого кадра. */
  tick(dt) {
    this.frames++;
    this.acc += dt;
    this.worst = Math.max(this.worst, dt);
    if (this.acc < 0.5) return;
    this.fps = this.frames / this.acc;
    if (this.visible) {
      const info = this.renderer.info.render;
      this.el.textContent =
        `FPS ${this.fps.toFixed(0)}${this.limit() < 60 ? ` (предел ${this.limit()})` : ""} · ` +
        `${((this.acc / this.frames) * 1000).toFixed(1)} мс ` +
        `(макс ${(this.worst * 1000).toFixed(0)}) · вызовов ${info.calls} · ` +
        `треуг. ${(info.triangles / 1000).toFixed(0)}k`;
      this.el.classList.toggle("bad", this.fps < 0.9 * Math.min(30, this.limit()));
    }
    this.frames = 0;
    this.acc = 0;
    this.worst = 0;
  }
}

export function isTyping(e) {
  const t = e.target;
  return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}
