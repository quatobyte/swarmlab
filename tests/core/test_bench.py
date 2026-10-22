"""Бенчмарк: замер профиля, рекомендация, кэш."""

import json
from pathlib import Path

from swarmlab.core import bench
from swarmlab.core.bench import BenchReport, BenchResult

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def _result(profile, bodies, rtf):
    return BenchResult(profile, f"{profile}.yaml", bodies, 1, 0.1, 10.0, 10.0 / rtf, 2000, rtf)


def test_recommendation_is_heaviest_profile_fast_enough():
    report = BenchReport(results=[
        _result("small", 53, 4.0), _result("medium", 308, 1.3), _result("large", 920, 0.4),
    ])
    assert report.recommended == "medium"
    report.results[1] = _result("medium", 308, 1.1)  # ниже порога 1.2
    assert report.recommended == "small"
    report.results[0] = _result("small", 53, 0.9)
    assert report.recommended is None


def test_bench_small_profile_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARMLAB_HOME", str(tmp_path))
    report = bench.run_bench(CONFIGS, ["small"], seconds=1.0, warmup_s=0.5)
    (r,) = report.results
    assert r.profile == "small" and r.teams == 1 and r.steps > 0 and r.rtf > 0
    path = bench.save_cache(report)
    assert path == tmp_path / "bench.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["results"][0]["profile"] == "small"
    assert bench.load_cache().results[0].rtf == r.rtf


def test_every_profile_has_bench_match():
    profiles = {p.stem for p in (CONFIGS / "profiles").glob("*.yaml")}
    matches = {p.stem for p in bench.bench_matches(CONFIGS)}
    assert profiles == matches
