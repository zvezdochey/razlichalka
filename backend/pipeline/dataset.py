"""Работа с папкой датасета: манифест и список файлов среза."""

import json
from pathlib import Path

from .errors import BadFile


def read_manifest(dataset_dir: Path) -> dict:
    """Читает manifest.json. Нет файла или нужных полей -> BadFile с понятным текстом."""
    path = Path(dataset_dir) / "manifest.json"
    if not path.is_file():
        raise BadFile(f"в папке датасета {dataset_dir} нет manifest.json")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BadFile(f"manifest.json не читается: {e}") from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("srez"), dict):
        raise BadFile("в manifest.json нет поля srez")
    return manifest


def list_source_files(dataset_dir: Path, source: str) -> list[Path]:
    """Файлы среза (BEFORE/AFTER), отсортированные. Имя файла без .json = APP_ID."""
    manifest = read_manifest(dataset_dir)
    srez = manifest["srez"].get(source)
    if not isinstance(srez, dict) or not srez.get("dir"):
        raise BadFile(f"в manifest.json нет среза {source} (srez.{source}.dir)")
    folder = Path(dataset_dir) / srez["dir"]
    if not folder.is_dir():
        raise BadFile(f"папка среза {source} не найдена: {folder}")
    return sorted(folder.glob("*.json"))
