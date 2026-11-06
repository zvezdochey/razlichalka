"""Чтение и запись CSV в едином формате (CONTRACTS §2): `;`, utf-8-sig, первая строка — заголовок."""

import csv
import os
from pathlib import Path
from typing import Iterable

import pandas as pd


def write_csv(path: Path, fieldnames: list[str], rows_iterable: Iterable[dict]) -> int:
    """Пишет строки потоком (не держит всё в памяти). Возвращает число записанных строк.

    Пишет во временный файл рядом и переименовывает в `path` только при успехе:
    при ошибке или отмене обрезанного файла на диске не остаётся.
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    count = 0
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for row in rows_iterable:
                writer.writerow(row)
                count += 1
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return count


def read_csv(path: Path) -> pd.DataFrame:
    """Читает CSV, все колонки — строки: `null`/`NA` не превращаются в NaN."""
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
