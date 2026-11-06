"""Чтение неизменяемых результатов готового запуска."""
from csv import DictWriter
from functools import lru_cache
from io import StringIO
from pathlib import Path

import pandas as pd

from app.errors import ApiError
from pipeline.csvio import read_csv

APP_FIELDS = [
    "app_id", "decision_before", "decision_after", "decision_change", "attributes_changed",
    "pd_model_before", "pd_model_after", "cutoff_before", "cutoff_after",
    "reject_reason_before", "reject_reason_after",
]
SEGMENT_SEARCH_FIELDS = [
    "PRODUCTS", "TOP_OFFER_BEFORE", "TOP_OFFER_AFTER", "PARTNER_TYPE", "ROUTING_METHOD",
]
ATTRIBUTE_FIELDS = [
    "path", "array_key", "key", "value_before", "value_after", "adjusted_before",
    "adjusted_after", "diff_flag", "change_type",
]


def result_file(run_dir: Path, filename: str) -> Path:
    path = run_dir / filename
    if not path.is_file():
        raise ApiError("not_found", f"Файл результатов «{filename}» не найден")
    return path


def summary(run_dir: Path) -> bytes:
    return result_file(run_dir, "summary.json").read_bytes()


# Путь включает id запуска и различает хранилища. В кэше только файлы готовых запусков.
@lru_cache(maxsize=16)
def _apps(run_dir: Path) -> pd.DataFrame:
    rows = read_csv(result_file(run_dir, "apps.csv"))[APP_FIELDS]
    rows["attributes_changed"] = pd.to_numeric(rows["attributes_changed"]).astype("Int64")
    return rows.set_index("app_id", drop=False).rename_axis(None)


@lru_cache(maxsize=16)
def _segments(run_dir: Path) -> pd.DataFrame:
    return read_csv(result_file(run_dir, "segments.csv")).set_index("APP_ID")


@lru_cache(maxsize=4)
def _attributes(run_dir: Path) -> pd.DataFrame:
    rows = read_csv(result_file(run_dir, "comparison.csv"))
    rows.columns = rows.columns.str.lower()
    rows["diff_flag"] = rows["diff_flag"].astype(int)
    return rows.set_index("app_id")[ATTRIBUTE_FIELDS]


def _contains(column: pd.Series, term: str) -> pd.Series:
    return column.str.casefold().str.contains(term, regex=False)


def _page(rows: pd.DataFrame, key: str, page: int, size: int) -> dict:
    start = (page - 1) * size
    records = rows.iloc[start:start + size].to_dict("records")
    return {
        "page": page,
        "size": size,
        "total": len(rows),
        key: [
            {name: value if value != "" else None for name, value in row.items()}
            for row in records
        ],
    }


def _filter_apps(
    run_dir: Path, *, decision_change: str, has_attr_change: bool, search: str, sort: str,
) -> pd.DataFrame:
    field = sort.removeprefix("-")
    if sort and field not in APP_FIELDS:
        raise ApiError("bad_file", f"Неизвестное поле сортировки «{field}»")

    rows = _apps(run_dir)
    if decision_change:
        changes = [change.strip() for change in decision_change.split(",")]
        rows = rows[rows["decision_change"].isin(changes)]
    if has_attr_change:
        rows = rows[rows["attributes_changed"] > 0]
    if search:
        term = search.casefold()
        matches = _contains(rows["app_id"], term)
        for name in APP_FIELDS[5:]:
            matches |= _contains(rows[name], term)
        segments = _segments(run_dir)
        for name in SEGMENT_SEARCH_FIELDS:
            matches |= rows["app_id"].isin(segments.index[_contains(segments[name], term)])
        rows = rows[matches]
    if sort:
        rows = rows.sort_values(field, ascending=not sort.startswith("-"), kind="stable")
    return rows


def apps(
    run_dir: Path, *, decision_change: str, has_attr_change: bool, search: str,
    sort: str, page: int, size: int,
) -> dict:
    rows = _filter_apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change, search=search, sort=sort,
    )
    return _page(rows, "apps", page, size)


def _excel_value(value):
    # Excel распознаёт текст, начинающийся с этих символов, как формулу.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")):
        return "'" + value
    return value


def export_apps(
    run_dir: Path, *, decision_change: str, has_attr_change: bool, search: str, sort: str,
) -> bytes:
    rows = _filter_apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change, search=search, sort=sort,
    )
    records = ({name: _excel_value(value) for name, value in row.items()} for row in rows.to_dict("records"))
    output = StringIO(newline="")
    writer = DictWriter(output, fieldnames=APP_FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8-sig")


def attributes(
    run_dir: Path, app_id: str, *, only_diff: bool, search: str, page: int, size: int,
) -> dict:
    if app_id not in _apps(run_dir).index:
        raise ApiError("not_found", "Заявка не найдена")

    rows = _attributes(run_dir)
    rows = rows.loc[[app_id]] if app_id in rows.index else rows.iloc[:0]
    if only_diff:
        rows = rows[rows["diff_flag"] == 1]
    if search:
        rows = rows[_contains(rows["path"], search.casefold())]
    rows = rows.sort_values(["diff_flag", "path"], ascending=[False, True])
    return {"app_id": app_id, **_page(rows, "attributes", page, size)}
