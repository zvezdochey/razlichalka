"""Загрузка датасета (docs/api.md п. 2.2): файлы в любом формате -> папка датасета в UPLOADS_DIR.

Папка получается такой же, как у организаторов (manifest.json + RESULTS/<СРЕЗ>_<метка>/<APP_ID>.json),
поэтому нормализация, сравнение и всё остальное работают как раньше. Собираем во временной папке и
переименовываем в конце: недоделанного датасета в списке не бывает.
"""
import json
import re
import secrets
import shutil
from datetime import datetime

from app import settings
from app.errors import ApiError
from pipeline.array_rules import default_array_rules
from pipeline.errors import BadFile
from pipeline.ingest import EXTENSIONS, MAX_UNPACKED, iter_files, ext_of, split_apps

SOURCES = ("BEFORE", "AFTER")
MIN_PAIRS_FOR_AUTODETECT = 3  # меньше пар — «различается у каждой» ничего не доказывает
MAX_APPS = 50_000
MAX_LABEL = 40


def _read_source(source: str, uploads: list[tuple[str, bytes]], array_paths: set[str], budget: list[int]):
    """Все файлы среза -> ({app_id: ответ}, {формат: сколько файлов})."""
    apps: dict[str, dict] = {}
    origin: dict[str, str] = {}
    formats = {"json": 0, "xml": 0, "csv": 0}
    for upload_name, data in uploads:
        if ext_of(upload_name) not in (*EXTENSIONS, ".zip"):
            raise ApiError("bad_request", f"Файл {upload_name}: нужен .json, .xml, .csv или .zip")
        for name, ext, content in iter_files(upload_name, data, budget):
            for doc in split_apps(name, ext, content, array_paths):
                app_id = doc["appData"]["application_id"]
                if app_id in apps:
                    raise BadFile(f"в срезе {source} заявка {app_id} встречается дважды: {origin[app_id]} и {name}")
                if len(apps) >= MAX_APPS:
                    raise BadFile(f"в срезе {source} больше {MAX_APPS} заявок")
                apps[app_id], origin[app_id] = doc, name
            formats[ext[1:]] += 1
    if not apps:
        raise BadFile(f"в срезе {source} нет ни одной заявки: нужны файлы .json, .xml или .csv")
    return apps, formats


def _leaves(node, prefix: str = ""):
    """Скалярные пути вне массивов: массивы сопоставляются по ключу, их позиции для «всегда различается» не годятся."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{prefix}.{key}" if prefix else key)
    elif not isinstance(node, list):
        yield prefix, node


def detect_technical_fields(before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    """Пути, которые отличаются у КАЖДОЙ пары заявок (request_id, время создания и т. п.)."""
    pairs = sorted(before.keys() & after.keys())
    if len(pairs) < MIN_PAIRS_FOR_AUTODETECT:
        return []
    seen: dict[str, int] = {}
    differ: dict[str, int] = {}
    for app_id in pairs:
        left, right = dict(_leaves(before[app_id])), dict(_leaves(after[app_id]))
        for path in left.keys() & right.keys():
            seen[path] = seen.get(path, 0) + 1
            differ[path] = differ.get(path, 0) + (left[path] != right[path])
    return sorted(p for p, n in seen.items() if n == len(pairs) and differ[p] == len(pairs))


def _list_paths(node, path: str = "", out: set[str] | None = None) -> set[str]:
    """Пути всех списков заявки в виде, как их видит разбор: `a.b[]`, а внутри списка — `a[].c[]`."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            _list_paths(value, f"{path}.{key}" if path else key, out)
    elif isinstance(node, list):
        arr = path + "[]"
        out.add(arr)
        for item in node:
            _list_paths(item, arr, out)
    return out


def _label(raw: str | None, default: str) -> str:
    label = (raw or "").strip() or default
    if len(label) > MAX_LABEL:
        raise ApiError("bad_request", f"Название среза длиннее {MAX_LABEL} знаков")
    return label


def create_dataset(before: list[tuple[str, bytes]], after: list[tuple[str, bytes]], before_label: str | None = None,
                   after_label: str | None = None, technical_fields: list[str] | None = None) -> dict:
    """Собирает датасет из загрузки. Ошибки: ApiError(bad_request) или pipeline.BadFile (bad_file)."""
    if not before or not after:
        raise ApiError("bad_request", "Нужны оба среза: файлы «до» и файлы «после»")
    labels = {"BEFORE": _label(before_label, "BEFORE"), "AFTER": _label(after_label, "AFTER")}
    if labels["BEFORE"] == labels["AFTER"]:
        raise ApiError("bad_request", "Названия срезов «до» и «после» должны различаться")
    def read_all(array_paths: set[str]):
        budget = [MAX_UNPACKED]
        apps, received = {}, {}
        for source, uploads in zip(SOURCES, (before, after)):
            apps[source], formats = _read_source(source, uploads, array_paths, budget)
            received[source] = {"applications": len(apps[source]), **formats}
        return apps, received

    array_paths = set(default_array_rules(settings.PROCEDURES_DIR))
    apps, received = read_all(array_paths)
    # В XML одиночный тег неотличим от поля: массив определяем по всему датасету (списки в JSON и повторы в XML).
    # Если путь где-то список, в XML его тоже читаем списком, иначе срезы сравнятся как скаляр против списка.
    if any(received[s]["xml"] for s in SOURCES):
        found = set().union(*(_list_paths(doc) for s in SOURCES for doc in apps[s].values()))
        if found - array_paths:
            apps, received = read_all(array_paths | found)

    technical = [t.strip() for t in technical_fields or [] if t.strip()]
    try:
        if not technical:
            technical = detect_technical_fields(apps["BEFORE"], apps["AFTER"])
        bodies = {s: {i: json.dumps(d, ensure_ascii=False, indent=1) for i, d in apps[s].items()} for s in SOURCES}
    except RecursionError:
        raise BadFile("в заявках слишком глубокая вложенность") from None

    dataset_id = f"UP-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"
    dirs = {s: f"RESULTS/{s}_{re.sub(r'[^\w.-]+', '_', labels[s])}" for s in SOURCES}
    manifest = {
        "run_id": dataset_id,
        "applications": max(len(apps["BEFORE"]), len(apps["AFTER"])),
        "srez": {s: {"label": labels[s], "dir": dirs[s]} for s in SOURCES},
        "technical_fields_always_differ": technical,
    }
    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = settings.UPLOADS_DIR / f".tmp-{dataset_id}"
    try:
        for source in SOURCES:
            (tmp / dirs[source]).mkdir(parents=True)
            for app_id, body in bodies[source].items():
                (tmp / dirs[source] / f"{app_id}.json").write_text(body, encoding="utf-8")
        (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(settings.UPLOADS_DIR / dataset_id)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    return {
        "dataset": {
            "id": dataset_id,
            "applications": manifest["applications"],
            "sources": labels,
            "technical_fields": technical,
        },
        "received": received,
        "applications_only_before": len(apps["BEFORE"].keys() - apps["AFTER"].keys()),
        "applications_only_after": len(apps["AFTER"].keys() - apps["BEFORE"].keys()),
    }
