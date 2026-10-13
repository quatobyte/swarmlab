"""Генерация мира пчёлок по seed (BEES_SPEC §1).

Мир — это только данные (массивы NumPy): рельеф, деревья, камни, ульи, цветы.
Физическая модель собирается из него отдельно (`bees.physics.mjcf`), вьюеры и
сенсоры читают те же массивы. Вся случайность — из `rng("world")`, поэтому один
seed даёт один и тот же мир.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields

import numpy as np

from swarmlab.bees.params import FlowerParams, HiveGeomParams, TerrainParams, WorldParams
from swarmlab.core.rng import RngRegistry

#: Отступ ульев от края карты, м.
_HIVE_EDGE_MARGIN = 20.0
#: Ульи и камни немного утоплены в рельеф, чтобы на склоне не было щели снизу, м.
_SINK = 0.3


@dataclass(frozen=True, eq=False)
class World:
    """Статический мир матча. Координаты: центр карты в (0, 0), ось z вверх.

    Все массивы — структура массивов: i-я строка каждого массива группы описывает
    i-й объект. Рельеф `terrain[iy, ix]` — высоты узлов сетки, `iy` растёт по +y.
    """

    map_size: float
    ceiling_agl: float
    terrain: np.ndarray  # (n, n) высоты узлов, м, от 0 до max_relief
    max_relief: float

    tree_pos: np.ndarray  # (T, 3) основание ствола
    tree_trunk_radius: np.ndarray  # (T,)
    tree_trunk_height: np.ndarray  # (T,)
    tree_crown_radius: np.ndarray  # (T,)

    rock_pos: np.ndarray  # (R, 3) центр бокса
    rock_half: np.ndarray  # (R, 3) полуразмеры
    rock_yaw: np.ndarray  # (R,) поворот вокруг z, рад

    hive_pos: np.ndarray  # (H, 3) центр бокса
    hive_half: np.ndarray  # (H, 3) полуразмеры
    hive_entrance: np.ndarray  # (H, 3) точка летка

    flower_pos: np.ndarray  # (F, 3)
    flower_nectar: np.ndarray  # (F,) нектар, ед.
    flower_hive: np.ndarray  # (F,) улей, для которого генерировалась поляна
    flower_spider: np.ndarray  # (F,) bool — на цветке паук

    @property
    def n_hives(self) -> int:
        return int(self.hive_pos.shape[0])

    @property
    def half_size(self) -> float:
        return self.map_size / 2

    def ground_height(self, xy: np.ndarray) -> np.ndarray:
        """Высота рельефа в точках `xy` формы `(..., 2)` (билинейная интерполяция узлов)."""
        xy = np.asarray(xy, dtype=np.float64)
        n = self.terrain.shape[0]
        g = (xy + self.half_size) * ((n - 1) / self.map_size)
        g = np.clip(g, 0.0, n - 1)
        i = np.minimum(g.astype(np.int64), n - 2)
        f = g - i
        ix, iy = i[..., 0], i[..., 1]
        fx, fy = f[..., 0], f[..., 1]
        t = self.terrain
        return (
            t[iy, ix] * (1 - fx) * (1 - fy)
            + t[iy, ix + 1] * fx * (1 - fy)
            + t[iy + 1, ix] * (1 - fx) * fy
            + t[iy + 1, ix + 1] * fx * fy
        )

    def digests(self) -> dict[str, str]:
        """SHA-256 по группам массивов: рельеф, препятствия, ульи, цветы."""
        groups = {
            "terrain": ("terrain",),
            "obstacles": (
                "tree_pos",
                "tree_trunk_radius",
                "tree_trunk_height",
                "tree_crown_radius",
                "rock_pos",
                "rock_half",
                "rock_yaw",
            ),
            "hives": ("hive_pos", "hive_half", "hive_entrance"),
            "flowers": ("flower_pos", "flower_nectar", "flower_hive", "flower_spider"),
        }
        return {group: _hash_arrays(self, names) for group, names in groups.items()}

    def digest(self) -> str:
        """SHA-256 всего мира (все массивы и скалярные параметры)."""
        names = tuple(f.name for f in fields(self))
        return _hash_arrays(self, names)


def _hash_arrays(world: World, names: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for name in names:
        value = np.ascontiguousarray(getattr(world, name))
        h.update(name.encode())
        h.update(str(value.dtype).encode())
        h.update(str(value.shape).encode())
        h.update(value.tobytes())
    return h.hexdigest()


def generate_world(
    params: WorldParams,
    rng: RngRegistry,
    *,
    spiders_enabled: bool = False,
    spider_fraction: float = 0.0,
) -> World:
    """Построить мир. Порядок обращений к `rng("world")` фиксирован — не менять без нужды."""
    gen = rng.get("world")
    size = params.map_size

    terrain = _fbm_terrain(gen, params.terrain)
    proto = _TerrainView(size, terrain)

    hive_xy = _hive_layout(gen, params.n_hives, params.hives.spacing, size)
    hive_pos, hive_half, hive_entrance = _hive_boxes(proto, hive_xy, params.hives)

    flower_pos, flower_hive, cluster_centers = _flowers(gen, proto, hive_xy, params.flowers)
    n_flowers = flower_pos.shape[0]
    flower_spider = np.zeros(n_flowers, dtype=bool)
    if spiders_enabled and n_flowers:
        # Отдельный поток: включение пауков не меняет остальной мир.
        n_spiders = round(spider_fraction * n_flowers)
        picked = rng.get("world.spiders").choice(n_flowers, size=n_spiders, replace=False)
        flower_spider[picked] = True

    # Деревья и камни не ставим на поляны и ближе hive_clearance к ульям.
    keep_out = [(hive_xy, params.trees.hive_clearance)]
    if cluster_centers.size:
        keep_out.append((cluster_centers, params.flowers.cluster_radius + 2.0))
    t = params.trees
    tree_xy = _scatter(gen, _count(t.per_ha, size), size, t.edge_margin, keep_out)
    n_trees = tree_xy.shape[0]
    tree_trunk_radius = gen.uniform(*t.trunk_radius, n_trees)
    tree_trunk_height = gen.uniform(*t.trunk_height, n_trees)
    tree_crown_radius = gen.uniform(*t.crown_radius, n_trees)
    tree_pos = np.column_stack([tree_xy, proto.ground_height(tree_xy) - _SINK])

    r = params.rocks
    keep_out[0] = (hive_xy, r.hive_clearance)
    keep_out.append((tree_xy, 3.0))
    rock_xy = _scatter(gen, _count(r.per_ha, size), size, r.edge_margin, keep_out)
    n_rocks = rock_xy.shape[0]
    rock_half = gen.uniform(*r.half_size, (n_rocks, 3))
    rock_yaw = gen.uniform(0.0, 2 * np.pi, n_rocks)
    rock_pos = np.column_stack([rock_xy, proto.ground_height(rock_xy) + rock_half[:, 2] * 0.5])

    return World(
        map_size=float(size),
        ceiling_agl=float(params.ceiling_agl),
        terrain=terrain,
        max_relief=float(params.terrain.max_relief),
        tree_pos=tree_pos,
        tree_trunk_radius=tree_trunk_radius,
        tree_trunk_height=tree_trunk_height,
        tree_crown_radius=tree_crown_radius,
        rock_pos=rock_pos,
        rock_half=rock_half,
        rock_yaw=rock_yaw,
        hive_pos=hive_pos,
        hive_half=hive_half,
        hive_entrance=hive_entrance,
        flower_pos=flower_pos,
        flower_nectar=np.full(n_flowers, params.flowers.nectar_max),
        flower_hive=flower_hive,
        flower_spider=flower_spider,
    )


# ------------------------------------------------------------------ рельеф


@dataclass(frozen=True)
class _TerrainView:
    """Рельеф без остального мира — нужен, пока мир ещё строится."""

    map_size: float
    terrain: np.ndarray

    @property
    def half_size(self) -> float:
        return self.map_size / 2

    ground_height = World.ground_height


def _fbm_terrain(gen: np.random.Generator, p: TerrainParams) -> np.ndarray:
    """fBm из value-noise: сумма октав со сглаженной билинейной интерполяцией решёток."""
    out = np.zeros((p.grid, p.grid))
    amp = 1.0
    for octave in range(p.octaves):
        cells = p.base_cells * 2**octave
        lattice = gen.random((cells + 1, cells + 1))
        out += amp * _upsample(lattice, p.grid)
        amp *= p.persistence
    out -= out.min()
    peak = out.max()
    if peak > 0:
        out *= p.max_relief / peak
    return out


def _upsample(lattice: np.ndarray, n: int) -> np.ndarray:
    cells = lattice.shape[0] - 1
    t = np.linspace(0.0, cells, n)
    i = np.minimum(t.astype(np.int64), cells - 1)
    f = t - i
    f = f * f * (3 - 2 * f)  # smoothstep — без «гранёных» склонов
    rows = lattice[i] * (1 - f)[:, None] + lattice[i + 1] * f[:, None]
    return rows[:, i] * (1 - f)[None, :] + rows[:, i + 1] * f[None, :]


# ------------------------------------------------------------------ ульи


def _hive_layout(gen: np.random.Generator, n: int, spacing: float, size: float) -> np.ndarray:
    """1 улей — в центре; 2 — на отрезке; 3 — вершины равностороннего треугольника."""
    if n == 1:
        return np.zeros((1, 2))
    radius = spacing / 2 if n == 2 else spacing / np.sqrt(3)
    radius = min(radius, size / 2 - _HIVE_EDGE_MARGIN)
    phase = gen.uniform(0.0, 2 * np.pi)
    angles = phase + 2 * np.pi * np.arange(n) / n
    return radius * np.column_stack([np.cos(angles), np.sin(angles)])


def _hive_boxes(
    terrain: _TerrainView, hive_xy: np.ndarray, p: HiveGeomParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hx, hy = p.half_size
    corners = np.array([[0, 0], [hx, hy], [hx, -hy], [-hx, hy], [-hx, -hy]], dtype=np.float64)
    ground = terrain.ground_height(hive_xy[:, None, :] + corners[None, :, :])  # (H, 5)
    bottom = ground.min(axis=1) - _SINK
    top = ground.max(axis=1) + p.height
    pos = np.column_stack([hive_xy, (bottom + top) / 2])
    half = np.column_stack(
        [np.full(len(hive_xy), hx), np.full(len(hive_xy), hy), (top - bottom) / 2]
    )
    # Леток — перед гранью +x.
    entrance_xy = hive_xy + np.array([hx + p.entrance_offset, 0.0])
    entrance_z = terrain.ground_height(entrance_xy) + p.entrance_height
    return pos, half, np.column_stack([entrance_xy, entrance_z])


# ------------------------------------------------------------------ цветы


def _flowers(
    gen: np.random.Generator, terrain: _TerrainView, hive_xy: np.ndarray, p: FlowerParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Поляны: у каждого улья одинаковый набор расстояний до полян (честность)."""
    n_hives = hive_xy.shape[0]
    distances = np.sort(gen.uniform(*p.cluster_distance, p.clusters_per_hive))
    limit = terrain.half_size - p.edge_margin - p.cluster_radius

    centers: list[np.ndarray] = []
    owners: list[int] = []
    for h in range(n_hives):
        others = np.delete(hive_xy, h, axis=0)
        for d in distances:
            centers.append(_place_cluster(gen, hive_xy[h], others, float(d), limit))
            owners.append(h)

    n_per = p.flowers_per_cluster
    if not centers or n_per == 0:
        return np.zeros((0, 3)), np.zeros(0, dtype=np.int64), np.zeros((0, 2))
    center_arr = np.array(centers)
    radius = p.cluster_radius * np.sqrt(gen.random((len(centers), n_per)))
    angle = gen.uniform(0.0, 2 * np.pi, (len(centers), n_per))
    offsets = np.stack([radius * np.cos(angle), radius * np.sin(angle)], axis=-1)
    xy = (center_arr[:, None, :] + offsets).reshape(-1, 2)
    z = terrain.ground_height(xy) + p.height
    hive = np.repeat(np.array(owners, dtype=np.int64), n_per)
    return np.column_stack([xy, z]), hive, center_arr


def _place_cluster(
    gen: np.random.Generator,
    hive: np.ndarray,
    others: np.ndarray,
    distance: float,
    limit: float,
) -> np.ndarray:
    """Центр поляны на расстоянии `distance` от улья: внутри карты и ближе к своему улью."""
    for _ in range(20):
        for _ in range(32):
            angle = gen.uniform(0.0, 2 * np.pi)
            c = hive + distance * np.array([np.cos(angle), np.sin(angle)])
            inside = bool(np.all(np.abs(c) <= limit))
            own = others.size == 0 or bool(np.all(np.linalg.norm(others - c, axis=1) > distance))
            if inside and own:
                return c
        distance *= 0.9  # не влезло — чуть ближе к улью
    return np.clip(hive, -limit, limit)


# ------------------------------------------------------------------ препятствия


def _count(per_ha: float, size: float) -> int:
    return round(per_ha * size * size / 10_000.0)


def _scatter(
    gen: np.random.Generator,
    count: int,
    size: float,
    margin: float,
    keep_out: list[tuple[np.ndarray, float]],
) -> np.ndarray:
    """`count` точек, равномерно по карте, вне запретных кругов `(центры, радиус)`."""
    lo, hi = -size / 2 + margin, size / 2 - margin
    found: list[np.ndarray] = []
    total = 0
    for _ in range(50):
        if total >= count:
            break
        cand = gen.uniform(lo, hi, (max(count, 8) * 2, 2))
        ok = np.ones(len(cand), dtype=bool)
        for centers, radius in keep_out:
            if centers.size:
                d = np.linalg.norm(cand[:, None, :] - centers[None, :, :], axis=-1)
                ok &= d.min(axis=1) >= radius
        cand = cand[ok]
        found.append(cand)
        total += len(cand)
    if not found:
        return np.zeros((0, 2))
    return np.concatenate(found)[:count]
