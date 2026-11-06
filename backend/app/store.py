"""Хранилище: JSON-файлы в DATA_DIR/<kind>/<id>.json. Запись атомарная."""
import json
from typing import List
import os
import re
import tempfile
import threading
from pathlib import Path

from app import settings

_lock = threading.Lock()
_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _dir(kind: str) -> Path:
    if not _SAFE.match(kind):
        raise ValueError(f"плохой kind: {kind!r}")
    return Path(settings.DATA_DIR) / kind


def _path(kind: str, id: str) -> Path:
    if not _SAFE.match(id):
        raise ValueError(f"плохой id: {id!r}")
    return _dir(kind) / f"{id}.json"


def write_json(path: Path, obj) -> None:
    """Пишет во временный файл и подменяет настоящий — обрыв не оставит половину файла."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save(kind: str, id: str, obj: dict) -> None:
    path = _path(kind, id)
    with _lock:
        write_json(path, obj)


def load(kind: str, id: str) -> dict | None:
    try:
        return json.loads(_path(kind, id).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def list(kind: str) -> "List[dict]":  # noqa: A001 — имя из договора S3/S4
    folder = _dir(kind)
    if not folder.is_dir():
        return []
    items = []
    for p in sorted(folder.glob("*.json")):
        obj = load(kind, p.stem)
        if obj is not None:
            items.append(obj)
    return items


def delete(kind: str, id: str) -> bool:
    with _lock:
        try:
            _path(kind, id).unlink()
            return True
        except (FileNotFoundError, ValueError):
            return False
