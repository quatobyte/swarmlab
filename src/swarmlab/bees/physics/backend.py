"""`PhysicsBackend` пчёлок на MuJoCo.

Внешние силы задаются через `data.xfrc_applied` (мировая СК, центр масс тела).
Состояние тел читается из `qpos`/`qvel` векторно по заранее посчитанным индексам.
"""

from __future__ import annotations

from collections.abc import Sequence

import mujoco
import numpy as np

from swarmlab.core.physics import STATIC, ContactList


class MujocoBackend:
    """Физика на MuJoCo для пула свободных тел `body_names` (индексы бэкенда — по порядку)."""

    def __init__(
        self,
        xml: str,
        body_names: Sequence[str],
        *,
        angular_damping: float = 0.0,
    ) -> None:
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        m = self.model

        self._mj_body = np.array(
            [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, name) for name in body_names],
            dtype=np.int64,
        )
        if np.any(self._mj_body < 0):
            missing = [n for n, b in zip(body_names, self._mj_body, strict=True) if b < 0]
            raise ValueError(f"В модели нет тел: {missing}")
        joint = m.body_jntadr[self._mj_body]
        qadr = m.jnt_qposadr[joint][:, None]
        dadr = m.jnt_dofadr[joint][:, None]
        self._pos_idx = qadr + np.arange(3)
        self._quat_idx = qadr + 3 + np.arange(4)
        self._vel_idx = dadr + np.arange(6)
        self._geoms = [np.flatnonzero(m.geom_bodyid == b) for b in self._mj_body]
        self._geom_contype = m.geom_contype.copy()
        self._geom_conaffinity = m.geom_conaffinity.copy()

        # Вращение для игры не важно — демпфируем только угловые степени свободы.
        m.dof_damping[self._vel_idx[:, 3:].ravel()] = angular_damping

        # Обратное отображение: тело MuJoCo → индекс бэкенда (STATIC для остального).
        self._backend_of_mj = np.full(m.nbody, STATIC, dtype=np.int64)
        self._backend_of_mj[self._mj_body] = np.arange(len(self._mj_body))

        mujoco.mj_forward(m, self.data)

    # --------------------------------------------------------------- PhysicsBackend

    @property
    def timestep(self) -> float:
        return float(self.model.opt.timestep)

    @property
    def n_bodies(self) -> int:
        return int(self._mj_body.shape[0])

    def step(self, n_substeps: int = 1) -> None:
        mujoco.mj_step(self.model, self.data, nstep=n_substeps)

    def set_forces(
        self,
        body_ids: np.ndarray,
        forces: np.ndarray,
        torques: np.ndarray | None = None,
    ) -> None:
        mj = self._mj_body[body_ids]
        self.data.xfrc_applied[mj, :3] = forces
        if torques is not None:
            self.data.xfrc_applied[mj, 3:] = torques

    def poses(self) -> tuple[np.ndarray, np.ndarray]:
        qpos = self.data.qpos
        return qpos[self._pos_idx], qpos[self._quat_idx]

    def velocities(self) -> np.ndarray:
        return self.data.qvel[self._vel_idx]

    def contacts(self) -> ContactList:
        d = self.data
        n = d.ncon
        if n == 0:
            return ContactList.empty()
        geom = d.contact.geom[:n]
        mj_bodies = self.model.geom_bodyid[geom]
        backend = self._backend_of_mj[mj_bodies]
        force = np.zeros(n)
        buf = np.zeros(6)
        for i in range(n):  # mj_contactForce не векторизован; контактов немного
            mujoco.mj_contactForce(self.model, d, i, buf)
            force[i] = buf[0]
        return ContactList(backend[:, 0].copy(), backend[:, 1].copy(), force)

    def set_active(self, body_ids: np.ndarray, active: np.ndarray) -> None:
        """Выключенное тело не сталкивается и не получает сил (пул тел, ARCHITECTURE §3.5)."""
        m = self.model
        for body, on in zip(np.atleast_1d(body_ids), np.atleast_1d(active), strict=True):
            geoms = self._geoms[int(body)]
            m.geom_contype[geoms] = self._geom_contype[geoms] if on else 0
            m.geom_conaffinity[geoms] = self._geom_conaffinity[geoms] if on else 0
            if not on:
                self.data.xfrc_applied[self._mj_body[int(body)]] = 0.0

    # --------------------------------------------------------------- для тестов и вьюера

    def mj_body_id(self, body: int) -> int:
        """Идентификатор тела MuJoCo по индексу бэкенда."""
        return int(self._mj_body[body])
