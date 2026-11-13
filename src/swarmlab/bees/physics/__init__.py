"""Физика пчёлок. Единственное место в проекте, где импортируется MuJoCo.

`mjcf` строит XML без MuJoCo; `backend` и `viewer` импортируются явно, чтобы
`import swarmlab.bees.physics.mjcf` не тянул MuJoCo.
"""
