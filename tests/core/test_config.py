from pathlib import Path

import pytest
import yaml

from swarmlab.core.config import ConfigError, deep_merge, load_match, parse_override


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    root = tmp_path / "configs"
    _write(
        root / "toy" / "defaults.yaml",
        {"a": 1, "b": {"x": 1, "y": 1, "z": 1, "w": 1}, "lst": [1, 2]},
    )
    _write(
        root / "profiles" / "p.yaml",
        {"timing": {"decision_hz": 5}, "toy": {"b": {"y": 2}}, "other": {"b": 9}},
    )
    return root


def test_layers_merge_in_order(configs: Path):
    match = _write(
        configs / "matches" / "m.yaml",
        {
            "module": "toy",
            "seed": 1,
            "profile": "p",
            "duration_s": 10,
            "b": {"z": 3},
            "lst": [9],
            "overrides": {"b": {"w": 4}},
        },
    )
    cfg = load_match(match, cli_overrides=["b.w=5", "seed=11", "timing.frame_hz=20"])
    assert cfg.params == {"a": 1, "b": {"x": 1, "y": 2, "z": 3, "w": 5}, "lst": [9]}
    assert cfg.seed == 11
    assert cfg.timing.decision_hz == 5  # из профиля
    assert cfg.timing.frame_hz == 20  # из командной строки
    assert cfg.timing.physics_hz == 200  # по умолчанию


def test_custom_profile_needs_no_file(configs: Path):
    match = _write(configs / "matches" / "m.yaml", {"module": "toy", "seed": 1, "duration_s": 1})
    assert load_match(match).params["b"]["y"] == 1


def test_validation_errors(configs: Path):
    bad_timing = _write(
        configs / "matches" / "t.yaml",
        {"module": "toy", "seed": 1, "duration_s": 1, "timing": {"decision_hz": 7}},
    )
    with pytest.raises(ConfigError):
        load_match(bad_timing)
    no_seed = _write(configs / "matches" / "s.yaml", {"module": "toy", "duration_s": 1})
    with pytest.raises(ConfigError):
        load_match(no_seed)
    with pytest.raises(ConfigError):
        load_match(configs / "matches" / "missing.yaml")


def test_parse_override_types():
    assert parse_override("a.b=3") == {"a": {"b": 3}}
    assert parse_override("x=true") == {"x": True}
    assert parse_override("x=[1, 2]") == {"x": [1, 2]}
    assert parse_override("x=hello") == {"x": "hello"}
    with pytest.raises(ConfigError):
        parse_override("novalue")


def test_deep_merge_does_not_mutate():
    base = {"a": {"b": 1}}
    out = deep_merge(base, {"a": {"c": 2}})
    assert out == {"a": {"b": 1, "c": 2}}
    assert base == {"a": {"b": 1}}


def test_real_m0_config_loads(m0_match: Path):
    cfg = load_match(m0_match)
    assert cfg.module == "bees"
    assert cfg.params["world"]["map_size"] == 150.0  # из профиля small
    assert cfg.params["world"]["terrain"]["grid"] == 128  # из defaults
    assert len(cfg.params["demo"]["bees"]) == 1  # из файла матча
