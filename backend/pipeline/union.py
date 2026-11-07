"""Вертикальная витрина (datamart) по ТЗ: строки BEFORE и AFTER одна под другой, срез — в поле SOURCE.

normalized_BEFORE.csv + normalized_AFTER.csv (+ comparison.csv) -> union.csv

Это технический слой из ТЗ («вертикальный UNION, принадлежность к срезу — в SOURCE»). По нему сводная считает
распределения «значение или бакет × срез» для любого атрибута. Горизонтальная comparison.csv (VALUE_BEFORE /
VALUE_AFTER) остаётся результатом сравнения: её читают проверки организаторов (MartAPI) и сводная «до → после».

К каждой строке приписан признак различия её атрибута — DIFF_FLAG и CHANGE_TYPE из сравнения по ключу
(APP_ID, PATH, ARRAY_KEY): так в вертикальной сводной можно оставить только изменившиеся атрибуты.
Заявки без пары (их нет в comparison.csv, см. compare.py) в витрину не попадают — числа сходятся со сравнением.
"""

import os
from pathlib import Path

import pandas as pd

from pipeline.csvio import read_csv

KEY = ["APP_ID", "PATH", "ARRAY_KEY"]
COLUMNS = ["APP_ID", "SOURCE", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH", "VALUE", "ADJUSTED_VALUE",
           "DIFF_FLAG", "CHANGE_TYPE"]


def build_union(before_csv: Path, after_csv: Path, comparison_csv: Path, out_csv: Path) -> int:
    """Пишет union.csv. Возвращает число строк."""
    union = pd.concat([read_csv(before_csv), read_csv(after_csv)], ignore_index=True)
    flags = read_csv(comparison_csv)[KEY + ["DIFF_FLAG", "CHANGE_TYPE"]]
    # inner: только заявки с парой — те, что есть в сравнении
    union = union.merge(flags, on=KEY, how="inner", validate="many_to_one")[COLUMNS]
    tmp = Path(out_csv).with_name(Path(out_csv).name + ".tmp")
    union.to_csv(tmp, sep=";", index=False, encoding="utf-8-sig")
    os.replace(tmp, out_csv)  # обрыв записи не оставит половину файла
    return len(union)
