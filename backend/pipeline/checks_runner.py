"""Запуск автопроверок по контракту организаторов (docs/api.md п. 10, checks/README.md).

Проверка — файл или строка кода, где есть `CHECK = {"id", "label", "params", "entrypoint"}`;
`entrypoint(mart, params)` возвращает список строк результата.

Код пользователя исполняется в отдельном процессе с таймаутом: зависшая проверка убивается,
остальные продолжают работать. Процесс не получает переменных окружения (там могут быть секреты).
Если проверка не из кода (нет `source`) или у `mart` нет путей к CSV — идём в обычном процессе, без таймаута.
"""

import ast
import builtins
import multiprocessing as mp
import os
import queue
import time
import types
from pathlib import Path

from .csvio import write_csv
from .errors import BadFile

RESULT_COLUMNS = ["LABEL", "SOURCE", "ARGUMENT", "CNT", "TOTAL", "METRIC", "APP_IDS", "RESULT", "CONFIDENCE"]
CHECK_KEYS = ("id", "label", "params", "entrypoint")
DEFAULT_TIMEOUT = 60  # секунд на одну проверку
LOAD_TIMEOUT = 15  # секунд на загрузку кода проверки


# --- загрузка -----------------------------------------------------------------

def _restrict_env() -> None:
    """В дочернем процессе оставляем только самое нужное: секретов сервера код пользователя не увидит."""
    keep = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP")}
    os.environ.clear()
    os.environ.update(keep)


def _exec_check(code: str, name: str) -> dict:
    """Исполняет код и достаёт CHECK. ТОЛЬКО в дочернем процессе (или в тестах): код может зависнуть."""
    module = types.ModuleType("user_check")
    try:
        exec(compile(code, name, "exec"), module.__dict__)
    except SyntaxError as e:
        raise BadFile(f"Синтаксическая ошибка в строке {e.lineno}: {e.msg}") from e
    except Exception as e:
        raise BadFile(f"Код проверки упал при загрузке: {type(e).__name__}: {e}") from e
    check = getattr(module, "CHECK", None)
    if not isinstance(check, dict):
        raise BadFile("В коде нет объекта CHECK (словарь id/label/params/entrypoint)")
    missing = [k for k in CHECK_KEYS if k not in check]
    if missing:
        raise BadFile(f"В CHECK не хватает ключей: {', '.join(missing)}")
    if not callable(check["entrypoint"]):
        raise BadFile("CHECK['entrypoint'] должен быть функцией")
    return check


def _read_code(path_or_code, kind: str) -> tuple[str, str]:
    if kind == "file":
        return Path(path_or_code).read_text(encoding="utf-8"), str(path_or_code)
    if kind == "code":
        return str(path_or_code), "<check>"
    raise ValueError(f"kind должен быть 'file' или 'code', получено {kind!r}")


def _load_worker(code, name, out):
    _restrict_env()
    try:
        check = _exec_check(code, name)
        out.put(("ok", {"id": check["id"], "label": check["label"], "params": check["params"]}))
    except BaseException as e:  # noqa: BLE001
        out.put(("err", str(e) if isinstance(e, BadFile) else f"{type(e).__name__}: {e}"))


def load_check(path_or_code, kind: str = "file", timeout: float = LOAD_TIMEOUT) -> dict:
    """Загружает проверку. kind = "file" (путь к .py) или "code" (текст кода). Возвращает объект CHECK.

    Код НЕ исполняется в главном процессе: сначала статическая проверка (`validate_check_code`), потом загрузка
    в отдельном процессе с таймаутом и без переменных окружения. Поэтому код с `while True` на верхнем уровне
    даёт BadFile, а не вешает сервер. `entrypoint` в возвращённом CHECK исполняет код только при вызове
    (в `run_checks` с настоящим `Mart` это тоже происходит в дочернем процессе).
    В CHECK добавляется `source` = (kind, значение) — по нему проверку грузит дочерний процесс запуска.
    """
    code, name = _read_code(path_or_code, kind)
    problems = validate_check_code(code)
    if problems:
        p = problems[0]
        raise BadFile(f"Строка {p['line']}: {p['message']}")
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(target=_load_worker, args=(code, name, out), daemon=True)
    proc.start()
    try:
        status, payload = out.get(timeout=timeout)
    except queue.Empty:
        raise BadFile(f"Код проверки не загрузился за {timeout:g} с (бесконечный цикл на верхнем уровне?)") from None
    finally:
        proc.kill()
        proc.join()
    if status == "err":
        raise BadFile(payload)

    def entrypoint(mart, params):
        return _exec_check(code, name)["entrypoint"](mart, params)

    return {**payload, "entrypoint": entrypoint, "source": (kind, path_or_code)}


def validate_check_code(code: str) -> list[dict]:
    """Проверка кода без запуска: компилируется ли, есть ли CHECK с нужными ключами и функция проверки.

    Пустой список — всё хорошо; иначе список {"line", "message"}.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"line": e.lineno or 1, "message": f"Синтаксическая ошибка: {e.msg}"}]
    funcs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    known = set(funcs) | set(dir(builtins))  # что можно указать в entrypoint: функции, импорты, присваивания
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            known |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ClassDef):
            known.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            known.add(n.id)
    check_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CHECK" for t in node.targets):
            check_node = node
    if check_node is None:
        return [{"line": 1, "message": "Нет объекта CHECK = {...}"}]
    problems = []
    value = check_node.value
    if isinstance(value, ast.Dict):
        keys = {k.value: v for k, v in zip(value.keys, value.values) if isinstance(k, ast.Constant)}
        for k in CHECK_KEYS:
            if k not in keys:
                problems.append({"line": check_node.lineno, "message": f"В CHECK нет ключа '{k}'"})
        entry = keys.get("entrypoint")
        if isinstance(entry, ast.Name) and entry.id not in known:
            problems.append({"line": entry.lineno, "message": f"Функция '{entry.id}' (entrypoint) не определена в коде"})
        elif entry is not None and not isinstance(entry, (ast.Name, ast.Lambda, ast.Attribute, ast.Call)):
            problems.append({"line": entry.lineno, "message": "entrypoint должен быть функцией"})
    elif "run" not in funcs:
        problems.append({"line": check_node.lineno, "message": "Нет функции run(mart, params)"})
    return problems


# --- запуск ---------------------------------------------------------------------

def _error_row(label: str, text: str) -> dict:
    return {"LABEL": label, "SOURCE": "AFTER", "ARGUMENT": text, "CNT": 0, "TOTAL": 0, "METRIC": 0,
            "APP_IDS": [], "RESULT": "FAIL", "CONFIDENCE": "LOW"}


def _clean_rows(rows, label: str) -> list[dict]:
    """Приводит строки проверки к схеме: все колонки на месте, APP_IDS — список."""
    if not isinstance(rows, (list, tuple)):
        raise TypeError("проверка должна вернуть список строк (dict)")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            raise TypeError("строка результата должна быть dict")
        row = {c: r.get(c, "") for c in RESULT_COLUMNS}
        row["LABEL"] = row["LABEL"] or label
        ids = row["APP_IDS"]
        row["APP_IDS"] = [str(i) for i in ids] if isinstance(ids, (list, tuple, set)) else ([str(ids)] if ids != "" else [])
        out.append(row)
    return out


def _call(mart, check: dict, params: dict) -> list[dict]:
    return _clean_rows(check["entrypoint"](mart, params), check.get("label", check.get("id", "")))


def _worker(comparison_csv, segments_csv, tasks, results):
    """Дочерний процесс: один раз грузит витрину и по очереди выполняет проверки."""
    _restrict_env()
    from .mart import Mart
    mart = Mart(comparison_csv, segments_csv)
    results.put(("ready", None, None))
    while True:
        task = tasks.get()
        if task is None:
            return
        i, (kind, value), params = task
        try:
            code, name = _read_code(value, kind)
            check = _exec_check(code, name)
            results.put(("ok", i, _call(mart, check, params)))
        except BaseException as e:  # noqa: BLE001 — пользовательский код может бросить что угодно
            results.put(("err", i, f"{type(e).__name__}: {e}"))


def _params_for(check: dict, params_override) -> dict:
    return {**(check.get("params") or {}), **((params_override or {}).get(check.get("id")) or {})}


def run_checks(mart, checks: list[dict], params_override: dict | None = None, log=None,
               timeout: float = DEFAULT_TIMEOUT) -> list[dict]:
    """Запускает проверки, склеивает строки. Исключение или таймаут одной проверки не роняют прогон:
    вместо её строк — служебная строка FAIL / CONFIDENCE=LOW с текстом ошибки в ARGUMENT.

    params_override = {check_id: {параметр: значение}} перекрывает CHECK["params"].
    """
    log = log or (lambda level, message: None)
    isolated = getattr(mart, "comparison_csv", None) is not None
    rows: list[dict] = []
    proc = tasks = results = None

    def stop_worker():
        nonlocal proc, tasks, results
        if proc is not None:
            proc.kill()
            proc.join()
        proc = tasks = results = None

    def start_worker():
        nonlocal proc, tasks, results
        ctx = mp.get_context("spawn")
        tasks, results = ctx.Queue(), ctx.Queue()
        proc = ctx.Process(target=_worker, args=(mart.comparison_csv, mart.segments_csv, tasks, results), daemon=True)
        proc.start()
        if results.get(timeout=max(timeout, 120))[0] != "ready":
            raise RuntimeError("процесс проверок не запустился")

    try:
        for i, check in enumerate(checks):
            label = check.get("label", check.get("id", f"check{i}"))
            params = _params_for(check, params_override)
            started = time.time()
            try:
                if isolated and check.get("source"):
                    if proc is None:
                        start_worker()
                    tasks.put((i, check["source"], params))
                    try:
                        status, _, payload = results.get(timeout=timeout)
                    except queue.Empty:
                        stop_worker()
                        raise TimeoutError(f"проверка не уложилась в {timeout:g} с и остановлена") from None
                    if status == "err":
                        raise RuntimeError(payload)
                    result = payload
                else:
                    result = _call(mart, check, params)
            except Exception as e:  # noqa: BLE001
                text = str(e) if isinstance(e, (TimeoutError, RuntimeError)) else f"{type(e).__name__}: {e}"
                log("error", f"Проверка «{label}» не выполнена: {text}")
                rows.append(_error_row(label, text))
                continue
            log("info", f"Проверка «{label}»: {len(result)} строк за {time.time() - started:.1f} с")
            rows.extend(result)
    finally:
        if proc is not None:
            tasks.put(None)
            proc.join(5)
            stop_worker()
    return rows


def write_checks_csv(rows: list[dict], out_csv: Path) -> int:
    """checks.csv: колонки схемы, APP_IDS через `|`. Возвращает число строк."""
    def flat(r):
        out = {c: r.get(c, "") for c in RESULT_COLUMNS}
        ids = out["APP_IDS"]
        out["APP_IDS"] = "|".join(map(str, ids)) if isinstance(ids, (list, tuple, set)) else ids
        return out
    return write_csv(Path(out_csv), RESULT_COLUMNS, (flat(r) for r in rows))
