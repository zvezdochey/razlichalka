"""Факты по витрине готового запуска и ссылки на группы заявок."""
import hashlib
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from time import time_ns

import pandas as pd

from app.errors import ApiError
from app.services.results import result_file
from pipeline.csvio import read_csv

_MAX_GROUP_REFS = 20_000


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
    if raw.lstrip().startswith("{"):
        try:
            filters = json.loads(raw)
            if not isinstance(filters, dict):
                raise ValueError
            for name, choices in filters.items():
                if not isinstance(choices, list) or not choices or any(not isinstance(value, str) for value in choices):
                    raise ValueError
                conditions.append([name, choices])
        except ValueError:
            raise ApiError("bad_file", "Фильтр JSON должен содержать поля с непустыми списками строк") from None
    else:
        for condition in raw.split(";") if raw else []:
            name, separator, values = condition.partition(":")
            if not separator:
                raise ApiError("bad_file", f"Некорректное условие фильтра «{condition}»")
            conditions.append([name.strip(), values.split(",")])

    for condition in conditions:
        name, choices = condition
        if name not in columns:
            raise ApiError("bad_file", f"Неизвестное поле фильтра «{name}»")
        if name == "DIFF_FLAG":
            if any(value not in ("0", "1") for value in choices):
                raise ApiError("bad_file", "Для DIFF_FLAG допустимы только значения 0 и 1")
            condition[1] = [int(value) for value in choices]
    return conditions


def _filter_rows(rows: pd.DataFrame, conditions: list) -> pd.DataFrame:
    if not conditions:
        return rows
    mask = pd.Series(True, index=rows.index)
    for name, choices in conditions:
        mask &= rows[name].isin(choices)
    return rows[mask]


def _ref_database(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path)
    try:
        database.execute(
            """CREATE TABLE IF NOT EXISTS refs (
                ref TEXT PRIMARY KEY, definition TEXT NOT NULL,
                persistent INTEGER NOT NULL, touched INTEGER NOT NULL
            )"""
        )
        return database
    except BaseException:
        database.close()
        raise


def _load_ref(run_dir: Path, ref: str) -> dict | None:
    path = run_dir / "facts_refs.sqlite3"
    if path.is_file():
        with closing(_ref_database(path)) as database:
            row = database.execute("SELECT definition FROM refs WHERE ref = ?", (ref,)).fetchone()
        if row is not None:
            return json.loads(row[0])

    # Ссылки, выданные до смены формата хранилища, остаются доступны.
    try:
        old_refs = json.loads((run_dir / "facts_refs.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    return old_refs.get(ref)


def _save_refs(run_dir: Path, definitions: list[dict]) -> list[str]:
    if not definitions:
        return []
    records = []
    for definition in definitions:
        payload = json.dumps([run_dir.name, definition], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        ref = "f_" + hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        records.append((ref, json.dumps(definition, ensure_ascii=False), "app_ids" in definition))

    with closing(_ref_database(run_dir / "facts_refs.sqlite3")) as database, database:
        database.execute("BEGIN IMMEDIATE")
        touched = time_ns()
        database.execute(
            "CREATE INDEX IF NOT EXISTS recent_groups ON refs(touched DESC, ref) WHERE persistent = 0"
        )
        database.executemany(
            """INSERT INTO refs (ref, definition, persistent, touched) VALUES (?, ?, ?, ?)
               ON CONFLICT(ref) DO UPDATE SET touched = MAX(refs.touched, excluded.touched)""",
            ((*record, touched) for record in records),
        )
        database.execute(
            """DELETE FROM refs WHERE ref IN (
                SELECT ref FROM refs WHERE persistent = 0 ORDER BY touched DESC, ref LIMIT -1 OFFSET ?
            )""",
            (_MAX_GROUP_REFS,),
        )
    return [record[0] for record in records]


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


def group_app_ids(run_dir: Path, ref: str) -> list[str]:
    """Все заявки группы по ссылке `app_ids_ref` (клетка сводной или строка проверки)."""
    definition = _load_ref(run_dir, ref)
    if definition is None:
        raise ApiError("not_found", "Группа заявок не найдена")
    if "app_ids" in definition:
        return definition["app_ids"]
    conditions = definition["filter"] + [[name, [value]] for name, value in definition["group"]]
    return sorted(_filter_rows(_facts_base(run_dir), conditions)["APP_ID"].unique().tolist())


def fact_apps(run_dir: Path, ref: str, *, page: int, size: int) -> dict:
    app_ids = group_app_ids(run_dir, ref)

    start = (page - 1) * size
    return {"page": page, "size": size, "total": len(app_ids), "apps": app_ids[start:start + size]}
