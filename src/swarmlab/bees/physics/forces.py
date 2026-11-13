"""Силы и энергия пчёл (BEES_SPEC §2.2–2.3) — чистый NumPy, векторно по пчёлам.

MuJoCo здесь не нужен: функции получают массивы состояния и возвращают силы,
которые модуль одним вызовом передаёт бэкенду.
"""

from __future__ import annotations

import numpy as np


def drag(vel: np.ndarray, wind: np.ndarray, drag_coef: np.ndarray) -> np.ndarray:
    """Квадратичное сопротивление относительно воздуха `−c_d·|v − w|·(v − w)`, `(N,3)`."""
    air = vel - wind
    speed = np.sqrt(np.einsum("ij,ij->i", air, air))
    return -(drag_coef * speed)[:, None] * air


def rain_force(radius: np.ndarray, coef: float) -> np.ndarray:
    """Сила дождя вниз `k_rain · r²`, `(N,3)`."""
    out = np.zeros((radius.shape[0], 3))
    out[:, 2] = -coef * radius**2
    return out


def boundary_force(
    pos: np.ndarray,
    ground: np.ndarray,
    mass: np.ndarray,
    *,
    half_size: float,
    ceiling_agl: float,
    stiffness: float,
) -> np.ndarray:
    """Мягкие стенки и потолок: пружина `−k·m·выход` за край карты и выше потолка, `(N,3)`."""
    out = np.zeros_like(pos)
    out[:, :2] = -np.sign(pos[:, :2]) * np.maximum(np.abs(pos[:, :2]) - half_size, 0.0)
    out[:, 2] = -np.maximum(pos[:, 2] - (ground + ceiling_agl), 0.0)
    out *= (stiffness * mass)[:, None]
    return out


def power(thrust: np.ndarray, power_idle: np.ndarray, power_coef: np.ndarray) -> np.ndarray:
    """Мощность `P_idle + k_p·|T|^1.5`, Вт (модель идеального винта), `(N,)`."""
    t = np.sqrt(np.einsum("ij,ij->i", thrust, thrust))
    return power_idle + power_coef * t * np.sqrt(t)


def cruise_speed(
    vertical_load: np.ndarray, thrust_max: np.ndarray, drag_coef: np.ndarray
) -> np.ndarray:
    """Крейсерская скорость: `√(T_max² − L²) = c_d·v²`, где `L` — вес (+ дождь), `(N,)`."""
    budget = np.sqrt(np.maximum(thrust_max**2 - vertical_load**2, 0.0))
    return np.sqrt(budget / drag_coef)
