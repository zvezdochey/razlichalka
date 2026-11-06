"""Факты по витрине готового запуска и ссылки на группы заявок."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from threading import Lock

import pandas as pd

from app import store
from app.errors import ApiError
from app.services.results import result_file
from pipeline.csvio import read_csv

_refs_lock = Lock()


@lru_cache(maxsize=4)
def _facts_base(run_dir: Path) -> pd.DataFrame:
    comparison = read_csv(result_file(run_dir, "comparison.csv"))
    segments = read_csv(result_file(run_dir, "segments.csv"))
    app_ids = pd.Index(comparison["APP_ID"].unique()).union(segments["APP_ID"].unique())
    app_id_dtype = pd.CategoricalDtype(app_ids)
    comparison = comparison.astype({
        **dict.fromkeys(comparison.columns.drop(["APP_ID", "DIFF_FLAG"]), "category"),
        "APP_ID": app_id_dtype,
        "DIFF_FLAG": int,
    })
    segments = segments.astype({**dict.fromkeys(segments.columns, "category"), "APP_ID": app_id_dtype})
    comparison["ARRAY_KEY_1"] = comparison["ARRAY_KEY"].map(lambda key: key.partition("|")[0]).astype("category")

    rows = comparison.merge(segments, on="APP_ID", how="left", validate="many_to_one")
    for name in segments.columns.drop("APP_ID"):
        column = rows[name]
        if column.isna().any():
            if "" not in column.cat.categories:
                column = column.cat.add_categories([""])
            rows[name] = column.fillna("")
    return rows


def _parse_filter(raw: str, columns: pd.Index) -> list:
    conditions = []
    for condition in raw.split(";") if raw else []:
        name, separator, values = condition.partition(":")
        name = name.strip()
        if not separator or name not in columns:
            raise ApiError("bad_file", f"Некорректное условие фильтра «{condition}»")
        choices = values.split(",")
        if name == "DIFF_FLAG":
            choices = [int(value) for value in choices if value in ("0", "1")]
        conditions.append([name, choices])
    return conditions


def _filter_rows(rows: pd.DataFrame, conditions: list) -> pd.DataFrame:
    if not conditions:
        return rows
    mask = pd.Series(True, index=rows.index)
    for name, choices in conditions:
        mask &= rows[name].isin(choices)
    return rows[mask]


def _load_refs(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _save_refs(run_dir: Path, definitions: list[dict]) -> list[str]:
    if not definitions:
        return []
    refs = []
    for definition in definitions:
        payload = json.dumps([run_dir.name, definition], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        refs.append("f_" + hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:12])
    path = run_dir / "facts_refs.json"
    with _refs_lock:
        saved = _load_refs(path)
        new = {ref: definition for ref, definition in zip(refs, definitions) if ref not in saved}
        if new:
            saved.update(new)
            store.write_json(path, saved)
    return refs


def make_apps_ref(run_dir: Path, filters: dict | list[str]) -> str:
    """Для проверки принимает список APP_ID. Для группы — словарь с двумя полями.

    filter: список пар [поле, список допустимых значений].
    group: список пар [поле измерения, значение группы].
    """
    definition = {"app_ids": sorted(set(filters))} if isinstance(filters, list) else filters
    return _save_refs(run_dir, [definition])[0]


def facts(run_dir: Path, *, dims: str, filter_: str, measure: str, limit: int) -> dict:
    names = [name.strip() for name in dims.split(",")]
    if not 1 <= len(names) <= 3 or len(set(names)) != len(names) or not all(names):
        raise ApiError("bad_file", "Укажите от одного до трёх разных измерений")
    if measure not in ("counts", "counts_distinct_apps"):
        raise ApiError("bad_file", f"Неизвестный показатель «{measure}»")

    base = _facts_base(run_dir)
    for name in names:
        if name not in base.columns:
            raise ApiError("bad_file", f"Неизвестное измерение «{name}»")
    conditions = _parse_filter(filter_, base.columns)
    grouped = _filter_rows(base, conditions).groupby(names, observed=True)
    counts = grouped.size() if measure == "counts" else grouped["APP_ID"].nunique()

    rows = counts.nlargest(limit).reset_index(name="counts").to_dict("records")
    definitions = [{"filter": conditions, "group": [[name, row[name]] for name in names]} for row in rows]
    for row, ref in zip(rows, _save_refs(run_dir, definitions)):
        for name in names:
            if row[name] == "":
                row[name] = None
        row["app_ids_ref"] = ref
    return {"dims": names, "rows": rows, "total_groups": len(counts)}


def fact_apps(run_dir: Path, ref: str, *, page: int, size: int) -> dict:
    with _refs_lock:
        definition = _load_refs(run_dir / "facts_refs.json").get(ref)
    if definition is None:
        raise ApiError("not_found", "Группа заявок не найдена")

    if "app_ids" in definition:
        app_ids = definition["app_ids"]
    else:
        conditions = definition["filter"] + [[name, [value]] for name, value in definition["group"]]
        app_ids = sorted(_filter_rows(_facts_base(run_dir), conditions)["APP_ID"].unique().tolist())

    start = (page - 1) * size
    return {"page": page, "size": size, "total": len(app_ids), "apps": app_ids[start:start + size]}
