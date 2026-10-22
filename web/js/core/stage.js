// Сцена three.js, общая для модулей: рендерер, небо, туман, свет, камера-орбита, «следить».
// Координаты: мир симуляции (x, y, z вверх) → three (x, z, −y); перевод — toThree().

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

/**
 * Уровни качества графики (DECISIONS №45). Когда встроенная видеокарта загружена до упора,
 * GPU-процесс браузера отнимает CPU у симуляции: на i3-8145U + UHD 620 при 60 FPS на весь экран
 * живой матч шёл в 0.1–0.2 реального времени, при 30 FPS — в 1.0. Поэтому по умолчанию 30 FPS
 * (кадры симуляции 10 Гц всё равно интерполируются), 60 FPS — «Высокое» для дискретных видеокарт;
 * при отставании живого матча вьюер сам переходит на уровень ниже.
 * Сглаживание (MSAA) задаётся при создании контекста — его смена требует перезагрузки.
 */
export const QUALITY = {
  high: { label: "Высокое", dpr: 1.5, aa: true, fps: 60 },
  medium: { label: "Среднее", dpr: 1.0, aa: true, fps: 30 },
  low: { label: "Экономное", dpr: 0.75, aa: false, fps: 30 },
};
export const QUALITY_ORDER = ["high", "medium", "low"];
const QUALITY_KEY = "swarmlab.quality";

/** Качество из адреса (?quality=low) или сохранённое; по умолчанию «Среднее». */
export function savedQuality() {
  const fromUrl = new URLSearchParams(location.search).get("quality");
  if (fromUrl && QUALITY[fromUrl]) return fromUrl;
  try {
    const v = localStorage.getItem(QUALITY_KEY);
    if (v && QUALITY[v]) return v;
  } catch {
    /* без хранилища — по умолчанию */
  }
  return "medium";
}

export function saveQuality(name) {
  try {
    localStorage.setItem(QUALITY_KEY, name);
  } catch {
    /* не важно */
  }
}

export function toThree(out, x, y, z) {
  out.set(x, z, -y);
  return out;
}

const SKY_VERT = `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  vec4 p = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * p;
  gl_Position.z = gl_Position.w; // всегда на дальней плоскости
}`;

const SKY_FRAG = `
uniform vec3 uTop;
uniform vec3 uHorizon;
uniform vec3 uBottom;
varying vec3 vDir;
void main() {
  float h = vDir.y;
  vec3 c = h > 0.0 ? mix(uHorizon, uTop, pow(clamp(h, 0.0, 1.0), 0.6))
                   : mix(uHorizon, uBottom, clamp(-h * 4.0, 0.0, 1.0));
  gl_FragColor = vec4(c, 1.0);
  #include <colorspace_fragment>
}`;

export class Stage {
  constructor(container) {
    this.container = container;
    this.qualityName = savedQuality();
    this.quality = QUALITY[this.qualityName];
    this.antialias = this.quality.aa;
    const renderer = new THREE.WebGLRenderer({ antialias: this.antialias, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.quality.dpr));
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    const scene = new THREE.Scene();
    this.scene = scene;
    this.fog = new THREE.Fog(0xcfe3f2, 150, 600);
    scene.fog = this.fog;

    this.camera = new THREE.PerspectiveCamera(55, container.clientWidth / container.clientHeight, 0.3, 3000);
    this.camera.position.set(-120, 110, 160);

    this.controls = new OrbitControls(this.camera, renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.controls.minDistance = 2;
    this.controls.maxDistance = 900;
    this.controls.screenSpacePanning = false;

    this.skyUniforms = {
      uTop: { value: new THREE.Color(0x5d9ad6) },
      uHorizon: { value: new THREE.Color(0xd6e8f5) },
      uBottom: { value: new THREE.Color(0x9fb69a) },
    };
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 12),
      new THREE.ShaderMaterial({
        uniforms: this.skyUniforms, vertexShader: SKY_VERT, fragmentShader: SKY_FRAG,
        side: THREE.BackSide, depthWrite: false, fog: false,
      }),
    );
    sky.scale.setScalar(2000);
    sky.frustumCulled = false;
    sky.renderOrder = -1;
    this.sky = sky;
    scene.add(sky);

    this.hemi = new THREE.HemisphereLight(0xdcecff, 0x5a6b3a, 1.6);
    scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xfff1d6, 2.2);
    this.sun.position.set(-0.6, 1.0, 0.45).multiplyScalar(100);
    scene.add(this.sun);

    this.followGetter = null;
    this._followPos = new THREE.Vector3();
    this._tmp = new THREE.Vector3();
    this._handlers = [];
    this._last = performance.now();

    new ResizeObserver(() => this.resize()).observe(container);
    renderer.setAnimationLoop(() => this._tick());
  }

  /**
   * Сменить качество на лету: разрешение и предел FPS меняются сразу.
   * Возвращает true, если для сглаживания нужна перезагрузка страницы.
   */
  setQuality(name) {
    const q = QUALITY[name];
    if (!q) return false;
    this.qualityName = name;
    this.quality = q;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, q.dpr));
    this.resize();
    return q.aa !== this.antialias;
  }

  resize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  /** Подписка на кадр рендера: fn(dtСекунд). */
  onFrame(fn) {
    this._handlers.push(fn);
  }

  /** Обзор карты размера `size`, м. */
  overview(size, center = new THREE.Vector3()) {
    this.unfollow();
    this.controls.target.copy(center);
    this.camera.position.set(center.x - size * 0.42, center.y + size * 0.36, center.z + size * 0.55);
    this.fog.near = size * 0.45;
    this.fog.far = size * 2.0;
    this.controls.maxDistance = size * 2.5;
    this.camera.far = size * 8;
    this.camera.updateProjectionMatrix();
  }

  /** Подлететь к точке (three) с расстоянием dist. */
  flyTo(point, dist = 30) {
    this.unfollow();
    const dir = this._tmp.copy(this.camera.position).sub(this.controls.target).normalize();
    this.controls.target.copy(point);
    this.camera.position.copy(point).addScaledVector(dir, dist);
  }

  /** «Следить»: getter(out: Vector3) → true, пока цель жива. */
  follow(getter) {
    this.followGetter = getter;
    this._followStarted = false;
  }

  unfollow() {
    this.followGetter = null;
  }

  /** Настроение неба: цвета верха, горизонта, тумана, сила света. */
  setMood({ top, horizon, bottom, light = 1 }) {
    this.skyUniforms.uTop.value.copy(top);
    this.skyUniforms.uHorizon.value.copy(horizon);
    this.skyUniforms.uBottom.value.copy(bottom);
    this.fog.color.copy(horizon);
    this.hemi.intensity = 1.6 * light;
    this.sun.intensity = 2.2 * light * light;
  }

  /** Экранные координаты точки (three) в пикселях холста; null — за камерой. */
  project(p, out) {
    const v = this._tmp.copy(p).project(this.camera);
    if (v.z > 1 || v.z < -1) return null;
    const el = this.renderer.domElement;
    out.x = ((v.x + 1) / 2) * el.clientWidth;
    out.y = ((1 - v.y) / 2) * el.clientHeight;
    return out;
  }

  _tick() {
    const now = performance.now();
    // Предел FPS: лишние кадры не рисуем — меньше нагрузка на GPU и общий с CPU лимит питания.
    if (this.quality.fps < 60 && now - this._last < 1000 / this.quality.fps - 6) return;
    const dt = Math.min((now - this._last) / 1000, 0.25);
    this._last = now;
    for (const fn of this._handlers) fn(dt);
    if (this.followGetter) {
      if (this.followGetter(this._followPos)) {
        if (!this._followStarted) {
          this._followStarted = true;
          const dir = this._tmp.copy(this.camera.position).sub(this.controls.target);
          const len = Math.min(Math.max(dir.length(), 6), 14);
          dir.setLength(len);
          this.controls.target.copy(this._followPos);
          this.camera.position.copy(this._followPos).add(dir);
        } else {
          const delta = this._tmp.copy(this._followPos).sub(this.controls.target);
          this.controls.target.add(delta);
          this.camera.position.add(delta);
        }
      } else {
        this.followGetter = null;
        this.onFollowLost?.();
      }
    }
    this.controls.update();
    this.sky.position.copy(this.camera.position);
    this.renderer.render(this.scene, this.camera);
    this.afterRender?.(dt);
  }
}
