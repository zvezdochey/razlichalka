"""Исполнение пользовательских процедур этапов: приведение, сравнение, факты (docs/api.md п. 3).

Как и проверки (pipeline/checks_runner.py), код пользователя исполняется в отдельном процессе с таймаутом,
без переменных окружения, во временной папке и с лимитами ОС. Главный процесс получает только результат.

Два вида процедур:
  * «процедуры-данные» — приведение (`ARRAY_RULES`) и факты (`FIELD_MAP`, `INPUT_PREFIXES`): код исполняется,
    наружу отдаются переменные заглавными буквами. Из них этап пишет файл процедуры в папку запуска
    (`runs/<id>/procedures/`) — его и читает разбор. Так разбор не исполняет чужой код у себя;
  * «процедура-функция» — сравнение (`COMPARE["entrypoint"](before, after)` -> DataFrame витрины).
"""

import ast
import json
import multiprocessing as mp
import pprint
import queue
import shutil
import types
from pathlib import Path

from .checks_runner import _enter_temp_dir, _limit_resources, _restrict_env, forbidden_code_problems
from .errors import BadFile

LOAD_TIMEOUT = 30      # секунд на исполнение кода процедуры-данных
COMPARE_TIMEOUT = 300  # секунд на сравнение всего датасета (встроенное идёт ~10 с)

# Что обязательно должно быть в коде процедуры каждого вида
REQUIRED = {"normalize": ["ARRAY_RULES"], "aggregate": ["FIELD_MAP"], "compare": ["COMPARE"]}


def static_problems(kind: str, code: str) -> list[dict]:
    """Проверка без запуска: компилируется, нет запрещённых модулей, есть обязательные переменные."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"line": e.lineno or 1, "message": f"Синтаксическая ошибка: {e.msg}"}]
    problems = forbidden_code_problems(tree)
    if problems:
        return problems
    assigned = {t.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, ast.Name)}
    for name in REQUIRED.get(kind, []):
        if name not in assigned:
            hint = {"ARRAY_RULES": "словарь правил массивов", "FIELD_MAP": "словарь «поле разреза -> путь»",
                    "COMPARE": "словарь с entrypoint — функцией compare(before, after)"}[name]
            return [{"line": 1, "message": f"Нет переменной {name} = {{...}} ({hint})"}]
    return []


def _exec(code: str, name: str) -> types.ModuleType:
    """Исполняет код как модуль. ТОЛЬКО в дочернем процессе."""
    module = types.ModuleType("user_procedure")
    try:
        exec(compile(code, name, "exec"), module.__dict__)
    except SyntaxError as e:
        raise BadFile(f"Синтаксическая ошибка в строке {e.lineno}: {e.msg}") from e
    except Exception as e:
        raise BadFile(f"Код процедуры упал при загрузке: {type(e).__name__}: {e}") from e
    return module


def _error_text(e: BaseException) -> str:
    return str(e) if isinstance(e, BadFile) else f"{type(e).__name__}: {e}"


def _constants_worker(code, name, out):
    _restrict_env()
    out.put(("up", None))  # служебный поток очереди — до запрета на новые потоки
    folder = _enter_temp_dir()
    _limit_resources()
    try:
        module = _exec(code, name)
        found = {}
        for key, value in vars(module).items():
            if key.isupper():
                try:
                    found[key] = json.loads(json.dumps(value))  # только данные: словари, списки, строки, числа
                except (TypeError, ValueError):
                    pass
        out.put(("ok", found))
    except BaseException as e:  # noqa: BLE001
        out.put(("err", _error_text(e)))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _compare_worker(code, name, before, after, out):
    _restrict_env()
    out.put(("up", None))
    folder = _enter_temp_dir()
    _limit_resources()
    try:
        compare = _exec(code, name).__dict__.get("COMPARE")
        if not isinstance(compare, dict) or not callable(compare.get("entrypoint")):
            raise BadFile("COMPARE должен быть словарём с entrypoint — функцией compare(before, after)")
        result = compare["entrypoint"](before, after)
        out.put(("ok", result))
    except BaseException as e:  # noqa: BLE001
        out.put(("err", _error_text(e)))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _in_child(target, args: tuple, timeout: float, what: str):
    """Запускает target в отдельном процессе и ждёт ("ok", результат) или ("err", текст)."""
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(target=target, args=(*args, out), daemon=True)
    proc.start()
    try:
        out.get(timeout=60)  # ("up", None): процесс стартовал
        status, payload = out.get(timeout=timeout)
    except queue.Empty:
        raise BadFile(f"{what}: код не закончил работу за {timeout:g} с") from None
    finally:
        proc.kill()
        proc.join()
    if status == "err":
        raise BadFile(f"{what}: {payload}")
    return payload


def load_constants(kind: str, code: str, name: str = "<procedure>", timeout: float = LOAD_TIMEOUT) -> dict:
    """Переменные заглавными буквами из кода процедуры-данных (исполняется в отдельном процессе)."""
    problems = static_problems(kind, code)
    if problems:
        raise BadFile(f"Строка {problems[0]['line']}: {problems[0]['message']}")
    found = _in_child(_constants_worker, (code, name), timeout, "Процедура")
    for var in REQUIRED[kind]:
        if not isinstance(found.get(var), dict):
            raise BadFile(f"Процедура: {var} должен быть словарём")
    return found


def run_compare(code: str, before, after, name: str = "<compare>", timeout: float = COMPARE_TIMEOUT):
    """Пользовательское сравнение: (before, after) -> DataFrame. Исполняется в отдельном процессе."""
    problems = static_problems("compare", code)
    if problems:
        raise BadFile(f"Строка {problems[0]['line']}: {problems[0]['message']}")
    return _in_child(_compare_worker, (code, name, before, after), timeout, "Процедура сравнения")


def write_data_procedure(path: Path, title: str, values: dict) -> None:
    """Файл процедуры-данных в папке запуска: только переменные, без логики — его читает pipeline/procedures.py."""
    lines = [f'"""{title}. Файл собран приложением из выбранной процедуры для этого запуска."""', ""]
    for key, value in values.items():
        lines.append(f"{key} = {pprint.pformat(value, width=110, sort_dicts=False)}")
        lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
