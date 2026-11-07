"""Сравнение двух срезов (E5): normalized_BEFORE.csv + normalized_AFTER.csv → comparison.csv.

Само правило сравнения — в процедуре: встроенная `procedures/builtin_compare.py` или своя из рабочей области
(тогда она исполняется в отдельном процессе, pipeline/user_procedures.py). Здесь — обвязка: чтение срезов,
заявки без пары, проверка результата по контракту, сортировка и запись.
Сортировка: APP_ID «естественная» (1, 2, 10, а не 1, 10, 2), затем PATH и ARRAY_KEY как строки.
Строка `null` (JSON null) и «атрибута нет в срезе» — разные случаи: второе даёт пустые ячейки стороны.

Только заявки с парой (E15, ответ организаторов): в витрину попадают заявки, у которых есть строки
и в BEFORE, и в AFTER. Заявка, которой нет в одном из срезов (ответа нет или он не разобрался), —
не ATTRIBUTE_NEW/LOST по всем полям, а шум: её исключаем, а сколько таких — пишем в `unpaired.json`
(`only_before` / `only_after`, списки APP_ID) и в журнал этапа. Счётчики потом попадают в summary.json.
"""

import json
import os
import re
from pathlib import Path

import pandas as pd

from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile
from pipeline.procedures import load_builtin_module

BUILTIN = "builtin_compare"  # встроенная процедура: само правило сравнения — там
CHANGE_TYPES = ("SAME", "VALUE_CHANGED", "ATTRIBUTE_NEW", "ATTRIBUTE_LOST")

KEY = ["APP_ID", "PATH", "ARRAY_KEY"]
NUM = re.compile(r"\d+")
# Поля, которые берём из той стороны, где строка есть
META = ["PREFIX", "CLASS", "SUFFIX", "KEY"]
NEEDED = KEY + META + ["VALUE", "ADJUSTED_VALUE"]

# Порядок колонок — CONTRACTS §2.2
COLUMNS = [
    "APP_ID", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH",
    "VALUE_BEFORE", "VALUE_AFTER", "ADJUSTED_BEFORE", "ADJUSTED_AFTER",
    "DIFF_FLAG", "CHANGE_TYPE",
]


def _load(path: Path, name: str) -> pd.DataFrame:
    """Читает срез и проверяет колонки и уникальность ключа."""
    df = read_csv(path)
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise BadFile(f"В файле {name} нет колонок: {', '.join(missing)}")
    df = df[NEEDED]
    dup = df.duplicated(KEY, keep=False)
    if dup.any():
        first = df[dup].iloc[0]
        raise BadFile(
            f"В файле {name} повторяется ключ строки (заявка {first['APP_ID']}, "
            f"путь {first['PATH']}, ключ массива «{first['ARRAY_KEY']}»): "
            f"всего {int(dup.sum())} строк-дублей. Проверьте правила ключей массивов."
        )
    return df


def _natural(ids) -> list[str]:
    """APP_ID в «естественном» порядке: 2 раньше 10."""
    return sorted(ids, key=lambda x: NUM.sub(lambda m: m.group().zfill(20), x))


def write_unpaired(path: Path, only_before: list[str], only_after: list[str]) -> None:
    """unpaired.json: заявки без пары. Временный файл + подмена — обрыв не оставит половину JSON."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"only_before": only_before, "only_after": only_after},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_unpaired(path: Path | None) -> dict:
    """Счётчики из unpaired.json; файла нет (старый запуск) — нули."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (TypeError, FileNotFoundError, ValueError):
        data = {}
    if not isinstance(data, dict):  # файл переписали руками — считаем, что счётчиков нет
        data = {}
    return {"only_before": len(data.get("only_before") or []), "only_after": len(data.get("only_after") or [])}


def _builtin_compare(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """Встроенная процедура сравнения — `procedures/builtin_compare.py` (свой файл, исполняем в этом процессе)."""
    return load_builtin_module(BUILTIN)["COMPARE"]["entrypoint"](before, after)


def _check_result(out) -> pd.DataFrame:
    """Результат процедуры сравнения -> витрина по контракту: все колонки, словарь CHANGE_TYPE, DIFF_FLAG 0/1."""
    if not isinstance(out, pd.DataFrame):
        raise BadFile(f"Процедура сравнения вернула {type(out).__name__}, а нужен pandas.DataFrame")
    missing = [c for c in COLUMNS if c not in out.columns]
    if missing:
        raise BadFile(f"Процедура сравнения: в результате нет колонок {', '.join(missing)}")
    out = out[COLUMNS].fillna("").astype(str)
    bad = sorted(set(out["CHANGE_TYPE"]) - set(CHANGE_TYPES))
    if bad:
        raise BadFile(f"Процедура сравнения: CHANGE_TYPE «{bad[0]}» не из словаря {', '.join(CHANGE_TYPES)}")
    # DIFF_FLAG — строго по CHANGE_TYPE: иначе сводная и проверки разойдутся с типом изменения
    out["DIFF_FLAG"] = (out["CHANGE_TYPE"] != "SAME").astype(int).astype(str)
    return out


def compare_csv(before_csv: Path, after_csv: Path, out_csv: Path, log=None,
                unpaired_json: Path | None = None, compare_fn=None) -> int:
    """Строит витрину сравнения. Возвращает число записанных строк.

    `unpaired_json` — куда записать заявки без пары (см. docstring модуля); без него только журнал.
    `compare_fn(before, after)` — процедура сравнения пользователя; без неё — встроенная.
    """
    before = _load(before_csv, "BEFORE")
    after = _load(after_csv, "AFTER")

    # E15: оставляем только заявки, которые есть в обоих срезах
    ids_b, ids_a = set(before["APP_ID"]), set(after["APP_ID"])
    ids_only_before, ids_only_after = _natural(ids_b - ids_a), _natural(ids_a - ids_b)
    paired = ids_b & ids_a
    if ids_only_before:
        before = before[before["APP_ID"].isin(paired)]
    if ids_only_after:
        after = after[after["APP_ID"].isin(paired)]
    if unpaired_json is not None:
        write_unpaired(unpaired_json, ids_only_before, ids_only_after)
    if log:
        for side, ids, other in (("BEFORE", ids_only_before, "AFTER"), ("AFTER", ids_only_after, "BEFORE")):
            if ids:
                log("warn", f"Заявок только в {side} (нет в {other} или ответ не разобрался): {len(ids)} — "
                            f"в витрину не попали: {', '.join(ids[:5])}"
                            + (f" и ещё {len(ids) - 5}" if len(ids) > 5 else ""))

    out = _check_result(compare_fn(before, after) if compare_fn else _builtin_compare(before, after))

    # Естественный порядок APP_ID: числа внутри id дополняем нулями, чтобы 2 шло раньше 10
    natural = out["APP_ID"].str.replace(r"\d+", lambda m: m.group().zfill(20), regex=True)
    out = out.assign(_app=natural).sort_values(["_app", "PATH", "ARRAY_KEY"], kind="stable")[COLUMNS]

    counts = out["CHANGE_TYPE"].value_counts()
    if log:
        log(
            "info",
            "Сравнение: "
            + " / ".join(
                f"{t}={int(counts.get(t, 0))}"
                for t in ("SAME", "VALUE_CHANGED", "ATTRIBUTE_NEW", "ATTRIBUTE_LOST")
            ),
        )
    return write_csv(out_csv, COLUMNS, out.to_dict("records"))
