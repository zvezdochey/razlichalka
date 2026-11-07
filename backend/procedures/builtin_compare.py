"""Встроенная процедура «Сравнение срезов»: две плоские таблицы -> витрина сравнения (CONTRACTS §2.2).

Контракт. `COMPARE["entrypoint"](before, after)`:
    вход  — два pandas.DataFrame, нормализованные строки BEFORE и AFTER (одна заявка — в обоих срезах),
            колонки APP_ID, PREFIX, CLASS, SUFFIX, ARRAY_KEY, KEY, PATH, VALUE, ADJUSTED_VALUE, все — строки;
    выход — pandas.DataFrame с колонками витрины сравнения:
            APP_ID, PREFIX, CLASS, SUFFIX, ARRAY_KEY, KEY, PATH,
            VALUE_BEFORE, VALUE_AFTER, ADJUSTED_BEFORE, ADJUSTED_AFTER, DIFF_FLAG, CHANGE_TYPE.
    CHANGE_TYPE — SAME, VALUE_CHANGED, ATTRIBUTE_NEW, ATTRIBUTE_LOST; DIFF_FLAG — 1, если не SAME.

Остальное делает приложение (pipeline/compare.py): читает файлы, убирает заявки без пары,
проверяет результат по контракту, сортирует и пишет comparison.csv.

Правила этой процедуры:
    ключ строки — (APP_ID, PATH, ARRAY_KEY);
    сравниваем по VALUE, а не по ADJUSTED_VALUE: значение, сменившееся внутри бакета, — всё равно VALUE_CHANGED;
    PREFIX/CLASS/SUFFIX/KEY берём из AFTER, а у ATTRIBUTE_LOST (AFTER нет) — из BEFORE;
    у стороны, где атрибута нет, ячейки пустые (это не то же самое, что JSON null).

Как поменять. Скопируйте процедуру в рабочую область («Копировать в рабочую область»), поправьте функцию
и выберите копию в форме «Новый прогон» → «Как считаем» → «Сравнение». Код приложения трогать не нужно.
Например, чтобы сравнивать по бакетам, а не по точным значениям, замените VALUE на ADJUSTED_VALUE в `changed`.
"""

import pandas as pd

KEY = ["APP_ID", "PATH", "ARRAY_KEY"]
META = ["PREFIX", "CLASS", "SUFFIX", "KEY"]


def compare(before, after):
    merged = before.merge(after, on=KEY, how="outer", suffixes=("_B", "_A"), indicator=True)
    both = merged["_merge"] == "both"
    only_before = merged["_merge"] == "left_only"
    only_after = merged["_merge"] == "right_only"

    out = pd.DataFrame({c: merged[c] for c in KEY})
    # PREFIX/CLASS/SUFFIX/KEY: из AFTER, а если строки там нет — из BEFORE
    for col in META:
        out[col] = merged[col + "_A"].where(~only_before, merged[col + "_B"])
    # Пустая ячейка у стороны, где атрибута нет
    out["VALUE_BEFORE"] = merged["VALUE_B"].where(~only_after, "")
    out["VALUE_AFTER"] = merged["VALUE_A"].where(~only_before, "")
    out["ADJUSTED_BEFORE"] = merged["ADJUSTED_VALUE_B"].where(~only_after, "")
    out["ADJUSTED_AFTER"] = merged["ADJUSTED_VALUE_A"].where(~only_before, "")

    changed = both & (merged["VALUE_B"] != merged["VALUE_A"])
    change_type = pd.Series("SAME", index=merged.index)
    change_type[changed] = "VALUE_CHANGED"
    change_type[only_after] = "ATTRIBUTE_NEW"
    change_type[only_before] = "ATTRIBUTE_LOST"
    out["CHANGE_TYPE"] = change_type
    out["DIFF_FLAG"] = (change_type != "SAME").astype(int)
    return out


COMPARE = {"label": "Сравнение по ключу (APP_ID, PATH, ARRAY_KEY)", "entrypoint": compare}
