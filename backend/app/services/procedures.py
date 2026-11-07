"""Процедуры и проверки (docs/api.md п. 3): встроенные из файлов + пользовательские в хранилище.

Встроенные не лежат в хранилище — их список собирается из папок `backend/procedures/` и `CHECKS_DIR`.
Пользовательские (`inline` — код в теле, `file` — файл в этих же папках) хранятся через `store`.
"""
import ast
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import settings, store
from app.errors import ApiError
from pipeline.checks_runner import forbidden_code_problems, validate_check_code

KIND = "procedures"
KINDS = ("normalize", "aggregate", "check")

# Встроенные процедуры этапов: id -> (вид, название, файл в procedures/)
_STAGE_BUILTINS = {
    "builtin_normalize": ("normalize", "Правила разбора ответов", "builtin_normalize.py"),
    "builtin_aggregate": ("aggregate", "Карта полей для разрезов", "builtin_segments.py"),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- пути: наружу только файлы из двух папок ------------------------------------

def _roots() -> dict[str, Path]:
    return {"procedures": Path(settings.PROCEDURES_DIR), "checks": Path(settings.CHECKS_DIR)}


def resolve_path(path: str) -> Path:
    """`procedures/x.py` или `checks/x.py` -> настоящий файл. Выход за папку (`..`, абсолютный путь) — bad_code."""
    head, _, rest = (path or "").replace("\\", "/").partition("/")
    root = _roots().get(head)
    if root is None or not rest or not rest.endswith(".py"):
        raise ApiError("bad_code", "Путь к файлу: procedures/<имя>.py или checks/<имя>.py")
    file = (root / rest).resolve()
    if root.resolve() not in file.parents:
        raise ApiError("bad_code", "Файл должен лежать внутри папки procedures/ или checks/")
    if not file.is_file():
        raise ApiError("bad_code", f"Файл «{path}» не найден на сервере")
    return file


def _check_header(file: Path) -> tuple[str, str] | None:
    """(id, label) из `CHECK = {...}` без исполнения файла."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CHECK" for t in node.targets) \
                and isinstance(node.value, ast.Dict):
            fields = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)
                      if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
            if "id" in fields:
                return str(fields["id"]), str(fields.get("label") or fields["id"])
    return None


# --- встроенные ----------------------------------------------------------------

def builtins() -> list[dict]:
    items = [
        {"id": pid, "kind": kind, "name": name, "source": "file", "path": f"procedures/{file}",
         "builtin": True, "updated_at": None}
        for pid, (kind, name, file) in _STAGE_BUILTINS.items()
    ]
    folder = Path(settings.CHECKS_DIR)
    for file in sorted(folder.glob("check_*.py")) if folder.is_dir() else []:
        header = _check_header(file)
        if header:
            items.append({"id": f"builtin_{header[0]}", "kind": "check", "name": header[1], "source": "file",
                          "path": f"checks/{file.name}", "builtin": True, "updated_at": None})
    return items


# --- пользовательские ----------------------------------------------------------

def _public(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k not in ("owner", "code")}


def _own(proc_id: str, user: str) -> dict:
    obj = store.load(KIND, proc_id)
    if obj is None or obj.get("owner") != user:
        raise ApiError("not_found", "Процедура не найдена")
    return obj


def find(proc_id: str, user: str) -> dict:
    """Процедура по id (встроенная или своя) вместе с `code` для inline."""
    for item in builtins():
        if item["id"] == proc_id:
            return item
    return _own(proc_id, user)


def list_all(kind: str | None, user: str) -> list[dict]:
    mine = [_public(p) for p in store.list(KIND) if p.get("owner") == user]
    mine.sort(key=lambda p: p["updated_at"], reverse=True)
    items = builtins() + mine
    return [p for p in items if kind is None or p["kind"] == kind]


def validate(kind: str, source: str, code: str | None, path: str | None) -> list[dict]:
    """Список {line, message}; пустой — код годится. Исполнять код здесь не нужно: проверка статическая."""
    if kind not in KINDS:
        return [{"line": 1, "message": f"Неизвестный вид процедуры «{kind}», нужен normalize, aggregate или check"}]
    if source == "file":
        try:
            text = resolve_path(path or "").read_text(encoding="utf-8")
        except ApiError as exc:
            return [{"line": 1, "message": exc.message}]
    elif source == "inline":
        text = code or ""
        if not text.strip():
            return [{"line": 1, "message": "Код пустой"}]
    else:
        return [{"line": 1, "message": "source — inline или file"}]
    if kind == "check":
        return validate_check_code(text)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [{"line": exc.lineno or 1, "message": f"Синтаксическая ошибка: {exc.msg}"}]
    return forbidden_code_problems(tree)


def _checked_fields(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise ApiError("bad_code", "Название процедуры не может быть пустым")
    errors = validate(body["kind"], body["source"], body.get("code"), body.get("path"))
    if errors:
        e = errors[0]
        raise ApiError("bad_code", f"Строка {e['line']}: {e['message']}")
    fields = {"kind": body["kind"], "name": name, "source": body["source"]}
    body_key = "code" if body["source"] == "inline" else "path"
    fields[body_key] = body[body_key]
    return fields


def create(body: dict, user: str) -> dict:
    obj = {"id": "p_" + uuid.uuid4().hex[:6], "owner": user, "builtin": False, "updated_at": _now(),
           **_checked_fields(body)}
    store.save(KIND, obj["id"], obj)
    return _public(obj)


def update(proc_id: str, body: dict, user: str) -> dict:
    if any(b["id"] == proc_id for b in builtins()):
        raise ApiError("conflict", "Встроенную процедуру нельзя изменить")
    obj = {**_own(proc_id, user), "updated_at": _now(), **_checked_fields(body)}
    obj.pop("code" if obj["source"] == "file" else "path", None)
    store.save(KIND, proc_id, obj)
    return _public(obj)


def delete(proc_id: str, user: str) -> None:
    if any(b["id"] == proc_id for b in builtins()):
        raise ApiError("conflict", "Встроенную процедуру нельзя удалить")
    _own(proc_id, user)
    store.delete(KIND, proc_id)


def with_code(proc: dict) -> dict:
    """Объект процедуры + `code`: текст файла (только из procedures/ и checks/) или inline-код."""
    if proc["source"] == "file":
        return {**_public(proc), "code": resolve_path(proc["path"]).read_text(encoding="utf-8")}
    return {**_public(proc), "code": proc["code"]}


def check_source(proc: dict) -> tuple[str, str]:
    """Что отдать `load_check`: ("file", путь) или ("code", текст)."""
    if proc["source"] == "file":
        return "file", str(resolve_path(proc["path"]))
    return "code", proc["code"]
