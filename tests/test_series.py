"""Серии матчей M7c (DECISIONS №66): детерминизм, параллельность, файлы, остановка."""

import csv
import json
import threading
import time
from pathlib import Path

import pytest

from swarmlab.cli import main
from swarmlab.core import series as sr
from swarmlab.core.replay import file_sha256, read_replay

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "configs" / "matches" / "demo.yaml"
M2 = ROOT / "configs" / "matches" / "m2_economy.yaml"
#: Бюджет раннера снят: под нагрузкой (2 матча × 3 раннера на 4 потоках) превышение 20 мс по
#: часам стены отбрасывало бы команды тика — результат зависел бы от машины, а не от seed.
NO_BUDGET = ["runner.budget_ms=100000", "runner.hard_timeout_ms=100000"]


def _series(tmp: Path, *, match: Path = DEMO, n: int = 2, seed: int = 11, jobs: int = 1,
            duration: float = 6.0) -> dict:
    spec = sr.SeriesSpec(match=match, overrides=[f"duration_s={duration}", *NO_BUDGET],
                         start_seed=seed, n=n, jobs=jobs, out=tmp)
    return sr.Series(spec, root=ROOT).run()


def _results(data: dict) -> list[tuple]:
    return [(m["seed"], m["hash"], json.dumps(m["teams"], sort_keys=True), m["winner"])
            for m in data["matches"]]


def test_same_start_seed_twice_and_jobs_1_vs_2_give_same_results(tmp_path):
    """Критерий M7c: один начальный seed дважды → те же хеши; `--jobs 1` и `--jobs 2` — то же."""
    a = _series(tmp_path / "a", jobs=1)
    b = _series(tmp_path / "b", jobs=1)
    c = _series(tmp_path / "c", jobs=2)
    print(_results(a))
    assert [m["seed"] for m in a["matches"]] == [11, 12]
    assert all(m["state"] == sr.FINISHED for m in a["matches"])
    assert _results(a) == _results(b) == _results(c)
    assert a["matches"][0]["hash"] != a["matches"][1]["hash"]  # разные seed — разные матчи
    assert c["jobs"] == 2 and a["summary"] == c["summary"]


def test_series_writes_replays_json_with_sha256_and_csv(tmp_path):
    """Критерий M7c: `s<seed>.swr`, `series.json` (sha256 кода ульев), `results.csv` с колонками."""
    out = tmp_path / "series"
    code = main(["series", str(M2), "--n", "2", "--seed", "3", "--duration", "5", "--jobs", "1",
                 "--out", str(out), *(a for s in NO_BUDGET for a in ("--set", s))])
    assert code == 0
    (folder,) = out.iterdir()
    assert folder.name.endswith("-example_basic")
    data = json.loads((folder / "series.json").read_text(encoding="utf-8"))
    assert data["state"] == sr.FINISHED and data["start_seed"] == 3 and data["n"] == 2
    for key in ("format", "created", "match", "overrides", "profile", "duration_s", "jobs",
                "hives", "matches", "summary"):
        assert key in data, key
    (hive,) = data["hives"]
    assert hive["sha256"] == file_sha256(ROOT / "examples" / "bees" / "example_basic.py")
    for m in data["matches"]:
        rp = read_replay(folder / f"s{m['seed']}.swr")
        assert rp.hash_ok and rp.hash == m["hash"] and m["replay"] == f"s{m['seed']}.swr"
        assert rp.header["seed"] == m["seed"]
    raw = (folder / "results.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM — Excel узнаёт UTF-8
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
    head = rows[0]
    for title in ("seed", "место", "мёд", "доставлено нектара", "живых пчёл", "гибели: энергия",
                  "гибели: шершень", "гибели: паук", "ошибки кода: исключения",
                  "ошибки кода: пропущено тиков", "ошибки кода: сверх бюджета"):
        assert title in head, title
    assert [r[0] for r in rows[1:]] == ["3", "4", "среднее"]
    assert data["summary"]["worst_seed"] in (3, 4) and data["summary"]["played"] == 2


def test_stop_keeps_finished_matches_and_drops_unfinished(tmp_path):
    """Критерий M7c: остановка серии оставляет дописанные матчи, недописанные реплеи удаляются."""
    spec = sr.SeriesSpec(match=M2, overrides=["duration_s=4", *NO_BUDGET], start_seed=20, n=5,
                         jobs=1, out=tmp_path)
    s = sr.Series(spec, root=ROOT)
    done = threading.Event()

    def stop_after_first(_m: dict) -> None:
        (s.dir / sr.STOP_FILE).write_text("")  # так серию останавливает сервер
        done.set()

    data = s.run(stop_after_first)
    assert done.is_set()
    assert data["state"] == sr.STOPPED
    assert [m["seed"] for m in data["matches"]] == [20]
    assert sorted(p.name for p in s.dir.glob("*.swr")) == ["s20.swr"]
    assert read_replay(s.dir / "s20.swr").hash_ok
    assert not (s.dir / sr.STOP_FILE).exists()
    saved = json.loads((s.dir / "series.json").read_text(encoding="utf-8"))
    assert saved["state"] == sr.STOPPED and len(saved["matches"]) == 1
    assert (s.dir / "results.csv").is_file()


def test_stop_interrupts_running_match(tmp_path):
    spec = sr.SeriesSpec(match=M2, overrides=["duration_s=600", *NO_BUDGET], start_seed=1, n=2,
                         jobs=1, out=tmp_path)
    s = sr.Series(spec, root=ROOT)
    threading.Timer(3.0, lambda: (s.dir / sr.STOP_FILE).write_text("")).start()
    t0 = time.monotonic()
    data = s.run()
    assert time.monotonic() - t0 < 60
    assert data["state"] == sr.STOPPED and data["matches"] == []
    assert not list(s.dir.glob("*.swr"))


def test_series_parameters_and_cores(tmp_path):
    assert sr.physical_cores() >= 1
    assert sr.default_jobs() == max(1, sr.physical_cores() - 1)
    for n in (1, 51):
        with pytest.raises(sr.SeriesError):
            sr.Series(sr.SeriesSpec(match=M2, n=n, out=tmp_path), root=ROOT)


def test_list_series_keeps_old_series(tmp_path):
    for name in ("20261020-100000-a", "20261021-100000-b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "series.json").write_text(json.dumps({"id": name}), encoding="utf-8")
    assert [d["id"] for d in sr.list_series(tmp_path)] == ["20261021-100000-b",
                                                           "20261020-100000-a"]
