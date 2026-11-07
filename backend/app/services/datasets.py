"""Датасеты: каждая подпапка DATASETS_DIR и UPLOADS_DIR с manifest.json (docs/api.md п. 2.1)."""
import json
import logging

from app import settings

log = logging.getLogger("razlichalka")


def _read_manifest(folder) -> dict | None:
    """Читает manifest.json; битый манифест — None и запись в лог, а не падение."""
    try:
        m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        return {
            "id": str(m["run_id"]),
            "applications": int(m["applications"]),
            "sources": {"BEFORE": m["srez"]["BEFORE"]["label"], "AFTER": m["srez"]["AFTER"]["label"]},
            "technical_fields": list(m.get("technical_fields_always_differ", [])),
        }
    except Exception as exc:
        log.warning("Датасет %s пропущен — битый manifest.json: %s", folder.name, exc)
        return None


def _scan() -> list[dict]:
    """Все датасеты вместе с путём к папке (`path` нужен только бэку, наружу его не отдаём)."""
    folders = []
    for root in (settings.DATASETS_DIR, settings.UPLOADS_DIR):
        folders += sorted(root.iterdir()) if root.is_dir() else []
    result, seen = [], {}
    for folder in folders:
        if folder.name.startswith(".") or not (folder / "manifest.json").is_file():
            continue  # «.tmp-…» — загрузка ещё собирается (services/uploads.py)
        ds = _read_manifest(folder)
        if ds is None:
            continue
        if ds["id"] in seen:
            log.warning("Датасет %s пропущен — id %s уже занят папкой %s", folder.name, ds["id"], seen[ds["id"]])
            continue
        seen[ds["id"]] = folder.name
        ds["path"] = folder
        result.append(ds)
    if not result and settings.USE_STUB_PIPELINE:
        demo = _read_manifest(settings.STUB_RUN_DIR)
        if demo is not None:
            result.append({**demo, "path": settings.STUB_RUN_DIR})
    return result


def list_datasets() -> list[dict]:
    return [{k: v for k, v in ds.items() if k != "path"} for ds in _scan()]


def get_dataset(dataset_id: str) -> dict | None:
    """Датасет по id; в `path` — папка с manifest.json (id из манифеста может не совпадать с её именем)."""
    return next((d for d in _scan() if d["id"] == dataset_id), None)
