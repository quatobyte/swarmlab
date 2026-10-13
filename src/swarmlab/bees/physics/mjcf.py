"""Сборка MJCF-модели (строка XML) из мира пчёлок.

Модуль не импортирует MuJoCo: он только пишет XML. Статика (рельеф, деревья,
камни, ульи) — геометрии мирового тела; пчёлы — свободные тела-сферы. Цветы — не
тела, а сайты без столкновений: их видно во вьюере, но они ни с чем не сталкиваются.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import quoteattr

import numpy as np

from swarmlab.bees.world import World

# Маски столкновений (BEES_SPEC §2.4). Контакт есть, если
# (contype_a & conaffinity_b) or (contype_b & conaffinity_a).
STATIC_CONTYPE, STATIC_CONAFFINITY = 0b001, 0b000  # статика не сталкивается сама с собой
BEE_CONTYPE, BEE_CONAFFINITY = 0b010, 0b011  # пчёлы: с пчёлами и статикой

TERRAIN_RGBA = "0.42 0.55 0.30 1"
BARK_RGBA = "0.40 0.27 0.16 1"
LEAF_RGBA = "0.20 0.45 0.18 1"
ROCK_RGBA = "0.50 0.50 0.48 1"
FLOWER_RGBA = "0.95 0.45 0.75 1"
SPIDER_FLOWER_RGBA = "0.55 0.20 0.65 1"
DEFAULT_HIVE_COLORS = ("#f5b700", "#3a86ff", "#e63946")


@dataclass(frozen=True)
class BodySlot:
    """Слот пула тел: свободная сфера."""

    name: str
    radius: float
    mass: float
    pos: tuple[float, float, float]
    rgba: str = "1 0.8 0.1 1"


def hex_to_rgba(color: str, alpha: float = 1.0) -> str:
    """`"#rrggbb"` → `"r g b a"` (0..1)."""
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"Цвет должен быть в формате #rrggbb, получено {color!r}")
    r, g, b = (int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return f"{r:.3f} {g:.3f} {b:.3f} {alpha:g}"


def build_mjcf(
    world: World,
    slots: Sequence[BodySlot],
    *,
    timestep: float,
    gravity: float,
    hive_colors: Sequence[str] = DEFAULT_HIVE_COLORS,
) -> str:
    """Собрать XML модели MuJoCo."""
    half = world.half_size
    relief = max(world.max_relief, 1e-3)
    # Атрибут elevation читается как картинка: первая строка — это +y. Наш terrain[iy]
    # растёт по +y, поэтому строки переворачиваем.
    elevation = np.flipud(world.terrain / relief)

    parts: list[str] = [
        '<mujoco model="swarmlab_bees">',
        '  <compiler angle="radian" autolimits="true"/>',
        f'  <option timestep="{timestep:g}" gravity="0 0 {-gravity:g}" integrator="implicitfast"/>',
        f'  <statistic center="0 0 {relief:g}" extent="{half:g}"/>',
        "  <visual>",
        '    <global offwidth="1280" offheight="720"/>',
        '    <headlight ambient="0.35 0.35 0.35" diffuse="0.5 0.5 0.5"/>',
        '    <quality shadowsize="4096"/>',
        "  </visual>",
        "  <asset>",
        '    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.55 0.75 0.95"'
        ' rgb2="0.95 0.97 1" width="256" height="256"/>',
        f'    <hfield name="terrain" nrow="{elevation.shape[0]}" ncol="{elevation.shape[1]}"'
        f' size="{half:g} {half:g} {relief:g} {1.0:g}" elevation="{_floats(elevation.ravel())}"/>',
        "  </asset>",
        "  <worldbody>",
        '    <light directional="true" pos="0 0 100" dir="0.3 0.2 -1" castshadow="true"/>',
        f'    <geom name="terrain" type="hfield" hfield="terrain" rgba="{TERRAIN_RGBA}"'
        f"{_static()}/>",
    ]
    parts += _trees(world)
    parts += _rocks(world)
    parts += _hives(world, hive_colors)
    parts += _flowers(world)
    parts += [_bee(slot) for slot in slots]
    parts += ["  </worldbody>", "</mujoco>"]
    return "\n".join(parts)


def _floats(values: Iterable[float]) -> str:
    return " ".join(f"{v:.6g}" for v in values)


def _static() -> str:
    return f' contype="{STATIC_CONTYPE}" conaffinity="{STATIC_CONAFFINITY}"'


def _trees(world: World) -> list[str]:
    out = []
    for i, (base, r, h, crown) in enumerate(
        zip(
            world.tree_pos,
            world.tree_trunk_radius,
            world.tree_trunk_height,
            world.tree_crown_radius,
            strict=True,
        )
    ):
        top = base + np.array([0.0, 0.0, h])
        crown_c = top + np.array([0.0, 0.0, crown * 0.6])
        out.append(
            f'    <geom name="tree{i}_trunk" type="capsule" size="{r:.4g}"'
            f' fromto="{_floats(base)} {_floats(top)}" rgba="{BARK_RGBA}"{_static()}/>'
        )
        out.append(
            f'    <geom name="tree{i}_crown" type="sphere" size="{crown:.4g}"'
            f' pos="{_floats(crown_c)}" rgba="{LEAF_RGBA}"{_static()}/>'
        )
    return out


def _rocks(world: World) -> list[str]:
    return [
        f'    <geom name="rock{i}" type="box" size="{_floats(half)}" pos="{_floats(pos)}"'
        f' euler="0 0 {yaw:.4g}" rgba="{ROCK_RGBA}"{_static()}/>'
        for i, (pos, half, yaw) in enumerate(
            zip(world.rock_pos, world.rock_half, world.rock_yaw, strict=True)
        )
    ]


def _hives(world: World, colors: Sequence[str]) -> list[str]:
    out = []
    for i, (pos, half, entrance) in enumerate(
        zip(world.hive_pos, world.hive_half, world.hive_entrance, strict=True)
    ):
        rgba = hex_to_rgba(colors[i % len(colors)])
        out.append(
            f'    <geom name="hive{i}" type="box" size="{_floats(half)}" pos="{_floats(pos)}"'
            f' rgba="{rgba}"{_static()}/>'
        )
        out.append(
            f'    <site name="hive{i}_entrance" type="sphere" size="0.3"'
            f' pos="{_floats(entrance)}" rgba="0.1 0.1 0.1 0.6"/>'
        )
    return out


def _flowers(world: World) -> list[str]:
    return [
        f'    <site name="flower{i}" type="sphere" size="0.3" pos="{_floats(pos)}"'
        f' rgba="{SPIDER_FLOWER_RGBA if spider else FLOWER_RGBA}"/>'
        for i, (pos, spider) in enumerate(zip(world.flower_pos, world.flower_spider, strict=True))
    ]


def _bee(slot: BodySlot) -> str:
    name = quoteattr(slot.name)
    return (
        f'    <body name={name} pos="{_floats(slot.pos)}">'
        f"<freejoint name={name}/>"
        f'<geom name={name} type="sphere" size="{slot.radius:g}" mass="{slot.mass:g}"'
        f' contype="{BEE_CONTYPE}" conaffinity="{BEE_CONAFFINITY}" rgba="{slot.rgba}"/>'
        "</body>"
    )
