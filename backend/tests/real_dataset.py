"""Где лежит настоящий датасет организаторов (в .gitignore). Нужен тестам с skipif."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_CANDIDATES = [
    ROOT / "ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001",
    ROOT / "ПАКЕТ/ПАКЕТ/ЗАДАНИЕ/ЗАДАНИЕ/data/RUN-20260827-0001",
]


def find_real_dataset() -> Path:
    """Папка с manifest.json. Можно задать переменной DATASET_DIR; иначе ищем в известных местах."""
    env = os.environ.get("DATASET_DIR")
    paths = ([Path(env)] if env else []) + _CANDIDATES
    for path in paths:
        if (path / "manifest.json").is_file():
            return path
    return paths[0]


REAL = find_real_dataset()
