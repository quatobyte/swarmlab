"""Встроенные боты врагов (BEES_SPEC §7, DECISIONS №36).

Боты написаны на том же API, что и код игроков (`swarmlab.bees.api`), и работают
как команда без процесса: модуль собирает для них сенсоры и вызывает `step()` в
процессе симуляции через тот же хост, что у раннера. Шершней в игре нет
(DECISIONS №82) — остались пауки.
"""

from __future__ import annotations

from swarmlab.bees.bots.spider import SpiderBot


def bot_classes() -> dict[str, type]:
    """Классы встроенных ботов по типам агентов."""
    return {"spider": SpiderBot}


__all__ = ["SpiderBot", "bot_classes"]
