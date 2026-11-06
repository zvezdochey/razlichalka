"""Чтение неизменяемых результатов готового запуска."""
import json
from functools import lru_cache
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


def _artifact(run_dir: Path, filename: str) -> Path:
    path = run_dir / filename
    if not path.is_file():
        raise ApiError("not_found", f"Файл результатов «{filename}» не найден")
    return path


def summary(run_dir: Path) -> bytes:
    return _artifact(run_dir, "summary.json").read_bytes()


# Путь включает id запуска и различает хранилища. В кэше только файлы готовых запусков.
@lru_cache(maxsize=16)
def _apps(run_dir: Path) -> pd.DataFrame:
    rows = read_csv(_artifact(run_dir, "apps.csv"))[APP_FIELDS]
    rows["attributes_changed"] = pd.to_numeric(rows["attributes_changed"]).astype("Int64")
    return rows.set_index("app_id", drop=False).rename_axis(None)


@lru_cache(maxsize=16)
def _segments(run_dir: Path) -> pd.DataFrame:
    return read_csv(_artifact(run_dir, "segments.csv")).set_index("APP_ID")


@lru_cache(maxsize=4)
def _attributes(run_dir: Path) -> pd.DataFrame:
    rows = read_csv(_artifact(run_dir, "comparison.csv"))
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


def apps(
    run_dir: Path, *, decision_change: str, has_attr_change: bool, search: str,
    sort: str, page: int, size: int,
) -> dict:
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
    return _page(rows, "apps", page, size)


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


def _apps_ref(run_dir: Path, app_ids: list[str]) -> str | None:
    """Ссылка на список заявок для ручки 7.3. make_apps_ref приходит с I1; пока её нет — ссылки нет."""
    if not app_ids:
        return None
    try:
        from app.services.facts import make_apps_ref
    except ImportError:
        return None
    return make_apps_ref(run_dir, app_ids)


def _number(text: str):
    try:
        return float(text)
    except ValueError:
        return text


def checks(run_dir: Path, *, result: str, page: int, size: int) -> dict:
    """Таблица проверок (docs/api.md п. 10.1) из checks.csv."""
    if result and result not in ("PASS", "FAIL"):
        raise ApiError("bad_file", "result — PASS или FAIL")
    rows = read_csv(_artifact(run_dir, "checks.csv")).fillna("")
    index_file = run_dir / "checks_index.json"
    ids = json.loads(index_file.read_text(encoding="utf-8")) if index_file.is_file() else {}
    if result:
        rows = rows[rows["RESULT"] == result]
    start = (page - 1) * size
    out = []
    for r in rows.iloc[start:start + size].to_dict("records"):
        app_ids = [a for a in str(r["APP_IDS"]).split("|") if a]
        out.append({
            "check_id": ids.get(r["LABEL"]),
            "check_name": r["LABEL"],
            "source": r["SOURCE"] or None,
            "argument": r["ARGUMENT"] or None,
            "numbers": f"{r['CNT']} / {r['TOTAL']}" if r["CNT"] != "" else None,
            "metric": _number(r["METRIC"]) if r["METRIC"] != "" else None,
            "result": r["RESULT"],
            "apps_ref": _apps_ref(run_dir, app_ids),
            "faint": r["CONFIDENCE"] == "LOW",
        })
    return {"page": page, "size": size, "total": len(rows), "rows": out}
