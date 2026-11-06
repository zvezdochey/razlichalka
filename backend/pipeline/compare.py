"""Сравнение двух срезов (E5): normalized_BEFORE.csv + normalized_AFTER.csv → comparison.csv.

Ключ строки — (APP_ID, PATH, ARRAY_KEY). Сравниваем строго по VALUE (не по ADJUSTED_VALUE):
значение, сменившееся внутри одного бакета, — всё равно VALUE_CHANGED.
Строка `null` (JSON null) и «атрибута нет в срезе» — разные случаи: второе даёт пустые ячейки стороны.
"""

from pathlib import Path

import pandas as pd

from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile

KEY = ["APP_ID", "PATH", "ARRAY_KEY"]
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


def compare_csv(before_csv: Path, after_csv: Path, out_csv: Path, log=None) -> int:
    """Строит витрину сравнения. Возвращает число записанных строк."""
    before = _load(before_csv, "BEFORE")
    after = _load(after_csv, "AFTER")

    merged = before.merge(
        after, on=KEY, how="outer", suffixes=("_B", "_A"), indicator=True
    )
    both = merged["_merge"] == "both"
    only_before = merged["_merge"] == "left_only"
    only_after = merged["_merge"] == "right_only"

    out = pd.DataFrame({c: merged[c] for c in ["APP_ID", "ARRAY_KEY", "PATH"]})
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
    out["DIFF_FLAG"] = (change_type != "SAME").astype(int).astype(str)

    out = out[COLUMNS].sort_values(KEY, kind="stable")

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
