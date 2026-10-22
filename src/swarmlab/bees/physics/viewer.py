"""Отладочный MuJoCo-вьюер (`swarmlab run ... --mj-viewer`, `swarmlab replay ... --mj-viewer`).

Управление камерой (кроме обычной мыши MuJoCo):

* **стрелки** — плавно ехать по карте: ↑/↓ — вперёд/назад по взгляду камеры,
  ←/→ — влево/вправо; клавишу можно держать;
* **Shift** — ехать в 3 раза быстрее;
* **PageUp / PageDown** — плавно приблизиться / отдалиться.

Камера управляется скоростью, а не шагами: зажатая клавиша задаёт желаемую
скорость, текущая подтягивается к ней экспоненциально (разгон и торможение
≈ 0.12 с), поэтому движение без рывков и не зависит от частоты кадров. Скорость
пропорциональна расстоянию до точки взгляда: издалека карта проезжается быстро,
вблизи — точно.

Какие клавиши зажаты, на Windows спрашиваем у ОС (`GetAsyncKeyState`) — и только
пока окно вьюера активно. MuJoCo сообщает лишь о нажатиях (и об автоповторе
клавиатуры с задержкой ~0.5 с), этого мало для плавного удержания. На других
системах — запасной путь по этим событиям: клавиша считается зажатой ещё
`_HOLD_S` после последнего нажатия или повтора.
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

import mujoco
import mujoco.viewer

from swarmlab.bees.physics.backend import MujocoBackend

#: Логические клавиши камеры.
UP, DOWN, LEFT, RIGHT, ZOOM_IN, ZOOM_OUT, FAST = (
    "up", "down", "left", "right", "zoom_in", "zoom_out", "fast",
)
#: Коды клавиш GLFW (так их передаёт `key_callback` MuJoCo).
_GLFW = {265: UP, 264: DOWN, 263: LEFT, 262: RIGHT, 266: ZOOM_IN, 267: ZOOM_OUT}
#: Виртуальные коды Windows.
_VK = {0x26: UP, 0x28: DOWN, 0x25: LEFT, 0x27: RIGHT, 0x21: ZOOM_IN, 0x22: ZOOM_OUT,
       0x10: FAST}
#: Запасной путь: клавиша «зажата» столько секунд после нажатия или автоповтора.
_HOLD_S = 0.6


class CameraController:
    """Плавное движение камеры MuJoCo по зажатым клавишам (скорость, а не шаги)."""

    #: Скорость езды — доля расстояния до точки взгляда в секунду
    #: (обзор карты с 240 м — 120 м/с, камера за пчелой с 25 м — 12.5 м/с).
    pan_rate = 0.5
    #: Shift: во столько раз быстрее.
    fast_factor = 3.0
    #: Скорость приближения: расстояние меняется в e раз за столько секунд.
    zoom_time_s = 1.0
    #: Постоянная времени разгона и торможения, с.
    smooth_s = 0.12
    #: Минимальная скорость езды, м/с, и пределы расстояния, м.
    min_speed, min_distance, max_distance = 1.0, 2.0, 2000.0

    def __init__(self) -> None:
        self.velocity = [0.0, 0.0]  # м/с по x, y
        self.zoom_velocity = 0.0  # d ln(distance) / dt

    @property
    def moving(self) -> bool:
        """Камера ещё катится (медленнее 5 см/с — уже незаметно, останавливаем)."""
        return math.hypot(*self.velocity) > 0.05 or abs(self.zoom_velocity) > 1e-3

    def update(self, cam: Any, held: set[str], dt: float) -> bool:
        """Продвинуть камеру на `dt` секунд; вернуть True, если камера сдвинулась."""
        if dt <= 0:
            return False
        dt = min(dt, 1.0 / 30.0)  # после паузы окна (перетаскивание…) не прыгаем
        forward = (UP in held) - (DOWN in held)
        right = (RIGHT in held) - (LEFT in held)
        zoom = (ZOOM_OUT in held) - (ZOOM_IN in held)
        if not (forward or right or zoom or self.moving):
            return False
        if cam.type == mujoco.mjtCamera.mjCAMERA_TRACKING and (forward or right):
            cam.type = mujoco.mjtCamera.mjCAMERA_FREE  # lookat уже стоит на пчеле

        distance = float(cam.distance)
        speed = max(self.pan_rate * distance, self.min_speed)
        if FAST in held:
            speed *= self.fast_factor
        az = math.radians(float(cam.azimuth))
        fx, fy = math.cos(az), math.sin(az)  # вперёд по взгляду камеры
        rx, ry = math.sin(az), -math.cos(az)  # вправо
        norm = math.hypot(forward, right) or 1.0
        target = (
            speed * (forward * fx + right * rx) / norm,
            speed * (forward * fy + right * ry) / norm,
        )
        target_zoom = zoom / self.zoom_time_s * (self.fast_factor if FAST in held else 1.0)

        # Экспоненциальное сглаживание: одинаково при любой частоте кадров.
        k = 1.0 - math.exp(-dt / self.smooth_s)
        self.velocity[0] += (target[0] - self.velocity[0]) * k
        self.velocity[1] += (target[1] - self.velocity[1]) * k
        self.zoom_velocity += (target_zoom - self.zoom_velocity) * k
        if not (forward or right or zoom) and not self.moving:
            self.velocity = [0.0, 0.0]
            self.zoom_velocity = 0.0
            return False

        cam.lookat[0] += self.velocity[0] * dt
        cam.lookat[1] += self.velocity[1] * dt
        cam.distance = min(max(distance * math.exp(self.zoom_velocity * dt), self.min_distance),
                           self.max_distance)
        return True


class _HeldKeys:
    """Какие клавиши камеры зажаты сейчас."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_seen: dict[str, float] = {}
        self._poll: Callable[[], set[str] | None] | None = _windows_poller()

    def on_key(self, glfw_key: int) -> None:
        """Событие MuJoCo (нажатие или автоповтор) — для запасного пути."""
        name = _GLFW.get(glfw_key)
        if name is not None:
            with self._lock:
                self._last_seen[name] = time.perf_counter()

    def held(self) -> set[str]:
        if self._poll is not None:
            keys = self._poll()
            if keys is not None:
                return keys
        now = time.perf_counter()
        with self._lock:
            return {k for k, t in self._last_seen.items() if now - t <= _HOLD_S}


def _windows_poller() -> Callable[[], set[str] | None] | None:
    """Опрос клавиатуры Windows, пока активно окно нашего процесса (окно вьюера)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                    ctypes.POINTER(wintypes.DWORD)]
    except (OSError, AttributeError):
        return None
    pid = os.getpid()

    def poll() -> set[str] | None:
        hwnd = user32.GetForegroundWindow()
        owner = wintypes.DWORD(0)
        if hwnd:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return set()  # активно другое окно (терминал…) — стрелки не наши
        return {name for vk, name in _VK.items() if user32.GetAsyncKeyState(vk) & 0x8000}

    return poll


class MujocoDebugViewer:
    """Пассивное окно MuJoCo: симуляцию шагает внешний цикл, окно только рисует.

    Если задано `track_body`, камера следует за этим телом (двойной клик и Esc во
    вьюере переключают камеру как обычно). Клавиши камеры — см. docstring модуля;
    камера обновляется в `sync()`, который внешний цикл вызывает каждый кадр.
    """

    def __init__(self, backend: MujocoBackend, track_body: int | None = None) -> None:
        self._keys = _HeldKeys()
        self._camera = CameraController()
        self._last_sync = time.perf_counter()
        self._handle = mujoco.viewer.launch_passive(
            backend.model,
            backend.data,
            key_callback=self._keys.on_key,
            show_left_ui=False,
            show_right_ui=False,
        )
        with self._handle.lock():
            cam = self._handle.cam
            if track_body is None:
                # Обзор всей карты сверху-сбоку (иначе камера стоит в 2 м от центра карты).
                mujoco.mjv_defaultFreeCamera(backend.model, cam)
                cam.distance = 1.6 * float(backend.model.stat.extent)
                cam.elevation = -40.0
                cam.azimuth = 90.0
            else:
                cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
                cam.trackbodyid = backend.mj_body_id(track_body)
                cam.distance = 25.0
                cam.elevation = -25.0
                cam.azimuth = 135.0

    def is_running(self) -> bool:
        return self._handle.is_running()

    def sync(self) -> None:
        now = time.perf_counter()
        dt, self._last_sync = now - self._last_sync, now
        held = self._keys.held()
        if held or self._camera.moving:
            with self._handle.lock():
                self._camera.update(self._handle.cam, held, dt)
        self._handle.sync()

    def close(self) -> None:
        self._handle.close()
