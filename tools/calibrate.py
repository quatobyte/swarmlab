"""Калибровка параметров пчёл из целей (BEES_SPEC §2.1–2.3).

Цели — в `configs/bees/defaults.yaml` (`bee_types.*`: масса, радиус, `thrust_max`,
`cruise_speed`, `flight_time_s`). Скрипт выводит из них:

* `drag_coef` (c_d): горизонтальный запас тяги на крейсерской скорости
  `√(T_max² − (mg)²) = c_d · v_cruise²` — крейсерская скорость = максимальная
  скорость горизонтального полёта, тяга при этом равна `T_max`;
* `power_coef` (k_p): теория импульсного диска, индуктивная мощность идеального
  винта `P = T^1.5 / √(2ρA)`, с площадью диска `A = π r²` и коэффициентом
  качества винта `FM`: `k_p = 1 / (FM · √(2ρA))`;
* `power_idle` (P_idle): доля `idle_fraction` от индуктивной мощности на крейсере
  (электроника, «холостой ход»);
* `energy_max` (E_max): запас энергии на `flight_time_s` полёта на крейсерской
  скорости, где `|T| = T_max`: `E_max = t · (P_idle + k_p · T_max^1.5)`;
* `physics.rain_force_coef` (k_rain): дождь `F = k_rain · r²` даёт в среднем по
  типам долю `rain_weight_fraction` от веса пустой пчелы.

Запуск (PowerShell, из корня репозитория):

    .venv\\Scripts\\python tools\\calibrate.py           # таблица и YAML-фрагмент
    .venv\\Scripts\\python tools\\calibrate.py --write   # записать в defaults.yaml
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "configs" / "bees" / "defaults.yaml"
KINDS = ("scout", "forager", "guard")

#: Опоры калибровки (не механики игры, а допущения модели).
AIR_DENSITY = 1.225  # ρ, кг/м³
FIGURE_OF_MERIT = 0.6  # FM, качество винта (идеальный = 1)
IDLE_FRACTION = 0.05  # P_idle как доля индуктивной мощности на крейсере
RAIN_WEIGHT_FRACTION = 0.10  # дождь ≈ 10% веса
#: Знаков после запятой при записи в YAML.
DIGITS = 6


@dataclass(frozen=True)
class Calibrated:
    drag_coef: float
    power_coef: float
    power_idle: float
    energy_max: float
    # Справочно: что получается при этих параметрах.
    power_cruise: float
    power_hover: float


def calibrate_type(t: dict, gravity: float) -> Calibrated:
    """Параметры одного типа пчёл из его целей."""
    weight = t["mass"] * gravity
    t_max = t["thrust_max"]
    if t_max <= weight:
        raise ValueError(f"T_max = {t_max} Н не держит вес {weight:.3f} Н")
    c_d = math.sqrt(t_max**2 - weight**2) / t["cruise_speed"] ** 2
    area = math.pi * t["radius"] ** 2
    k_p = 1.0 / (FIGURE_OF_MERIT * math.sqrt(2 * AIR_DENSITY * area))
    p_ind_cruise = k_p * t_max**1.5
    p_idle = IDLE_FRACTION * p_ind_cruise
    p_cruise = p_idle + p_ind_cruise
    return Calibrated(
        drag_coef=round(c_d, DIGITS),
        power_coef=round(k_p, DIGITS),
        power_idle=round(p_idle, DIGITS),
        energy_max=round(t["flight_time_s"] * p_cruise, 2),
        power_cruise=p_cruise,
        power_hover=p_idle + k_p * weight**1.5,
    )


def rain_force_coef(types: dict, gravity: float) -> float:
    """k_rain: дождь — в среднем `RAIN_WEIGHT_FRACTION` веса по типам."""
    ratios = [RAIN_WEIGHT_FRACTION * types[k]["mass"] * gravity / types[k]["radius"] ** 2
              for k in KINDS]
    return round(sum(ratios) / len(ratios), DIGITS)


def calibrate(defaults: dict) -> tuple[dict[str, Calibrated], float]:
    g = defaults["physics"]["gravity"]
    types = defaults["bee_types"]
    return {k: calibrate_type(types[k], g) for k in KINDS}, rain_force_coef(types, g)


# ------------------------------------------------------------------ запись в YAML


_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][\w]*):(?P<rest>.*)$")
_VALUE_LINE = re.compile(r"^(?P<head> *\w+:\s+)(?P<value>[^#]*?)(?P<tail>\s+#.*)?$")


def _set_key(lines: list[str], path: tuple[str, ...], value: float) -> None:
    """Заменить значение ключа блочного YAML по пути, сохранив отступы и комментарий."""
    stack: list[tuple[int, str]] = []  # (отступ, ключ) — текущий путь
    for i, line in enumerate(lines):
        m = _KEY_LINE.match(line)
        if not m:
            continue
        indent = len(m.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group("key")))
        if tuple(k for _, k in stack) == path:
            v = _VALUE_LINE.match(line)
            if v is None:
                raise ValueError(f"Строка {i + 1}: у ключа {'.'.join(path)} нет значения")
            head, tail = v.group("head"), v.group("tail")
            if not tail:
                lines[i] = f"{head}{value}"
                return
            # Комментарий остаётся в той же колонке (если значение не длиннее места под него).
            column = len(head) + len(v.group("value")) + len(tail) - len(tail.lstrip())
            text = f"{head}{value}"
            lines[i] = f"{text.ljust(column - 1)} {tail.lstrip()}"
            return
    raise KeyError(f"Ключ {'.'.join(path)} не найден")


def write_defaults(path: Path, result: dict[str, Calibrated], k_rain: float) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for kind, c in result.items():
        for name in ("drag_coef", "energy_max", "power_idle", "power_coef"):
            _set_key(lines, ("bee_types", kind, name), getattr(c, name))
    _set_key(lines, ("physics", "rain_force_coef"), k_rain)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--defaults", type=Path, default=DEFAULTS)
    parser.add_argument("--write", action="store_true", help="записать результат в defaults")
    args = parser.parse_args(argv)

    defaults = yaml.safe_load(args.defaults.read_text(encoding="utf-8"))
    result, k_rain = calibrate(defaults)
    types = defaults["bee_types"]

    print(f"Опоры: rho = {AIR_DENSITY}, FM = {FIGURE_OF_MERIT}, P_idle = {IDLE_FRACTION:.0%} "
          f"P_ind, дождь = {RAIN_WEIGHT_FRACTION:.0%} веса")
    print(f"{'тип':8} {'v, м/с':>7} {'t, с':>6} {'c_d':>9} {'k_p':>8} {'P_idle':>7} "
          f"{'E_max, Дж':>10} {'P_круиз':>8} {'P_висение':>9} {'t_висения':>9}")
    for kind, c in result.items():
        t = types[kind]
        print(f"{kind:8} {t['cruise_speed']:7.1f} {t['flight_time_s']:6.0f} {c.drag_coef:9.5f} "
              f"{c.power_coef:8.4f} {c.power_idle:7.3f} {c.energy_max:10.1f} "
              f"{c.power_cruise:8.3f} {c.power_hover:9.3f} {c.energy_max / c.power_hover:8.0f}с")
    print(f"k_rain = {k_rain} Н/м^2")
    print()
    print("bee_types:")
    for kind, c in result.items():
        print(f"  {kind}: {{drag_coef: {c.drag_coef}, energy_max: {c.energy_max}, "
              f"power_idle: {c.power_idle}, power_coef: {c.power_coef}}}")
    print(f"physics: {{rain_force_coef: {k_rain}}}")

    if args.write:
        write_defaults(args.defaults, result, k_rain)
        print(f"\nЗаписано в {args.defaults}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
