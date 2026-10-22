// Статический мир пчёлок из header.scene.world: рельеф, деревья, камни, ульи, цветы, трава.
// Всё повторяющееся — InstancedMesh: один вызов отрисовки на вид объектов.

import * as THREE from "three";

const dummy = new THREE.Object3D();
const color = new THREE.Color();

/** Детерминированный «случайный» 0..1 по индексу (для оттенков и травы). */
export function hash01(i, salt = 0) {
  let h = (i * 374761393 + salt * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

const TERRAIN_STOPS = [
  [0.0, new THREE.Color("#a7c56f")],
  [0.35, new THREE.Color("#7fb04f")],
  [0.7, new THREE.Color("#5a913f")],
  [1.0, new THREE.Color("#8d9064")],
];
const MEADOW = new THREE.Color("#c3d66a");
const ROCKY = new THREE.Color("#8a8466");

function terrainColor(out, h01) {
  for (let i = 1; i < TERRAIN_STOPS.length; i++) {
    const [t1, c1] = TERRAIN_STOPS[i];
    if (h01 <= t1 || i === TERRAIN_STOPS.length - 1) {
      const [t0, c0] = TERRAIN_STOPS[i - 1];
      return out.copy(c0).lerp(c1, Math.min(Math.max((h01 - t0) / (t1 - t0), 0), 1));
    }
  }
  return out;
}

export class BeesWorld {
  constructor(scene) {
    const w = scene.world;
    this.size = w.map_size;
    this.half = w.map_size / 2;
    this.relief = Math.max(w.max_relief, 1e-6);
    this.n = w.terrain.shape[0];
    this.terrain = w.terrain;
    this.group = new THREE.Group();
    this.group.name = "bees-world";

    this._buildTerrain(w);
    this._buildTrees(w);
    this._buildRocks(w);
    this._buildHives(w, scene.hive_colors);
    this._buildFlowers(w);
    this._buildGrass(w);
  }

  /** Высота рельефа в точке мира (x, y), билинейно — как `World.ground_height`. */
  heightAt(x, y) {
    const n = this.n;
    const gx = Math.min(Math.max(((x + this.half) * (n - 1)) / this.size, 0), n - 1);
    const gy = Math.min(Math.max(((y + this.half) * (n - 1)) / this.size, 0), n - 1);
    const ix = Math.min(Math.floor(gx), n - 2);
    const iy = Math.min(Math.floor(gy), n - 2);
    const fx = gx - ix;
    const fy = gy - iy;
    const t = this.terrain;
    const k = iy * n + ix;
    const low = t[k] + (t[k + 1] - t[k]) * fx;
    const high = t[k + n] + (t[k + n + 1] - t[k + n]) * fx;
    return low + (high - low) * fy;
  }

  _buildTerrain(w) {
    const n = this.n;
    const geo = new THREE.PlaneGeometry(this.size, this.size, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2); // строки плоскости: от +y мира (верх) к −y
    const pos = geo.attributes.position;
    for (let row = 0; row < n; row++) {
      const iy = n - 1 - row;
      for (let ix = 0; ix < n; ix++) pos.setY(row * n + ix, this.terrain[iy * n + ix]);
    }
    geo.computeVertexNormals();
    const nrm = geo.attributes.normal;
    const colors = new Float32Array(n * n * 3);
    const fp = w.flower_pos;
    const nf = fp.length / 3;
    for (let k = 0; k < n * n; k++) {
      const x = pos.getX(k);
      const y = -pos.getZ(k);
      terrainColor(color, pos.getY(k) / this.relief);
      // Поляны цветов — светлее и желтее.
      let near = 0;
      for (let f = 0; f < nf; f++) {
        const d2 = (fp[3 * f] - x) ** 2 + (fp[3 * f + 1] - y) ** 2;
        if (d2 < 100) near = Math.max(near, 1 - d2 / 100);
      }
      if (near > 0) color.lerp(MEADOW, 0.55 * near);
      const steep = 1 - nrm.getY(k);
      if (steep > 0.04) color.lerp(ROCKY, Math.min((steep - 0.04) * 6, 0.6));
      const v = 0.94 + 0.12 * hash01(k, 7);
      colors[3 * k] = color.r * v;
      colors[3 * k + 1] = color.g * v;
      colors[3 * k + 2] = color.b * v;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ vertexColors: true }));
    mesh.name = "terrain";
    this.group.add(mesh);

    // Земля за краем карты: туман растворяет её у горизонта.
    const skirt = new THREE.Mesh(
      new THREE.RingGeometry(this.size * 0.7, this.size * 12, 48, 1),
      new THREE.MeshLambertMaterial({ color: "#7c9c55" }),
    );
    skirt.rotation.x = -Math.PI / 2;
    skirt.position.y = -0.05;
    this.group.add(skirt);
    const under = new THREE.Mesh(
      new THREE.PlaneGeometry(this.size * 1.42, this.size * 1.42),
      new THREE.MeshLambertMaterial({ color: "#7c9c55" }),
    );
    under.rotation.x = -Math.PI / 2;
    under.position.y = -0.08;
    this.group.add(under);
  }

  _buildTrees(w) {
    const T = w.tree_trunk_radius.length;
    if (!T) return;
    const trunkGeo = new THREE.CylinderGeometry(0.75, 1, 1, 7);
    trunkGeo.translate(0, 0.5, 0);
    const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshLambertMaterial({ color: "#6b4a2f" }), T);
    const crownGeo = new THREE.IcosahedronGeometry(1, 1);
    const crowns = new THREE.InstancedMesh(
      crownGeo, new THREE.MeshLambertMaterial({ flatShading: true }), T);
    for (let i = 0; i < T; i++) {
      const [x, y, z] = [w.tree_pos[3 * i], w.tree_pos[3 * i + 1], w.tree_pos[3 * i + 2]];
      const r = w.tree_trunk_radius[i];
      const h = w.tree_trunk_height[i];
      const c = w.tree_crown_radius[i];
      dummy.position.set(x, z, -y);
      dummy.rotation.set(0, hash01(i, 1) * 6.28, 0);
      dummy.scale.set(r, h + c * 0.3, r);
      dummy.updateMatrix();
      trunks.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, z + h + c * 0.6, -y);
      dummy.scale.set(c, c * (0.9 + 0.2 * hash01(i, 2)), c);
      dummy.updateMatrix();
      crowns.setMatrixAt(i, dummy.matrix);
      color.setHSL(0.27 + 0.07 * hash01(i, 3), 0.45 + 0.15 * hash01(i, 4), 0.27 + 0.1 * hash01(i, 5));
      crowns.setColorAt(i, color);
    }
    trunks.name = "tree-trunks";
    crowns.name = "tree-crowns";
    this.group.add(trunks, crowns);
  }

  _buildRocks(w) {
    const R = w.rock_yaw.length;
    if (!R) return;
    const rocks = new THREE.InstancedMesh(
      new THREE.DodecahedronGeometry(1, 0), new THREE.MeshLambertMaterial({ flatShading: true }), R);
    for (let i = 0; i < R; i++) {
      const p = w.rock_pos;
      const hlf = w.rock_half;
      dummy.position.set(p[3 * i], p[3 * i + 2], -p[3 * i + 1]);
      dummy.rotation.set(0, w.rock_yaw[i], 0);
      dummy.scale.set(hlf[3 * i] * 1.15, hlf[3 * i + 2] * 1.1, hlf[3 * i + 1] * 1.15);
      dummy.updateMatrix();
      rocks.setMatrixAt(i, dummy.matrix);
      const g = 0.45 + 0.15 * hash01(i, 9);
      rocks.setColorAt(i, color.setRGB(g, g * 0.98, g * 0.93));
    }
    rocks.name = "rocks";
    this.group.add(rocks);
  }

  _buildHives(w, colors) {
    const H = w.hive_pos.length / 3;
    this.hivePos = [];
    this.hiveColors = [];
    const body = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial(), H);
    const roofGeo = new THREE.ConeGeometry(Math.SQRT1_2 * 1.25, 1, 4);
    roofGeo.rotateY(Math.PI / 4);
    const roof = new THREE.InstancedMesh(roofGeo, new THREE.MeshLambertMaterial({ color: "#5b4636", flatShading: true }), H);
    const door = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial({ color: "#1b140e" }), H);
    const ringGeo = new THREE.RingGeometry(0.8, 1, 48);
    ringGeo.rotateX(-Math.PI / 2);
    const ring = new THREE.InstancedMesh(ringGeo, new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2,
    }), H);
    // Луч-маяк над ульем: цвет команды читается издалека; сверху гаснет (аддитивно, чёрный = прозрачный).
    const beamGeo = new THREE.CylinderGeometry(1, 1, 1, 16, 1, true);
    beamGeo.translate(0, 0.5, 0);
    const bc = new Float32Array(beamGeo.attributes.position.count * 3);
    for (let k = 0; k < beamGeo.attributes.position.count; k++) {
      const v = 1 - beamGeo.attributes.position.getY(k);
      bc[3 * k] = bc[3 * k + 1] = bc[3 * k + 2] = v * v;
    }
    beamGeo.setAttribute("color", new THREE.BufferAttribute(bc, 3));
    const beam = new THREE.InstancedMesh(beamGeo, new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending,
      depthWrite: false, side: THREE.DoubleSide, fog: false,
    }), H);
    for (let i = 0; i < H; i++) {
      const [x, y, z] = [w.hive_pos[3 * i], w.hive_pos[3 * i + 1], w.hive_pos[3 * i + 2]];
      const [hx, hy, hz] = [w.hive_half[3 * i], w.hive_half[3 * i + 1], w.hive_half[3 * i + 2]];
      const c = new THREE.Color(colors[i % colors.length] || "#cccccc");
      this.hiveColors.push(c);
      this.hivePos.push(new THREE.Vector3(x, z + hz, -y));
      dummy.rotation.set(0, 0, 0);
      dummy.position.set(x, z, -y);
      dummy.scale.set(2 * hx, 2 * hz, 2 * hy);
      dummy.updateMatrix();
      body.setMatrixAt(i, dummy.matrix);
      body.setColorAt(i, c);
      dummy.position.set(x, z + hz + 0.45, -y);
      dummy.scale.set(2 * hx * 1.1, 0.9, 2 * hy * 1.1);
      dummy.updateMatrix();
      roof.setMatrixAt(i, dummy.matrix);
      const e = w.hive_entrance;
      dummy.position.set(x + hx + 0.01, e[3 * i + 2], -y);
      dummy.scale.set(0.06, 0.35, 0.9);
      dummy.updateMatrix();
      door.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, this.heightAt(x, y) + 0.12, -y);
      dummy.scale.set(7, 1, 7);
      dummy.updateMatrix();
      ring.setMatrixAt(i, dummy.matrix);
      ring.setColorAt(i, c);
      dummy.position.set(x, z + hz + 0.9, -y);
      dummy.scale.set(0.9, 45, 0.9);
      dummy.updateMatrix();
      beam.setMatrixAt(i, dummy.matrix);
      beam.setColorAt(i, c);
    }
    body.name = "hives";
    beam.renderOrder = 2;
    this.group.add(body, roof, door, ring, beam);
  }

  _buildFlowers(w) {
    const F = w.flower_pos.length / 3;
    this.flowerCount = F;
    if (!F) return;
    const stemGeo = new THREE.CylinderGeometry(0.03, 0.04, 1, 4);
    stemGeo.translate(0, 0.5, 0);
    const stems = new THREE.InstancedMesh(stemGeo, new THREE.MeshLambertMaterial({ color: "#3f7a2c" }), F);
    const bloomGeo = new THREE.IcosahedronGeometry(0.42, 0);
    bloomGeo.scale(1, 0.5, 1);
    const blooms = new THREE.InstancedMesh(bloomGeo, new THREE.MeshLambertMaterial({ flatShading: true }), F);
    const spiders = w.flower_spider;
    const nSpiders = spiders.reduce((s, v) => s + (v ? 1 : 0), 0);
    const spiderGeo = new THREE.SphereGeometry(0.14, 6, 4);
    spiderGeo.scale(1, 0.7, 1.3);
    const spiderMesh = new THREE.InstancedMesh(spiderGeo, new THREE.MeshLambertMaterial({ color: "#1a1410" }), Math.max(nSpiders, 1));
    spiderMesh.count = nSpiders;
    const palette = ["#ff6fae", "#b98bff", "#fff4fa", "#ffd23f", "#ff9a3c", "#7fd3ff"].map((c) => new THREE.Color(c));
    this.flowerBase = [];
    let s = 0;
    for (let i = 0; i < F; i++) {
      const [x, y, z] = [w.flower_pos[3 * i], w.flower_pos[3 * i + 1], w.flower_pos[3 * i + 2]];
      const g = this.heightAt(x, y);
      dummy.rotation.set(0, 0, 0);
      dummy.position.set(x, g, -y);
      dummy.scale.set(1, Math.max(z - g, 0.1), 1);
      dummy.updateMatrix();
      stems.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, z, -y);
      dummy.rotation.set(0, hash01(i, 11) * 6.28, 0);
      dummy.scale.setScalar(1);
      dummy.updateMatrix();
      blooms.setMatrixAt(i, dummy.matrix);
      this.flowerBase.push(palette[Math.floor(hash01(i, 12) * palette.length)]);
      if (spiders[i]) {
        dummy.position.set(x + 0.12, z + 0.2, -y);
        dummy.updateMatrix();
        spiderMesh.setMatrixAt(s++, dummy.matrix);
      }
    }
    this.blooms = blooms;
    this.updateFlowers(null);
    stems.name = "flower-stems";
    blooms.name = "flower-blooms";
    this.group.add(stems, blooms, spiderMesh);
  }

  /** Яркость цветка = нектар (доля 0–255); пустой цветок блёкнет. */
  updateFlowers(nectarU8) {
    if (!this.blooms || nectarU8 === this._lastNectar) return;
    this._lastNectar = nectarU8;
    const withered = this._withered ||= new THREE.Color("#8b7d68");
    for (let i = 0; i < this.flowerCount; i++) {
      const f = nectarU8 ? nectarU8[i] / 255 : 1;
      color.copy(withered).lerp(this.flowerBase[i], 0.15 + 0.85 * f);
      this.blooms.setColorAt(i, color);
    }
    this.blooms.instanceColor.needsUpdate = true;
  }

  _buildGrass(w) {
    // Декоративная трава: только для вида, в симуляции её нет.
    const N = Math.round(Math.min(6000, (this.size * this.size) / 18));
    const geo = new THREE.ConeGeometry(0.22, 0.7, 3);
    geo.translate(0, 0.3, 0);
    const grass = new THREE.InstancedMesh(geo, new THREE.MeshLambertMaterial(), N);
    const hp = w.hive_pos;
    const H = hp.length / 3;
    let k = 0;
    for (let i = 0; i < N * 2 && k < N; i++) {
      const x = (hash01(i, 21) - 0.5) * this.size * 0.98;
      const y = (hash01(i, 22) - 0.5) * this.size * 0.98;
      let nearHive = false;
      for (let h = 0; h < H; h++) {
        if ((hp[3 * h] - x) ** 2 + (hp[3 * h + 1] - y) ** 2 < 64) nearHive = true;
      }
      if (nearHive) continue;
      dummy.position.set(x, this.heightAt(x, y), -y);
      dummy.rotation.set((hash01(i, 23) - 0.5) * 0.4, hash01(i, 24) * 6.28, 0);
      dummy.scale.setScalar(0.7 + 0.8 * hash01(i, 25));
      dummy.updateMatrix();
      grass.setMatrixAt(k, dummy.matrix);
      color.setHSL(0.22 + 0.08 * hash01(i, 26), 0.5, 0.3 + 0.12 * hash01(i, 27));
      grass.setColorAt(k, color);
      k++;
    }
    grass.count = k;
    grass.name = "grass";
    this.group.add(grass);
  }
}
