"""Чтение и запись CSV в едином формате (CONTRACTS §2): `;`, utf-8-sig, первая строка — заголовок."""

import csv
from pathlib import Path
from typing import Iterable

import pandas as pd


def write_csv(path: Path, fieldnames: list[str], rows_iterable: Iterable[dict]) -> int:
    """Пишет строки потоком (не держит всё в памяти). Возвращает число записанных строк."""
    count = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows_iterable:
            writer.writerow(row)
            count += 1
    return count


def read_csv(path: Path) -> pd.DataFrame:
    """Читает CSV, все колонки — строки: `null`/`NA` не превращаются в NaN."""
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
