"""Загрузка встроенных процедур из папки `backend/procedures/` (docs/api.md п. 3).

Встроенная процедура — обычный .py-файл с одной переменной-словарём заглавными буквами
(`ARRAY_RULES`, `FIELD_MAP`). Это данные, а не логика: их можно открыть «как код этапа» и прочитать.

Файл грузим по пути через importlib, а не `import procedures...`: так `pipeline` не зависит от того,
как разложены пакеты, и папку можно подменить переменной окружения PROCEDURES_DIR.
"""

import importlib.util
import os
from pathlib import Path

from .errors import BadFile

# backend/pipeline/procedures.py -> backend/procedures
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "procedures"


def procedures_dir(path: Path | None = None) -> Path:
    """Папка процедур: аргумент → переменная PROCEDURES_DIR → backend/procedures."""
    if path is not None:
        return Path(path)
    return Path(os.environ.get("PROCEDURES_DIR") or DEFAULT_DIR)


def load_builtin(name: str, folder: Path | None = None) -> dict:
    """Словарь из `<папка>/<name>.py`. Ровно одна переменная-словарь заглавными буквами, иначе BadFile."""
    file = procedures_dir(folder) / f"{name}.py"
    if not file.is_file():
        raise BadFile(f"процедура {name}: нет файла {file}")
    spec = importlib.util.spec_from_file_location(f"razlichalka_procedure_{name}", file)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:  # синтаксическая ошибка и т. п. — понятная ошибка этапа
        raise BadFile(f"процедура {name}: файл не загрузить: {e}") from None
    found = [v for k, v in vars(module).items() if k.isupper() and isinstance(v, dict)]
    if len(found) != 1:
        raise BadFile(f"процедура {name}: в файле должна быть одна переменная-словарь заглавными буквами, "
                      f"найдено {len(found)}")
    return found[0]
