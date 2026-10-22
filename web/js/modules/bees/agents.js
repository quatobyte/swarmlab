// Пчёлы и шершни: InstancedMesh на тип, интерполяция между кадрами по uid, ориентация по скорости.
// Разведчик — тонкий и вытянутый, сборщик — круглый, охранник — крупный, угловатый, с жалом.
// Цвет инстанса = цвет команды; чёрные полоски остаются чёрными (цвет вершин × цвет инстанса).

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { dequantize } from "../../core/codec.js";

const dummy = new THREE.Object3D();
dummy.rotation.order = "YXZ";
const tmpColor = new THREE.Color();
const WHITE = new THREE.Color(1, 1, 1);
const FLEE = new THREE.Color(0.62, 0.62, 0.72);
const ROB = new THREE.Color(1.0, 0.45, 0.4);

// ------------------------------------------------------------------ геометрия

/** Часть модели: геометрия → без индексов, с цветом вершин (число или функция от позиции). */
function part(geo, shade, matrix) {
  let g = geo.index ? geo.toNonIndexed() : geo;
  g.deleteAttribute("uv");
  if (matrix) g.applyMatrix4(matrix);
  const pos = g.attributes.position;
  const col = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const c = typeof shade === "function" ? shade(pos.getX(i), pos.getY(i), pos.getZ(i)) : shade;
    const [r, gg, b] = Array.isArray(c) ? c : [c, c, c];
    col[3 * i] = r;
    col[3 * i + 1] = gg;
    col[3 * i + 2] = b;
  }
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  return g;
}

const M = (x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1, rx = 0, ry = 0, rz = 0) =>
  new THREE.Matrix4().compose(
    new THREE.Vector3(x, y, z),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)),
    new THREE.Vector3(sx, sy, sz),
  );

const DARK = 0.13;
const WING = 2.3; // > 1: крылья светлее цвета команды (пастель)
const stripes = (freq, duty, z0) => (x, y, z) => ((((z - z0) * freq) % 1) + 1) % 1 < duty ? DARK : 1;

/** Модели вдоль +z (вперёд), единица ≈ радиус тела пчелы. */
function beeGeometry(kind) {
  const parts = [];
  if (kind === "scout") {
    parts.push(part(new THREE.SphereGeometry(1, 12, 8), stripes(1.6, 0.35, 0.3), M(0, 0, -0.2, 0.55, 0.55, 1.45)));
    parts.push(part(new THREE.SphereGeometry(0.42, 8, 6), DARK, M(0, 0.05, 1.35)));
    for (const s of [-1, 1]) {
      parts.push(part(new THREE.SphereGeometry(1, 8, 4), WING, M(s * 0.95, 0.55, 0.15, 1.05, 0.05, 0.32, 0, s * 0.35, s * 0.1)));
      parts.push(part(new THREE.CylinderGeometry(0.04, 0.04, 0.9, 3), DARK, M(s * 0.25, 0.45, 1.85, 1, 1, 1, 0.9, 0, -s * 0.4)));
    }
  } else if (kind === "forager") {
    parts.push(part(new THREE.SphereGeometry(1, 14, 10), stripes(2.0, 0.38, 0.1), M(0, 0, -0.2, 0.92, 0.85, 1.12)));
    parts.push(part(new THREE.SphereGeometry(0.5, 8, 6), DARK, M(0, 0.08, 1.0)));
    for (const s of [-1, 1]) {
      parts.push(part(new THREE.SphereGeometry(1, 8, 4), WING, M(s * 0.75, 0.8, 0.1, 0.72, 0.06, 0.42, 0, s * 0.25, s * 0.25)));
    }
  } else {
    parts.push(part(new THREE.IcosahedronGeometry(1, 1), stripes(1.5, 0.45, 0.2), M(0, 0, -0.35, 0.95, 0.9, 1.3)));
    parts.push(part(new THREE.IcosahedronGeometry(0.62, 0), DARK, M(0, 0.1, 1.0)));
    parts.push(part(new THREE.ConeGeometry(0.2, 0.75, 5), DARK, M(0, -0.05, -1.95, 1, 1, 1, -Math.PI / 2, 0, 0)));
    for (const s of [-1, 1]) {
      parts.push(part(new THREE.SphereGeometry(1, 6, 3), WING, M(s * 0.8, 0.85, 0.15, 0.8, 0.06, 0.5, 0, s * 0.3, s * 0.3)));
      parts.push(part(new THREE.ConeGeometry(0.1, 0.45, 4), DARK, M(s * 0.28, -0.1, 1.5, 1, 1, 1, Math.PI / 2, 0, s * 0.5)));
    }
  }
  return mergeGeometries(parts);
}

function hornetGeometry() {
  // Шершень — оранжево-бурый с чёрным, не путается с жёлтым ульем.
  const O = [0.95, 0.38, 0.04];
  const B = [0.08, 0.05, 0.04];
  const body = (x, y, z) => (((((z + 3) * 2.2) % 1) + 1) % 1 < 0.42 ? B : O);
  return mergeGeometries([
    part(new THREE.SphereGeometry(1, 14, 9), body, M(0, 0, -0.55, 0.78, 0.74, 1.35)),
    part(new THREE.SphereGeometry(0.55, 10, 7), [0.3, 0.1, 0.05], M(0, 0.05, 0.75)),
    part(new THREE.SphereGeometry(0.48, 8, 6), [0.85, 0.15, 0.05], M(0, 0.05, 1.45)),
    part(new THREE.ConeGeometry(0.15, 0.6, 5), B, M(0, -0.1, -2.15, 1, 1, 1, -Math.PI / 2, 0, 0)),
    ...[-1, 1].map((s) =>
      part(new THREE.SphereGeometry(1, 8, 4), [0.75, 0.62, 0.42], M(s * 0.9, 0.62, 0.35, 0.95, 0.05, 0.38, 0, s * 0.3, s * 0.15))),
  ]);
}

// ------------------------------------------------------------------ подготовка кадров

/** Позиции и скорости кадра в координатах three — считаются один раз на кадр. */
function prepGroup(frame, prefix, lo, hi) {
  const A = frame.arrays;
  const q = A[`${prefix}_pos`];
  const n = q.length / 3;
  const w = dequantize(q, lo, hi);
  const v = A[`${prefix}_vel`];
  const pos = new Float32Array(n * 3);
  const vel = new Float32Array(n * 3);
  const map = new Map();
  const uid = A[`${prefix}_uid`];
  for (let i = 0; i < n; i++) {
    pos[3 * i] = w[3 * i];
    pos[3 * i + 1] = w[3 * i + 2];
    pos[3 * i + 2] = -w[3 * i + 1];
    vel[3 * i] = v[3 * i];
    vel[3 * i + 1] = v[3 * i + 2];
    vel[3 * i + 2] = -v[3 * i + 1];
    map.set(uid[i], i);
  }
  return { n, pos, vel, map, uid };
}

function prep(frame, scene) {
  if (!frame._prep) {
    frame._prep = {
      bee: prepGroup(frame, "bee", scene.pos_lo, scene.pos_hi),
      hornet: prepGroup(frame, "hornet", scene.pos_lo, scene.pos_hi),
    };
  }
  return frame._prep;
}

// ------------------------------------------------------------------ агенты

export class Agents {
  constructor(scene, hiveColors) {
    this.scene = scene;
    this.kinds = scene.kinds; // ["scout", "forager", "guard"]
    this.perHive = scene.per_hive;
    this.hiveColors = hiveColors;
    this.fallingState = scene.states.indexOf("falling");
    this.scale = 3; // масштаб для видимости (реальные радиусы 0.2–0.4 м)
    this.group = new THREE.Group();
    this.group.name = "bees-agents";

    const slots = scene.bee_slots;
    this.meshes = this.kinds.map((k) => {
      const mat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: k === "guard" });
      const mesh = new THREE.InstancedMesh(beeGeometry(k), mat, slots);
      mesh.setColorAt(0, WHITE);
      mesh.count = 0;
      mesh.frustumCulled = false;
      mesh.name = `bees-${k}`;
      this.group.add(mesh);
      return mesh;
    });
    this.radius = this.kinds.map((k) => scene.bee_radius[k]);
    this.cargo = new THREE.InstancedMesh(
      new THREE.SphereGeometry(0.5, 8, 6),
      new THREE.MeshLambertMaterial({ color: "#ffb300", emissive: "#6a3a00" }),
      slots,
    );
    this.cargo.count = 0;
    this.cargo.frustumCulled = false;
    this.group.add(this.cargo);

    const hs = Math.max(scene.hornet_slots, 1);
    this.hornets = new THREE.InstancedMesh(
      hornetGeometry(), new THREE.MeshLambertMaterial({ vertexColors: true }), hs);
    this.hornets.setColorAt(0, WHITE);
    this.hornets.count = 0;
    this.hornets.frustumCulled = false;
    this.group.add(this.hornets);
    this.heat = new THREE.InstancedMesh(
      new THREE.IcosahedronGeometry(1, 2),
      new THREE.MeshBasicMaterial({
        color: "#ff5a00", transparent: true, opacity: 0.45, depthWrite: false, fog: false,
      }),
      hs,
    );
    this.heat.count = 0;
    this.heat.frustumCulled = false;
    this.heat.renderOrder = 3;
    this.group.add(this.heat);

    // Метка выбранной цели «следить».
    this.marker = new THREE.Mesh(
      new THREE.TorusGeometry(1, 0.06, 6, 32),
      new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.9, depthTest: false, fog: false }),
    );
    this.marker.rotation.x = Math.PI / 2;
    this.marker.renderOrder = 5;
    this.marker.visible = false;
    this.group.add(this.marker);

    this.yaw = new Float32Array(slots + hs);
    this.pitch = new Float32Array(slots + hs);
    // Что нарисовано в последнем кадре: для клика и «следить».
    this.drawn = { pos: new Float32Array((slots + hs) * 3), uid: new Int32Array(slots + hs), n: 0, index: new Map() };
    this.info = new Map(); // uid → сведения для панели
    this.clock = 0;
  }

  /** Ориентация по скорости; на малой скорости — прежний курс. */
  _orient(key, vx, vy, vz) {
    const h = Math.hypot(vx, vz);
    if (h + Math.abs(vy) > 0.35) {
      this.yaw[key] = Math.atan2(vx, vz);
      this.pitch[key] = Math.max(-0.7, Math.min(0.7, -Math.atan2(vy, Math.max(h, 1e-3))));
    }
    dummy.rotation.set(this.pitch[key], this.yaw[key], 0);
  }

  update(sample, dt) {
    this.clock += dt;
    const scene = this.scene;
    const { a, b, alpha } = sample;
    const pa = prep(a, scene);
    const pb = b ? prep(b, scene) : null;
    const A = a.arrays;
    const drawn = this.drawn;
    drawn.n = 0;
    drawn.index.clear();
    this.info.clear();

    // ---- пчёлы
    const counts = [0, 0, 0];
    let nCargo = 0;
    const g = pa.bee;
    for (let i = 0; i < g.n; i++) {
      const uid = g.uid[i];
      const j = pb ? pb.bee.map.get(uid) : undefined;
      let x = g.pos[3 * i], y = g.pos[3 * i + 1], z = g.pos[3 * i + 2];
      let vx = g.vel[3 * i], vy = g.vel[3 * i + 1], vz = g.vel[3 * i + 2];
      if (j !== undefined) {
        const P = pb.bee.pos, V = pb.bee.vel;
        x += alpha * (P[3 * j] - x); y += alpha * (P[3 * j + 1] - y); z += alpha * (P[3 * j + 2] - z);
        vx += alpha * (V[3 * j] - vx); vy += alpha * (V[3 * j + 1] - vy); vz += alpha * (V[3 * j + 2] - vz);
      }
      const kind = A.bee_kind[i];
      const slot = A.bee_slot[i];
      const hive = Math.floor(slot / this.perHive);
      const mesh = this.meshes[kind];
      if (!mesh) continue;
      const s = this.radius[kind] * this.scale;
      this._orient(slot, vx, vy, vz);
      if (A.bee_state[i] === this.fallingState) dummy.rotation.z = this.clock * 9 + slot;
      dummy.position.set(x, y, z);
      dummy.scale.setScalar(s);
      dummy.updateMatrix();
      const k = counts[kind]++;
      mesh.setMatrixAt(k, dummy.matrix);
      mesh.setColorAt(k, this.hiveColors[hive] || WHITE);
      const cargo = A.bee_cargo[i] / 255;
      if (cargo > 0.02) {
        dummy.position.set(x, y - s * 0.75, z);
        dummy.scale.setScalar(s * (0.35 + 0.45 * cargo));
        dummy.updateMatrix();
        this.cargo.setMatrixAt(nCargo++, dummy.matrix);
      }
      this._draw(uid, x, y, z);
      this.info.set(uid, {
        type: "bee", kind: this.kinds[kind], hive, energy: A.bee_energy[i] / 255, cargo,
        falling: A.bee_state[i] === this.fallingState, speed: Math.hypot(vx, vy, vz), pos: [x, y, z],
        radius: s,
      });
    }
    this.meshes.forEach((m, k) => {
      m.count = counts[k];
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    });
    this.cargo.count = nCargo;
    this.cargo.instanceMatrix.needsUpdate = true;

    // ---- шершни
    const h = pa.hornet;
    let nH = 0;
    let nHeat = 0;
    const hs = scene.hornet_radius * this.scale * 1.25;
    for (let i = 0; i < h.n; i++) {
      const uid = h.uid[i];
      const j = pb ? pb.hornet.map.get(uid) : undefined;
      let x = h.pos[3 * i], y = h.pos[3 * i + 1], z = h.pos[3 * i + 2];
      let vx = h.vel[3 * i], vy = h.vel[3 * i + 1], vz = h.vel[3 * i + 2];
      if (j !== undefined) {
        const P = pb.hornet.pos, V = pb.hornet.vel;
        x += alpha * (P[3 * j] - x); y += alpha * (P[3 * j + 1] - y); z += alpha * (P[3 * j + 2] - z);
        vx += alpha * (V[3 * j] - vx); vy += alpha * (V[3 * j + 1] - vy); vz += alpha * (V[3 * j + 2] - vz);
      }
      const flags = A.hornet_flags[i];
      this._orient(scene.bee_slots + A.hornet_slot[i], vx, vy, vz);
      dummy.position.set(x, y, z);
      dummy.scale.setScalar(hs);
      dummy.updateMatrix();
      this.hornets.setMatrixAt(nH, dummy.matrix);
      if (flags & 1) tmpColor.copy(FLEE);
      else if (flags & 4) tmpColor.copy(WHITE).lerp(ROB, 0.5 + 0.5 * Math.sin(this.clock * 10));
      else tmpColor.copy(WHITE);
      this.hornets.setColorAt(nH++, tmpColor);
      if (flags & 2) {
        const r = (scene.hornet_radius + 1.0) * this.scale * (1 + 0.15 * Math.sin(this.clock * 9 + i));
        dummy.rotation.set(this.clock, this.clock * 0.7, 0);
        dummy.scale.setScalar(r);
        dummy.updateMatrix();
        this.heat.setMatrixAt(nHeat++, dummy.matrix);
      }
      this._draw(uid, x, y, z);
      this.info.set(uid, {
        type: "hornet", hp: A.hornet_hp[i] / 255, fleeing: !!(flags & 1), heatBall: !!(flags & 2),
        robbing: !!(flags & 4), speed: Math.hypot(vx, vy, vz), pos: [x, y, z], radius: hs,
      });
    }
    this.hornets.count = nH;
    this.hornets.instanceMatrix.needsUpdate = true;
    if (this.hornets.instanceColor) this.hornets.instanceColor.needsUpdate = true;
    this.heat.count = nHeat;
    this.heat.instanceMatrix.needsUpdate = true;
    this.heat.material.opacity = 0.38 + 0.14 * Math.sin(this.clock * 6);
  }

  _draw(uid, x, y, z) {
    const d = this.drawn;
    d.pos[3 * d.n] = x;
    d.pos[3 * d.n + 1] = y;
    d.pos[3 * d.n + 2] = z;
    d.uid[d.n] = uid;
    d.index.set(uid, d.n);
    d.n++;
  }

  /** uid ближайшего к точке экрана агента (в пределах radiusPx) или null. */
  pick(stage, x, y, radiusPx = 26) {
    const d = this.drawn;
    const v = new THREE.Vector3();
    const scr = { x: 0, y: 0 };
    let best = null;
    let bestD = radiusPx;
    for (let i = 0; i < d.n; i++) {
      v.set(d.pos[3 * i], d.pos[3 * i + 1], d.pos[3 * i + 2]);
      if (!stage.project(v, scr)) continue;
      const dd = Math.hypot(scr.x - x, scr.y - y);
      if (dd < bestD) {
        bestD = dd;
        best = d.uid[i];
      }
    }
    return best;
  }

  /** Позиция агента в последнем кадре; false — его нет в воздухе. */
  positionOf(uid, out) {
    const i = this.drawn.index.get(uid);
    if (i === undefined) return false;
    out.set(this.drawn.pos[3 * i], this.drawn.pos[3 * i + 1], this.drawn.pos[3 * i + 2]);
    return true;
  }

  setMarker(uid) {
    const inf = uid != null ? this.info.get(uid) : null;
    this.marker.visible = !!inf;
    if (inf) {
      this.marker.position.set(inf.pos[0], inf.pos[1], inf.pos[2]);
      this.marker.scale.setScalar(inf.radius * 2.2 * (1 + 0.08 * Math.sin(this.clock * 5)));
    }
  }
}
