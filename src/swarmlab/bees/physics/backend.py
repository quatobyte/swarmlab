"""`PhysicsBackend` пчёлок на MuJoCo.

Внешние силы задаются через `data.xfrc_applied` (мировая СК, центр масс тела).
Состояние тел читается из `qpos`/`qvel` векторно по заранее посчитанным индексам.

Пул тел (ARCHITECTURE §3.5): модель компилируется с телом на каждый слот пула.
Свободный слот «припаркован» под картой: столкновения выключены масками
`contype/conaffinity`, скорость обнулена, вес уравновешен внешней силой — тело
висит на месте. Рождение пчелы = `activate` (форма, масса, позиция, маски).
У каждой пчелы ровно одна геометрия — сфера.
"""

from __future__ import annotations

from collections.abc import Sequence

import mujoco
import numpy as np

from swarmlab.core.physics import STATIC, ContactList
from swarmlab.core.spatial import expand


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
        self._lin_idx = self._vel_idx[:, :3]

        geom_count = np.bincount(m.geom_bodyid, minlength=m.nbody)[self._mj_body]
        if np.any(geom_count != 1):
            raise ValueError("У каждого тела пула должна быть ровно одна геометрия")
        geom_of_body = np.full(m.nbody, -1, dtype=np.int64)
        geom_of_body[m.geom_bodyid[::-1]] = np.arange(m.ngeom)[::-1]
        self._geom = geom_of_body[self._mj_body]
        self._contype = m.geom_contype[self._geom].copy()
        self._conaffinity = m.geom_conaffinity[self._geom].copy()
        self._gravity = -float(m.opt.gravity[2])

        # Вращение для игры не важно — демпфируем только угловые степени свободы.
        m.dof_damping[self._vel_idx[:, 3:].ravel()] = angular_damping

        # Обратное отображение: тело MuJoCo → индекс бэкенда (STATIC для остального).
        self._backend_of_mj = np.full(m.nbody, STATIC, dtype=np.int64)
        self._backend_of_mj[self._mj_body] = np.arange(len(self._mj_body))
        self._parked = np.zeros(len(self._mj_body), dtype=bool)

        mujoco.mj_forward(m, self.data)

    # --------------------------------------------------------------- PhysicsBackend

    @property
    def engine_version(self) -> str:
        """Версия движка (для заголовка реплея)."""
        return f"mujoco {mujoco.__version__}"

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
        """Контакты шага с нормальными силами — векторно, без `mj_contactForce` по одному."""
        a, b = self.contact_pairs()
        n = a.shape[0]
        if n == 0:
            return ContactList.empty()
        con = self.data.contact
        adr = con.efc_address[:n].astype(np.int64)
        dim = con.dim[:n].astype(np.int64)
        active = adr >= 0
        if self.model.opt.cone == mujoco.mjtCone.mjCONE_PYRAMIDAL:
            # Пирамидальный конус: нормальная сила = сумма сил по рёбрам пирамиды.
            rows = np.where(dim > 1, 2 * (dim - 1), 1) * active
        else:
            # Эллиптический конус: первая строка контакта — нормаль.
            rows = active.astype(np.int64)
        owner, k = expand(rows)
        force = np.bincount(owner, weights=self.data.efc_force[adr[owner] + k], minlength=n)
        return ContactList(a, b, force)

    def set_active(self, body_ids: np.ndarray, active: np.ndarray) -> None:
        """Выключенное тело не сталкивается и не получает сил (пул тел, ARCHITECTURE §3.5)."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        on = np.broadcast_to(np.atleast_1d(np.asarray(active, dtype=bool)), ids.shape)
        g = self._geom[ids]
        self.model.geom_contype[g] = np.where(on, self._contype[ids], 0)
        self.model.geom_conaffinity[g] = np.where(on, self._conaffinity[ids], 0)
        self.data.xfrc_applied[self._mj_body[ids[~on]]] = 0.0

    # --------------------------------------------------------------- пул тел

    def contact_pairs(self) -> tuple[np.ndarray, np.ndarray]:
        """Пары тел контактов шага (индексы бэкенда, `STATIC` для статики) — без сил."""
        n = self.data.ncon
        if n == 0:
            z = np.zeros(0, dtype=np.int64)
            return z, z.copy()
        geom = self.data.contact.geom[:n]
        backend = self._backend_of_mj[self.model.geom_bodyid[geom]]
        return backend[:, 0].copy(), backend[:, 1].copy()

    def body_state(self, body_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Позиции `(K,3)` и линейные скорости `(K,3)` тел `body_ids`."""
        return self.data.qpos[self._pos_idx[body_ids]], self.data.qvel[self._lin_idx[body_ids]]

    def teleport(
        self, body_ids: np.ndarray, pos: np.ndarray, vel: np.ndarray | None = None
    ) -> None:
        """Переставить тела: позиция, ориентация по умолчанию, скорость (0 по умолчанию)."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        self.data.qpos[self._pos_idx[ids]] = pos
        self.data.qpos[self._quat_idx[ids]] = (1.0, 0.0, 0.0, 0.0)
        self.data.qvel[self._vel_idx[ids]] = 0.0
        if vel is not None:
            self.data.qvel[self._lin_idx[ids]] = vel

    def set_mass(self, body_ids: np.ndarray, mass: np.ndarray, radius: np.ndarray) -> None:
        """Масса и инерция сферы; константы для решателя контактов — для свободного тела.

        Груз сборщика меняет `body_mass` его тела (DECISIONS №25): MuJoCo читает
        массу каждый шаг, поэтому и вес, и инерция учитываются без пересборки модели.
        """
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        mass = np.broadcast_to(np.asarray(mass, dtype=np.float64), ids.shape)
        radius = np.broadcast_to(np.asarray(radius, dtype=np.float64), ids.shape)
        m = self.model
        mj = self._mj_body[ids]
        inertia = 0.4 * mass * radius**2
        m.body_mass[mj] = mass
        m.body_subtreemass[mj] = mass
        m.body_inertia[mj] = inertia[:, None]
        # То, что считает mj_setConst для свободного тела-сферы (без пересчёта всей модели).
        # dof_M0 обязателен: у «простых» тел MuJoCo берёт диагональ матрицы масс из него.
        m.dof_M0[self._lin_idx[ids]] = mass[:, None]
        m.dof_M0[self._vel_idx[ids, 3:]] = inertia[:, None]
        m.body_invweight0[mj, 0] = 1.0 / mass
        m.body_invweight0[mj, 1] = 1.0 / inertia
        m.dof_invweight0[self._lin_idx[ids]] = (1.0 / mass)[:, None]
        m.dof_invweight0[self._vel_idx[ids, 3:]] = (1.0 / inertia)[:, None]
        # Припаркованное тело должно и дальше висеть.
        parked = self._parked[ids]
        if np.any(parked):
            self.data.xfrc_applied[mj[parked], :3] = 0.0
            self.data.xfrc_applied[mj[parked], 2] = mass[parked] * self._gravity

    def set_radius(self, body_ids: np.ndarray, radius: np.ndarray) -> None:
        """Радиус сферы-геометрии (тип пчелы меняется при рождении в слоте)."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        r = np.broadcast_to(np.asarray(radius, dtype=np.float64), ids.shape)
        g = self._geom[ids]
        m = self.model
        m.geom_size[g, 0] = r
        m.geom_rbound[g] = r
        m.geom_aabb[g, 3:] = r[:, None]

    def park(self, body_ids: np.ndarray, pos: np.ndarray) -> None:
        """Припарковать слоты: без столкновений, неподвижно в `pos` (вес уравновешен)."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        self.set_active(ids, np.zeros(ids.shape, dtype=bool))
        self.teleport(ids, pos)
        self._parked[ids] = True
        mj = self._mj_body[ids]
        self.data.xfrc_applied[mj] = 0.0
        self.data.xfrc_applied[mj, 2] = self.model.body_mass[mj] * self._gravity

    def activate(
        self,
        body_ids: np.ndarray,
        pos: np.ndarray,
        radius: np.ndarray,
        mass: np.ndarray,
    ) -> None:
        """Вывести слоты из парковки: форма, масса, позиция, столкновения включены."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        self._parked[ids] = False
        self.data.xfrc_applied[self._mj_body[ids]] = 0.0
        self.set_radius(ids, radius)
        self.set_mass(ids, mass, radius)
        self.teleport(ids, pos)
        self.set_active(ids, np.ones(ids.shape, dtype=bool))

    def is_parked(self, body_ids: np.ndarray) -> np.ndarray:
        return self._parked[body_ids]

    # --------------------------------------------------------------- показ реплея

    def place(self, body_ids: np.ndarray, pos: np.ndarray, radius: np.ndarray) -> None:
        """Только поза и размер (воспроизведение реплея): без масс, сил и шага физики."""
        ids = np.atleast_1d(np.asarray(body_ids, dtype=np.int64))
        self.set_radius(ids, radius)
        self.teleport(ids, pos)

    def forward(self) -> None:
        """Пересчитать положения геометрий по `qpos` (для отрисовки без шага физики)."""
        mujoco.mj_kinematics(self.model, self.data)

    # --------------------------------------------------------------- для тестов и вьюера

    def mj_body_id(self, body: int) -> int:
        """Идентификатор тела MuJoCo по индексу бэкенда."""
        return int(self._mj_body[body])

    def geom_id(self, body: int) -> int:
        """Идентификатор геометрии MuJoCo тела пула."""
        return int(self._geom[body])
