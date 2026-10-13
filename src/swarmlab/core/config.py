"""Загрузка и слияние конфигов матча.

Слои (каждый следующий перекрывает предыдущий, словари сливаются рекурсивно):

1. `configs/<module>/defaults.yaml` — все параметры механик модуля;
2. `configs/profiles/<profile>.yaml` — секция `<module>:` (и общая секция `timing:`);
3. файл матча — все ключи, кроме ключей ядра, считаются параметрами модуля;
4. `overrides:` из файла матча;
5. переопределения из командной строки (`--set путь.к.ключу=значение`).

Ядро валидирует только свои поля (`MatchConfig`). Параметры модуля приходят в
`MatchConfig.params` словарём, и модуль валидирует их своей схемой в `build()`.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from swarmlab.core.clock import Rates

#: Ключи файла матча, которые принадлежат ядру, а не модулю.
CORE_KEYS = frozenset({"module", "seed", "profile", "duration_s", "timing", "overrides"})

#: Профиль без файла: только defaults модуля + файл матча.
CUSTOM_PROFILE = "custom"


class ConfigError(ValueError):
    """Ошибка конфига с понятным сообщением для пользователя."""


class TimingConfig(BaseModel):
    """Частоты симуляции (ARCHITECTURE §4)."""

    model_config = ConfigDict(extra="forbid")

    physics_hz: int = Field(200, gt=0)
    decision_hz: int = Field(10, gt=0)
    frame_hz: int = Field(10, gt=0)

    @model_validator(mode="after")
    def _divisible(self) -> TimingConfig:
        self.rates()
        return self

    def rates(self) -> Rates:
        return Rates(self.physics_hz, self.decision_hz, self.frame_hz)


class MatchConfig(BaseModel):
    """Итоговый конфиг матча после слияния всех слоёв."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = "bees"
    seed: int = Field(ge=0)
    profile: str = CUSTOM_PROFILE
    duration_s: float = Field(gt=0)
    timing: TimingConfig = TimingConfig()
    #: Параметры модуля (слитые слои 1–5), валидирует сам модуль.
    params: dict[str, Any] = Field(default_factory=dict)
    #: Файл матча, из которого собран конфиг (для логов и реплеев).
    source: Path | None = None


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Рекурсивно слить словари: значения `override` побеждают, вложенные dict сливаются.

    Списки и скаляры заменяются целиком. Аргументы не изменяются.
    """
    out = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_yaml(path: Path) -> dict[str, Any]:
    """Прочитать YAML-файл как словарь (пустой файл → `{}`)."""
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Файл конфига не найден: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Ошибка YAML в {path}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path}: ожидался словарь верхнего уровня, получено {type(data).__name__}"
        )
    return data


def parse_override(text: str) -> dict[str, Any]:
    """`"a.b.c=значение"` → `{"a": {"b": {"c": значение}}}`; значение разбирается как YAML."""
    key, sep, raw = text.partition("=")
    if not sep or not key.strip():
        raise ConfigError(f"Переопределение должно иметь вид путь.к.ключу=значение: {text!r}")
    value: Any = yaml.safe_load(raw) if raw.strip() else None
    for part in reversed(key.strip().split(".")):
        value = {part: value}
    return value


def default_configs_dir(match_path: Path) -> Path:
    """По соглашению файл матча лежит в `<configs>/matches/`."""
    return match_path.resolve().parent.parent


def load_match(
    match_path: str | Path,
    *,
    configs_dir: str | Path | None = None,
    cli_overrides: Iterable[str] = (),
) -> MatchConfig:
    """Собрать `MatchConfig` из файла матча и всех слоёв (см. docstring модуля)."""
    match_path = Path(match_path)
    configs = Path(configs_dir) if configs_dir is not None else default_configs_dir(match_path)

    match = load_yaml(match_path)
    for text in cli_overrides:
        match = _apply_cli_override(match, parse_override(text))

    module = match.get("module", "bees")
    profile = match.get("profile", CUSTOM_PROFILE)

    defaults = load_yaml(configs / module / "defaults.yaml")
    profile_data: dict[str, Any] = {}
    if profile != CUSTOM_PROFILE:
        profile_data = load_yaml(configs / "profiles" / f"{profile}.yaml")

    params = deep_merge(defaults, profile_data.get(module) or {})
    params = deep_merge(params, {k: v for k, v in match.items() if k not in CORE_KEYS})
    params = deep_merge(params, match.get("overrides") or {})

    timing = deep_merge(profile_data.get("timing") or {}, match.get("timing") or {})

    core_fields = {k: match[k] for k in ("seed", "duration_s") if k in match}
    try:
        return MatchConfig(
            module=module,
            profile=profile,
            timing=TimingConfig(**timing),
            params=params,
            source=match_path,
            **core_fields,
        )
    except ValidationError as e:
        raise ConfigError(f"{match_path}: неверный конфиг матча:\n{e}") from e


def _apply_cli_override(match: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Ключи ядра правятся в корне файла матча, остальные — в `overrides` (выше всех слоёв)."""
    (key,) = override
    if key in CORE_KEYS:
        return deep_merge(match, override)
    return deep_merge(match, {"overrides": override})
