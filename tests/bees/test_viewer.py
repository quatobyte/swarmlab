"""Камера отладочного вьюера: плавная езда по зажатым клавишам."""

import math
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest

from swarmlab.bees.physics.viewer import (
    DOWN,
    FAST,
    LEFT,
    RIGHT,
    UP,
    ZOOM_IN,
    ZOOM_OUT,
    CameraController,
)


def _cam(azimuth=0.0, distance=40.0, kind=mujoco.mjtCamera.mjCAMERA_FREE):
    return SimpleNamespace(type=kind, azimuth=azimuth, distance=distance,
                           lookat=np.array([10.0, 20.0, 3.0]))


def _drive(cam, held, seconds, fps=60.0, ctrl=None):
    ctrl = ctrl or CameraController()
    path = []
    for _ in range(round(seconds * fps)):
        ctrl.update(cam, held, 1.0 / fps)
        path.append(cam.lookat[:2].copy())
    return ctrl, np.array(path)


def test_held_key_moves_continuously_with_smooth_start():
    cam = _cam(azimuth=0.0)
    ctrl, path = _drive(cam, {UP}, 2.0)
    steps = np.diff(path[:, 0], prepend=10.0)
    assert np.all(steps > 0)  # едет каждый кадр, пока клавиша зажата
    assert np.all(np.diff(steps[:20]) >= -1e-12)  # плавный разгон, без рывка
    full = CameraController.pan_rate * 40.0  # 32 м/с
    assert ctrl.velocity[0] == pytest.approx(full, rel=1e-3)
    assert path[-1, 0] - 10.0 == pytest.approx(full * 2.0, rel=0.1)
    assert np.allclose(path[:, 1], 20.0)  # строго вперёд по взгляду
    assert cam.lookat[2] == 3.0


def test_release_brakes_smoothly_and_stops():
    cam = _cam()
    ctrl, _ = _drive(cam, {UP}, 1.0)
    x0 = cam.lookat[0]
    _, path = _drive(cam, set(), 1.0, ctrl=ctrl)
    steps = np.diff(path[:, 0], prepend=x0)
    assert np.all(steps >= 0) and np.all(np.diff(steps) <= 1e-12)  # только замедляется
    assert steps[-1] == 0.0 and not ctrl.moving
    assert path[-1, 0] - x0 < 0.2 * CameraController.pan_rate * 40.0  # тормозной путь короткий


def test_motion_does_not_depend_on_frame_rate():
    a, b = _cam(), _cam()
    _drive(a, {UP, RIGHT}, 1.5, fps=30)
    _drive(b, {UP, RIGHT}, 1.5, fps=144)
    assert np.allclose(a.lookat, b.lookat, atol=0.5)


@pytest.mark.parametrize(
    ("azimuth", "held", "direction"),
    [
        (0.0, {UP}, (1, 0)),
        (0.0, {DOWN}, (-1, 0)),
        (0.0, {RIGHT}, (0, -1)),  # справа при взгляде вдоль +x — это −y
        (0.0, {LEFT}, (0, 1)),
        (90.0, {UP}, (0, 1)),
        (90.0, {RIGHT}, (1, 0)),
        (0.0, {UP, RIGHT}, (math.sqrt(0.5), -math.sqrt(0.5))),  # диагональ не быстрее
    ],
)
def test_direction_relative_to_view(azimuth, held, direction):
    cam = _cam(azimuth=azimuth)
    _drive(cam, held, 1.0)
    d = cam.lookat[:2] - [10.0, 20.0]
    assert d / np.linalg.norm(d) == pytest.approx(direction, abs=1e-6)


def test_shift_is_faster_and_speed_scales_with_distance():
    slow, fast, near = _cam(), _cam(), _cam(distance=4.0)
    _drive(slow, {UP}, 1.0)
    _drive(fast, {UP, FAST}, 1.0)
    _drive(near, {UP}, 1.0)
    d_slow, d_fast, d_near = (c.lookat[0] - 10.0 for c in (slow, fast, near))
    assert d_fast == pytest.approx(CameraController.fast_factor * d_slow, rel=1e-6)
    assert d_near < d_slow / 5


def test_page_keys_zoom_smoothly_within_limits():
    cam = _cam(distance=100.0)
    _drive(cam, {ZOOM_IN}, 1.0)
    assert 30.0 < cam.distance < 60.0
    _drive(cam, {ZOOM_IN}, 20.0)
    assert cam.distance == CameraController.min_distance
    _drive(cam, {ZOOM_OUT}, 2.0)
    assert cam.distance > CameraController.min_distance * 3


def test_tracking_camera_switches_to_free_only_when_moving():
    cam = _cam(kind=mujoco.mjtCamera.mjCAMERA_TRACKING)
    CameraController().update(cam, set(), 1 / 60)
    assert cam.type == mujoco.mjtCamera.mjCAMERA_TRACKING
    CameraController().update(cam, {LEFT}, 1 / 60)
    assert cam.type == mujoco.mjtCamera.mjCAMERA_FREE
