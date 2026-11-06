"""Бакетизация значений (ADJUSTED_VALUE). Только стандартная библиотека.

Формат подписей (зафиксирован, не менять — по нему группирует отчёт):

    bounds = [0.3, 0.6]  →  "≤ 0.3"  |  "(0.3 – 0.6]"  |  "> 0.6"

- верхняя граница бакета включается: 0.6 → "(0.3 – 0.6]", 0.3 → "≤ 0.3";
- между числами стоит длинное тире «–» с пробелами (как в docs/api.md);
- большие числа сокращаются: 100000 → "100K", 1500000 → "1.5M", 1500 → "1.5K";
- границы различаются хотя бы в 10-м знаке после запятой, иначе ValueError;
- одна граница [5] даёт два бакета: "≤ 5" и "> 5".

Числа в виде строк разбираются через float(): " 0.5 " и "1e3" тоже числа.
Границы одни и те же для BEFORE и AFTER. DIFF_FLAG считается по VALUE, не по бакету.
"""

import math
from bisect import bisect_left
from typing import Callable

_DASH = "–"


def _trim(x: float) -> str:
    """Число без лишних нулей: 0.30 → '0.3', 2.0 → '2'."""
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def format_bound(x: float) -> str:
    """Подпись одной границы: 0.3 → '0.3', 100000 → '100K', 1500000 → '1.5M'."""
    a = abs(x)
    if a >= 1_000_000:
        return _trim(x / 1_000_000) + "M"
    if a >= 1_000:
        return _trim(x / 1_000) + "K"
    return _trim(x)


def bucket_label(value: float, bounds: list[float]) -> str:
    """Подпись бакета для числа. `bounds` — по возрастанию, без повторов."""
    if not bounds:
        raise ValueError("нет границ бакетов")
    i = bisect_left(bounds, value)  # сколько границ строго меньше value
    if i == 0:
        return f"≤ {format_bound(bounds[0])}"
    if i == len(bounds):
        return f"> {format_bound(bounds[-1])}"
    return f"({format_bound(bounds[i - 1])} {_DASH} {format_bound(bounds[i])}]"


def _norm_path(path: str) -> str:
    """Путь без индексов массивов: 'a[0].b[]' и 'a[].b' → 'a.b'. Так совпадают пути с `[]` и без."""
    out, depth = [], 0
    for ch in path:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _check_bounds(path: str, bounds) -> list[float]:
    if not isinstance(bounds, (list, tuple)):
        raise ValueError(f"бакеты для {path}: границы должны быть списком чисел, а не {bounds!r}")
    for b in bounds:
        if isinstance(b, bool) or not isinstance(b, (int, float)):
            raise ValueError(f"бакеты для {path}: граница {b!r} — не число ({list(bounds)})")
        try:
            finite = math.isfinite(float(b))
        except OverflowError:  # огромное целое вроде 10**400
            finite = False
        if not finite:
            raise ValueError(f"бакеты для {path}: граница {str(b)[:30]} — не конечное число")
    for a, b in zip(bounds, bounds[1:]):
        if a >= b:
            raise ValueError(
                f"бакеты для {path}: границы {list(bounds)} должны строго возрастать "
                f"(без повторов), а {a} идёт перед {b}"
            )
    labels = [format_bound(b) for b in bounds]
    if len(set(labels)) != len(labels):
        raise ValueError(
            f"бакеты для {path}: границы {list(bounds)} слишком близки — "
            f"подписи совпадают (точность до 10 знаков после запятой)"
        )
    return list(bounds)


def _to_number(value_str: str):
    """'0.42' → 0.42; всё, что не конечное число (строка, null, true, [], nan), → None."""
    if not isinstance(value_str, str) or "_" in value_str:
        return None
    try:
        x = float(value_str)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def make_adjuster(buckets_cfg: dict[str, list[float]]) -> Callable[[str, str], str]:
    """Возвращает adjust(path, value_str) -> str для flatten_response.

    Ошибка в границах (не по возрастанию, повторы, не числа) — ValueError с путём и границами.
    Пустой список границ = «бакетов для пути нет».
    """
    by_path: dict[str, list[float]] = {}
    for path, bounds in (buckets_cfg or {}).items():
        checked = _check_bounds(path, bounds)
        if checked:
            key = _norm_path(path)
            if key in by_path:
                raise ValueError(f"бакеты: путь {path} повторяет другой путь с теми же сегментами ({key}); оставьте один")
            by_path[key] = checked

    def adjust(path: str, value_str: str) -> str:
        bounds = by_path.get(_norm_path(path))
        if bounds is None:
            return value_str
        x = _to_number(value_str)
        return value_str if x is None else bucket_label(x, bounds)

    return adjust
