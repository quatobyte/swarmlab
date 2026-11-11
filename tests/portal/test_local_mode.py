"""Локальный режим без `--public` — как до M9a (DECISIONS №95): ни входа, ни CSRF, ни папок
пользователей. Полная проверка на матчах — прежние тесты `tests/server/` ветки модуля."""

from __future__ import annotations

from fastapi.routing import APIRoute


def test_local_mode_has_no_accounts_and_works_without_cookie_or_csrf(make_portal):
    p = make_portal(public=False)
    anon = p.client()
    assert p.app.state.portal is None
    assert anon.json("GET", "/api/me")[0] == 404  # клиент по 404 узнаёт локальный режим
    paths = {r.path for r in p.app.routes if isinstance(r, APIRoute)}
    assert not {"/api/me", "/api/auth/register", "/api/replays/{rid}/pin"} & paths

    names = {s["name"]: s["readonly"] for s in anon.json("GET", "/api/scripts")[1]}
    assert names == {"example_a.py": True, "template.py": True, "my_local.py": False}
    code, saved = anon.json("PUT", "/api/scripts/my_local.py", {"text": "# правка\n"})
    assert code == 200 and saved["path"] == "examples/my_local.py"
    assert (p.cfg.scripts / "my_local.py").read_text(encoding="utf-8") == "# правка\n"
    assert anon.json("GET", "/api/replays")[1] == []
    assert anon.json("GET", "/api/series")[0] == 200
    assert anon.json("GET", "/api/matches")[1] == []
    assert not (p.cfg.root / "data").exists()  # базы нет
