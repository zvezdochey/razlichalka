"""Пример своей процедуры сравнения, размещённой файлом на сервере: сравнение по бакетам, а не по точным значениям.

Отличие от встроенной (`builtin_compare.py`) — одна строка: `changed` считается по ADJUSTED_VALUE.
Значение, которое сдвинулось внутри своего бакета (границы — поле `buckets` конфигурации), не считается
изменением: так видно только переходы между диапазонами, а мелкий шум уходит.

Как подключить: «Процедуры» → новая процедура вида «Сравнение срезов», источник «Файл на сервере»,
путь `procedures/example_compare_by_bucket.py` — и выбрать её в форме «Новый прогон».
Контракт тот же, что у встроенной: COMPARE["entrypoint"](before, after) -> DataFrame витрины.
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

    changed = both & (merged["ADJUSTED_VALUE_B"] != merged["ADJUSTED_VALUE_A"])
    change_type = pd.Series("SAME", index=merged.index)
    change_type[changed] = "VALUE_CHANGED"
    change_type[only_after] = "ATTRIBUTE_NEW"
    change_type[only_before] = "ATTRIBUTE_LOST"
    out["CHANGE_TYPE"] = change_type
    out["DIFF_FLAG"] = (change_type != "SAME").astype(int)
    return out


COMPARE = {"label": "Сравнение по бакетам (ADJUSTED_VALUE)", "entrypoint": compare}
