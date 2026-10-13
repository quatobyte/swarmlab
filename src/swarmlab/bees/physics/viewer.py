"""Отладочный MuJoCo-вьюер (`swarmlab run ... --mj-viewer`)."""

from __future__ import annotations

import mujoco
import mujoco.viewer

from swarmlab.bees.physics.backend import MujocoBackend


class MujocoDebugViewer:
    """Пассивное окно MuJoCo: симуляцию шагает внешний цикл, окно только рисует.

    Если задано `track_body`, камера следует за этим телом (двойной клик и Esc во
    вьюере переключают камеру как обычно).
    """

    def __init__(self, backend: MujocoBackend, track_body: int | None = None) -> None:
        self._handle = mujoco.viewer.launch_passive(
            backend.model, backend.data, show_left_ui=False, show_right_ui=False
        )
        if track_body is not None:
            with self._handle.lock():
                cam = self._handle.cam
                cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
                cam.trackbodyid = backend.mj_body_id(track_body)
                cam.distance = 25.0
                cam.elevation = -25.0
                cam.azimuth = 135.0

    def is_running(self) -> bool:
        return self._handle.is_running()

    def sync(self) -> None:
        self._handle.sync()

    def close(self) -> None:
        self._handle.close()
