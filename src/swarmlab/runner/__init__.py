"""Процесс-раннер кода игрока: `python -m swarmlab.runner` (ARCHITECTURE §3.4).

Раннер общается с ядром кадрами протокола (`swarmlab.core.protocol`) по
stdin/stdout. Код игрока импортирует хост модуля (`AgentHost`) — только здесь,
в отдельном процессе.
"""
