// Погода во вьюере: настроение неба и света, дождь штрихами вокруг камеры (один вызов отрисовки,
// движение капель — в шейдере), снос дождя ветром.

import * as THREE from "three";
import { hash01 } from "./world.js";

const MOODS = {
  clear: { top: "#5d9ad6", horizon: "#d6e8f5", bottom: "#9fb69a", light: 1.0, fog: 1.0 },
  windy: { top: "#6d98c2", horizon: "#dfe6ea", bottom: "#a3b39a", light: 0.92, fog: 0.85 },
  rain: { top: "#56606b", horizon: "#9aa4ac", bottom: "#6f7b6c", light: 0.62, fog: 0.5 },
};
for (const m of Object.values(MOODS)) {
  for (const k of ["top", "horizon", "bottom"]) m[k] = new THREE.Color(m[k]);
}

const RAIN_VERT = `
uniform vec3 uCenter;
uniform vec3 uBox;
uniform float uTime;
uniform vec3 uVel;
uniform float uLen;
attribute vec3 aSeed;
attribute float aEnd;
varying float vA;
void main() {
  vec3 origin = uCenter - 0.5 * uBox;
  vec3 p = mod(aSeed * uBox + uVel * uTime - origin, uBox) + origin;
  p -= normalize(uVel) * uLen * aEnd;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  float d = length(mv.xyz);
  vA = (1.0 - 0.8 * aEnd) * (1.0 - smoothstep(uBox.x * 0.18, uBox.x * 0.5, d));
  gl_Position = projectionMatrix * mv;
}`;

const RAIN_FRAG = `
uniform float uOpacity;
varying float vA;
void main() {
  gl_FragColor = vec4(0.82, 0.87, 0.95, vA * uOpacity);
}`;

export class WeatherFx {
  constructor(stage, mapSize) {
    this.stage = stage;
    this.mapSize = mapSize;
    this.mood = { top: new THREE.Color(), horizon: new THREE.Color(), bottom: new THREE.Color(), light: 1, fog: 1 };
    this.copyMood(MOODS.clear);
    this.rainLevel = 0;
    this.state = "clear";

    const N = 7000;
    const seeds = new Float32Array(N * 2 * 3);
    const ends = new Float32Array(N * 2);
    for (let i = 0; i < N; i++) {
      const s = [hash01(i, 31), hash01(i, 32), hash01(i, 33)];
      for (let e = 0; e < 2; e++) {
        seeds.set(s, (2 * i + e) * 3);
        ends[2 * i + e] = e;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 2 * 3), 3));
    geo.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 3));
    geo.setAttribute("aEnd", new THREE.BufferAttribute(ends, 1));
    this.uniforms = {
      uCenter: { value: new THREE.Vector3() },
      uBox: { value: new THREE.Vector3(70, 36, 70) },
      uTime: { value: 0 },
      uVel: { value: new THREE.Vector3(0, -11, 0) },
      uLen: { value: 0.9 },
      uOpacity: { value: 0 },
    };
    this.rain = new THREE.LineSegments(geo, new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: RAIN_VERT, fragmentShader: RAIN_FRAG,
      transparent: true, depthWrite: false,
    }));
    this.rain.frustumCulled = false;
    this.rain.visible = false;
    this.rain.renderOrder = 4;
    stage.scene.add(this.rain);
    this.baseFog = { near: stage.fog.near, far: stage.fog.far };
  }

  copyMood(m) {
    this.mood.top.copy(m.top);
    this.mood.horizon.copy(m.horizon);
    this.mood.bottom.copy(m.bottom);
    this.mood.light = m.light;
    this.mood.fog = m.fog;
  }

  /** state — "clear" | "windy" | "rain"; wind — вектор ветра мира (x, y), м/с. */
  update(dt, state, wind) {
    this.state = state;
    const target = MOODS[state] || MOODS.clear;
    const k = 1 - Math.exp(-dt * 1.2);
    const m = this.mood;
    m.top.lerp(target.top, k);
    m.horizon.lerp(target.horizon, k);
    m.bottom.lerp(target.bottom, k);
    m.light += (target.light - m.light) * k;
    m.fog += (target.fog - m.fog) * k;
    this.stage.setMood(m);
    this.stage.fog.near = this.mapSize * 0.45 * m.fog;
    this.stage.fog.far = this.mapSize * 2.0 * (0.4 + 0.6 * m.fog);

    const wantRain = state === "rain" ? 1 : 0;
    this.rainLevel += (wantRain - this.rainLevel) * (1 - Math.exp(-dt * 1.5));
    this.rain.visible = this.rainLevel > 0.02;
    if (this.rain.visible) {
      const u = this.uniforms;
      u.uTime.value += dt;
      u.uOpacity.value = 0.6 * this.rainLevel;
      u.uCenter.value.copy(this.stage.camera.position);
      u.uVel.value.set(wind ? wind[0] * 0.8 : 0, -11, wind ? -wind[1] * 0.8 : 0);
    }
  }
}
