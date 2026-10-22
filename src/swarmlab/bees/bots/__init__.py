"""Встроенные боты врагов (BEES_SPEC §7, DECISIONS №36).

Боты написаны на том же API, что и код игроков (`swarmlab.bees.api`), и работают
как команда без процесса: модуль собирает для них сенсоры и вызывает `step()` в
процессе симуляции через тот же хост, что у раннера. Числа правил приходят
атрибутами класса из конфига матча (`bot_classes`).
"""

from __future__ import annotations

from swarmlab.bees.bots.hornet import HornetBot
from swarmlab.bees.bots.spider import SpiderBot
from swarmlab.bees.params import EnemiesParams


def bot_classes(params: EnemiesParams) -> dict[str, type]:
    """Классы ботов, настроенные под матч (свои подклассы — без общих глобальных настроек)."""
    h = params.hornets
    hornet = type(
        "HornetBot",
        (HornetBot,),
        {"max_allies": h.target_max_allies, "ally_radius": h.target_ally_radius},
    )
    return {"hornet": hornet, "spider": SpiderBot}


__all__ = ["HornetBot", "SpiderBot", "bot_classes"]
