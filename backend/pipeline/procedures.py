"""Загрузка встроенных процедур из папки `backend/procedures/` (docs/api.md п. 3).

Встроенная процедура — обычный .py-файл с одной переменной-словарём заглавными буквами
(`ARRAY_RULES`, `FIELD_MAP`). Это данные, а не логика: их можно открыть «как код этапа» и прочитать.

Файл грузим по пути через importlib, а не `import procedures...`: так `pipeline` не зависит от того,
как разложены пакеты. Папку передаёт вызывающий: приложение берёт её из `app/settings.py`
(PROCEDURES_DIR) и пробрасывает в этапы; без аргумента — `backend/procedures` рядом с кодом.
Переменные окружения здесь не читаем: источник правды о путях один — `app/settings.py`.

Файл исполняется как Python, поэтому так грузим только свои встроенные файлы из репозитория.
TODO (E13): пользовательские процедуры так грузить нельзя — их код надо исполнять в отдельном процессе
с таймаутом, как проверки (pipeline/checks_runner.py).
"""

import copy
import importlib.util
from pathlib import Path

from .errors import BadFile

# backend/pipeline/procedures.py -> backend/procedures
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "procedures"

# Кэш загруженных файлов: (путь, время изменения) -> словарь. Файл поменяли — перечитаем.
_cache: dict[tuple[str, float], dict] = {}


def load_builtin(name: str, folder: Path | None = None) -> dict:
    """Словарь из `<папка>/<name>.py` (копия — её можно менять).

    В файле должна быть ровно одна переменная-словарь заглавными буквами, иначе BadFile.
    """
    file = Path(folder or DEFAULT_DIR) / f"{name}.py"
    if not file.is_file():
        raise BadFile(f"процедура {name}: нет файла {file}")
    key = (str(file.resolve()), file.stat().st_mtime)
    if key not in _cache:
        _cache[key] = _exec(name, file)
    return copy.deepcopy(_cache[key])


def _exec(name: str, file: Path) -> dict:
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
