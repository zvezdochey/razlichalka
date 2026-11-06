"""Датасеты: каждая подпапка DATASETS_DIR с manifest.json (docs/api.md п. 2.1)."""
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


def list_datasets() -> list[dict]:
    root = settings.DATASETS_DIR
    if not root.is_dir():
        return []
    result = []
    for folder in sorted(root.iterdir()):
        if (folder / "manifest.json").is_file():
            ds = _read_manifest(folder)
            if ds:
                result.append(ds)
    return result


def get_dataset(dataset_id: str) -> dict | None:
    return next((d for d in list_datasets() if d["id"] == dataset_id), None)
