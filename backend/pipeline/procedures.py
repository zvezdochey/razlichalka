"""Загрузка встроенных процедур из папки `backend/procedures/` (docs/api.md п. 3).

Встроенная процедура — обычный .py-файл с одной переменной-словарём заглавными буквами
(`ARRAY_RULES`, `FIELD_MAP`). Это данные, а не логика: их можно открыть «как код этапа» и прочитать.
Рядом могут лежать второстепенные настройки — тоже заглавными, но не словари (`INPUT_PREFIXES` — список);
их читает `load_builtin_value`.

Файл грузим по пути через importlib, а не `import procedures...`: так `pipeline` не зависит от того,
как разложены пакеты. Папку передаёт вызывающий: приложение берёт её из `app/settings.py`
(PROCEDURES_DIR) и пробрасывает в этапы; без аргумента — `backend/procedures` рядом с кодом.
Переменные окружения здесь не читаем: источник правды о путях один — `app/settings.py`.

Файл исполняется как Python, поэтому так грузим только свои встроенные файлы из репозитория
и файлы, которые приложение само собрало в папке запуска. Код пользователя исполняется отдельно —
в дочернем процессе с таймаутом (pipeline/user_procedures.py).
"""

import copy
import importlib.util
from pathlib import Path

from .errors import BadFile

# backend/pipeline/procedures.py -> backend/procedures
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "procedures"

# Кэш загруженных файлов: (что грузили, путь, время изменения, размер) -> словарь. Файл поменяли — перечитаем.
_cache: dict[tuple, dict] = {}


def load_builtin(name: str, folder: Path | None = None) -> dict:
    """Словарь из `<папка>/<name>.py` (копия — её можно менять).

    В файле должна быть ровно одна переменная-словарь заглавными буквами, иначе BadFile.
    """
    file = _file(name, folder)
    key = ("dict", *_stamp(file))
    if key not in _cache:
        _cache[key] = _exec(name, file)
    return copy.deepcopy(_cache[key])


def load_builtin_value(name: str, var: str, folder: Path | None = None):
    """Переменная `var` (заглавными буквами) из `<папка>/<name>.py` — копия, её можно менять.

    Для второстепенных настроек процедуры рядом с главным словарём (например, `INPUT_PREFIXES`
    в `builtin_segments.py`). Нет переменной — BadFile.
    """
    file = _file(name, folder)
    key = ("value", *_stamp(file))
    if key not in _cache:
        _cache[key] = {k: v for k, v in vars(_module(name, file)).items() if k.isupper()}
    if var not in _cache[key]:
        raise BadFile(f"процедура {name}: в файле нет переменной {var}")
    return copy.deepcopy(_cache[key][var])


def load_builtin_module(name: str, folder: Path | None = None) -> dict:
    """Все переменные модуля `<папка>/<name>.py` — для встроенной процедуры-функции (сравнение).

    Только для своих файлов из репозитория: код исполняется в этом процессе.
    """
    file = _file(name, folder)
    key = ("module", *_stamp(file))
    if key not in _cache:
        _cache[key] = dict(vars(_module(name, file)))
    return _cache[key]


def _stamp(file: Path) -> tuple:
    """Отпечаток файла для кэша. Размер — на случай, если файл переписали быстрее, чем тикают часы ФС."""
    st = file.stat()
    return str(file.resolve()), st.st_mtime_ns, st.st_size


def _file(name: str, folder: Path | None) -> Path:
    file = Path(folder or DEFAULT_DIR) / f"{name}.py"
    if not file.is_file():
        raise BadFile(f"процедура {name}: нет файла {file}")
    return file


def _module(name: str, file: Path):
    spec = importlib.util.spec_from_file_location(f"razlichalka_procedure_{name}", file)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:  # синтаксическая ошибка и т. п. — понятная ошибка этапа
        raise BadFile(f"процедура {name}: файл не загрузить: {e}") from None
    return module


def _exec(name: str, file: Path) -> dict:
    found = [v for k, v in vars(_module(name, file)).items() if k.isupper() and isinstance(v, dict)]
    if len(found) != 1:
        raise BadFile(f"процедура {name}: в файле должна быть одна переменная-словарь заглавными буквами, "
                      f"найдено {len(found)}")
    return found[0]
