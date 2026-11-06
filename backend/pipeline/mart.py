"""Витрина `mart` для автопроверок (MartAPI из ПАКЕТ/ЗАДАНИЕ/checks/README.md).

Читает comparison.csv и segments.csv и отдаёт их проверкам. Вызовов много, строк ~290 тысяч,
поэтому индексы (колонка -> позиции строк) строим один раз и лениво: `groupby(...).indices` у pandas.
Фильтры объединяются через И; каждый фильтр — одно значение или список.

Строки отдаются как `dict` с ключами колонок витрины в верхнем регистре, все значения — строки
(как в CSV), кроме двух поправок в `segments()`, без которых готовые проверки организаторов не работают:
  * `DECISION_CHANGED` — число 0/1 (иначе строка "0" в `if s.get(...)` считалась бы «истиной»);
  * `PRODUCTS` — через `;` (проверка организаторов делает `.split(";")`, а в файле разделитель `|`).
"""

from pathlib import Path

import numpy as np

from .csvio import read_csv

# Фильтр -> колонка витрины
_FILTER_COLUMNS = {
    "path": "PATH",
    "key": "KEY",
    "array_key": "ARRAY_KEY",
    "diff_flag": "DIFF_FLAG",
    "change_type": "CHANGE_TYPE",
    "value_before": "VALUE_BEFORE",
    "value_after": "VALUE_AFTER",
    "app_ids": "APP_ID",
}
_FILTERS = set(_FILTER_COLUMNS) | {"path_prefix"}


def _as_list(value) -> list[str]:
    """Одно значение или список -> список строк (0/1 из diff_flag превращаем в '0'/'1')."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(v) for v in value]
    return [str(value)]


class Mart:
    def __init__(self, comparison_csv: Path, segments_csv: Path):
        self.comparison_csv = Path(comparison_csv)
        self.segments_csv = Path(segments_csv)
        self._df = read_csv(self.comparison_csv)
        self._records = self._df.to_dict("records")
        self._segments = self._load_segments(self.segments_csv)
        self._indexes: dict[str, dict] = {}
        self._prefix_cache: dict[str, list[str]] = {}
        self._all = np.arange(len(self._records))

    @staticmethod
    def _load_segments(path: Path) -> list[dict]:
        rows = read_csv(path).to_dict("records")
        for r in rows:
            r["DECISION_CHANGED"] = 1 if r.get("DECISION_CHANGED") == "1" else 0
            r["PRODUCTS"] = (r.get("PRODUCTS") or "").replace("|", ";")
        return rows

    # --- индексы -------------------------------------------------------------

    def _index(self, column: str) -> dict:
        if column not in self._indexes:
            self._indexes[column] = dict(self._df.groupby(column, sort=False).indices)
        return self._indexes[column]

    def _positions(self, column: str, values: list[str]) -> np.ndarray:
        idx = self._index(column)
        parts = [idx[v] for v in values if v in idx]
        if not parts:
            return np.empty(0, dtype=np.intp)
        return parts[0] if len(parts) == 1 else np.unique(np.concatenate(parts))

    def _select(self, filters: dict) -> np.ndarray:
        """Позиции строк, подходящих под все фильтры (по возрастанию, то есть в порядке файла)."""
        unknown = set(filters) - _FILTERS
        if unknown:
            raise TypeError(f"Неизвестный фильтр витрины: {', '.join(sorted(unknown))}")
        result = None
        for name, value in filters.items():
            if value is None:
                continue
            if name == "path_prefix":
                prefix = str(value)
                if prefix not in self._prefix_cache:
                    self._prefix_cache[prefix] = [p for p in self._index("PATH") if p.startswith(prefix)]
                pos = self._positions("PATH", self._prefix_cache[prefix])
            else:
                pos = self._positions(_FILTER_COLUMNS[name], _as_list(value))
            result = pos if result is None else np.intersect1d(result, pos, assume_unique=True)
            if result.size == 0:
                break
        return self._all if result is None else result

    # --- MartAPI -------------------------------------------------------------

    def rows(self, **filters) -> list[dict]:
        """Строки витрины сравнения (копии — проверка может их менять)."""
        return [dict(self._records[i]) for i in self._select(filters)]

    def count(self, **filters) -> int:
        return int(self._select(filters).size)

    def app_ids(self, **filters) -> list[str]:
        pos = self._select(filters)
        return sorted(set(self._df["APP_ID"].to_numpy()[pos].tolist()))

    def segments(self) -> list[dict]:
        return [dict(s) for s in self._segments]

    def total_apps(self) -> int:
        if self._segments:
            return len(self._segments)
        return len(self._index("APP_ID"))
