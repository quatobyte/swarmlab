"""Сведения для отладчика: что сейчас делает программа пчелы или улья (DECISIONS №105).

Работает в раннере, рядом с `player_host`: после тика читает стек ждущего потока
`loop()` и собирает снимок — на какой строке файла игрока программа ждёт, какую
команду, что лежит в переменных и в `self`, что пчела услышала. Только чтение: код
игрока не вызывается (ни `repr`, ни свойства), случайность и команды не трогаются,
время сбора в бюджет кода игрока не входит.

Снимок — простые структуры для msgpack:

```
{"line": 17 | None,            # строка файла игрока, на которой ждёт программа
 "fn": "имя" | None,           # функция этой строки, если это не loop()
 "wait": ["fly_to", x, y, …]   # команда, выполнения которой ждут (формат модуля)
       | ["wait", секунды] | ["tick"] | None,   # None — программа не запущена
 "pass": 3,                    # номер круга loop()
 "vars": [[имя, значение], …], # переменные (от loop() к вложенной функции)
 "self": [[имя, значение], …], # свои значения в self
 "heard": [значение, …],       # услышанные сообщения
 "error": {"text": "TypeError: …", "line": 15} | None}   # последняя ошибка
```

Значение: `None`, `bool`, число, строка или словарь с видом `k`: `point`, `flower`,
`bee`, `message`, `list`, `dict`, `obj` (незнакомый объект — только имя типа).
"""

from __future__ import annotations

import math
from types import FrameType, FunctionType, ModuleType
from typing import Any

from swarmlab.bees import api
from swarmlab.core.program import Order, Program, Wait

#: Пределы снимка: переменных, элементов списка, длины строки, вложенности.
MAX_VARS, MAX_ITEMS, MAX_TEXT, MAX_DEPTH = 24, 6, 80, 2

#: Не данные: модули, функции, классы и сами агенты (`self`, переданный в процедуру).
_SKIP = (ModuleType, FunctionType, type, api._Agent)


def _num(v: float) -> Any:
    return round(v, 3) if math.isfinite(v) else str(v)


def encode(value: Any, depth: int = 0) -> Any:
    """Значение переменной → простая структура. Код игрока не вызывается."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)[:MAX_TEXT]
    if isinstance(value, float):
        return _num(value)
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, api.Point):
        return {"k": "point", "x": _num(value.x), "y": _num(value.y)}
    if isinstance(value, api.Flower):
        return {"k": "flower", "x": _num(value.pos.x), "y": _num(value.pos.y),
                "nectar": _num(value.nectar), "spider": value.spider}
    if isinstance(value, api.OtherBee):
        return {"k": "bee", "x": _num(value.pos.x), "y": _num(value.pos.y),
                "friend": bool(value.friend)}
    if isinstance(value, api.Message):
        where = value.where
        return {"k": "message", "word": str(value.word)[:MAX_TEXT],
                "where": None if where is None else [_num(where.x), _num(where.y)]}
    kind = type(value)
    if kind in (list, tuple, set, frozenset):
        items = list(value)[:MAX_ITEMS] if depth < MAX_DEPTH else []
        return {"k": "list", "n": len(value), "items": [encode(v, depth + 1) for v in items]}
    if kind is dict:
        items = list(value.items())[:MAX_ITEMS] if depth < MAX_DEPTH else []
        return {"k": "dict", "n": len(value),
                "items": [[encode(k, depth + 1), encode(v, depth + 1)] for k, v in items]}
    return {"k": "obj", "text": kind.__name__[:MAX_TEXT]}


def _named(items: Any) -> list[list[Any]]:
    out = []
    for name, value in items:
        if name.startswith("_") or name == "self" or isinstance(value, _SKIP):
            continue
        out.append([name, encode(value)])
        if len(out) >= MAX_VARS:
            break
    return out


def _auto_home(obj: Any) -> bool:
    """Пчела сама летит домой заправляться (сенсор `me.auto_home`)."""
    view = getattr(obj, "_v", None)
    me = view.raw.get("me") if view is not None else None
    return bool(me and me.get("auto_home"))


def snapshot(program: Program | None, obj: Any, heard: list[Any], script: str,
             error: dict[str, Any] | None) -> dict[str, Any]:
    """Снимок программы агента после тика. `script` — файл игрока (`co_filename`)."""
    snap: dict[str, Any] = {"line": None, "fn": None, "wait": None, "pass": 0,
                            "vars": [], "self": [], "heard": [], "error": error}
    if obj is not None:
        snap["self"] = _named(getattr(obj, "__dict__", {}).items())
    snap["heard"] = [encode(m) for m in heard[:MAX_ITEMS]]
    if program is None or program.dead:
        return snap
    snap["pass"] = program.passes
    w = program.waiting
    if isinstance(w, Order):
        snap["wait"] = [encode(v) for v in w.move]
    elif isinstance(w, Wait):
        if w.seconds > 0:
            snap["wait"] = ["wait", _num(w.seconds)]
        elif not program.at_pass_end() and _auto_home(obj):
            snap["wait"] = ["auto_home"]  # команда ждёт конца заправки (DECISIONS №108)
        else:
            snap["wait"] = ["tick"]
    frames: list[FrameType] = [f for f in program.stack() if f.f_code.co_filename == script]
    if frames:
        inner = frames[0]
        snap["line"] = inner.f_lineno
        name = inner.f_code.co_name
        snap["fn"] = None if name == "loop" else name
        merged: dict[str, Any] = {}
        for frame in reversed(frames):  # от loop() к вложенной функции: внутренние имена важнее
            merged.update(frame.f_locals)
        snap["vars"] = _named(merged.items())
    return snap
