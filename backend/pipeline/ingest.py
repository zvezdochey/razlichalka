"""Приём файлов заявок в разных форматах: JSON, XML, CSV, ZIP -> один вид (словарь-ответ СПР).

Дальше расчёту всё равно, из какого формата пришла заявка: нормализация читает только JSON-дерево.
Формат каждого входа описан в docs/api.md п. 2.2.

    split_apps("a.xml", b"<response>...", array_paths) -> [{"appData": {...}, ...}]
    iter_files("срез.zip", data) -> (имя, расширение, байты) по файлам из архива
"""

import csv
import io
import json
import math
import re
import zipfile
from collections.abc import Iterator
from xml.etree import ElementTree

from .array_rules import DEFAULT_ID_PATH, get_by_path
from .errors import BadFile

EXTENSIONS = (".json", ".xml", ".csv")
MAX_FILE = 20 * 1024 * 1024       # один файл заявки (в архиве — после распаковки)
MAX_UNPACKED = 150 * 1024 * 1024  # все распакованные файлы одного запроса (разобранные заявки в памяти тяжелее в разы)
MAX_FILES_IN_ZIP = 100_000

_APP_ID = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_INT = re.compile(r"-?(0|[1-9]\d{0,17})")
_FLOAT = re.compile(r"-?(0|[1-9]\d{0,30})(\.\d{1,30})?([eE][+-]?\d{1,4})?")
csv.field_size_limit(MAX_FILE)  # по умолчанию поле CSV ограничено 128 КБ

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_PATH = re.compile(r"[^.\[\]]+(?:\.[^.\[\]]+|\[\d+\])*")


def ext_of(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot != -1 else ""


# ─── Архивы ──────────────────────────────────────────────────────────────────

def iter_files(name: str, data: bytes, budget: list[int] | None = None) -> Iterator[tuple[str, str, bytes]]:
    """Файлы загрузки: обычный файл отдаём как есть, архив .zip — по файлам внутри.

    `budget` — [сколько байт ещё можно распаковать за запрос]: общий счётчик от защиты от «zip-бомбы».
    В архиве пропускаем папки, мусор macOS, manifest.json организаторов и файлы других форматов.
    """
    ext = ext_of(name)
    if ext != ".zip":
        yield name, ext, data
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BadFile(f"архив {name} не открыть: это не zip или он повреждён") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES_IN_ZIP:
            raise BadFile(f"в архиве {name} больше {MAX_FILES_IN_ZIP} файлов")
        for info in infos:
            base = info.filename.rsplit("/", 1)[-1]
            if info.is_dir() or info.filename.startswith("__MACOSX/") or base.startswith("."):
                continue
            if base == "manifest.json" or ext_of(base) not in EXTENSIONS:
                continue
            label = f"{name}/{info.filename}"
            if info.flag_bits & 0x1:
                raise BadFile(f"в архиве {name} файл {info.filename} под паролем")
            if info.file_size > MAX_FILE:
                raise BadFile(f"файл {label} больше {MAX_FILE // 1024 // 1024} МБ")
            if budget is not None:
                budget[0] -= info.file_size
                if budget[0] < 0:
                    raise BadFile(f"после распаковки данных слишком много (лимит запроса — {MAX_UNPACKED // 1024 // 1024} МБ)")
            try:
                content = zf.read(info)
            except (zipfile.BadZipFile, RuntimeError, OSError) as e:
                raise BadFile(f"файл {label} из архива не прочитать: {e}") from None
            yield label, ext_of(base), content


# ─── Общее ───────────────────────────────────────────────────────────────────

def split_apps(name: str, ext: str, data: bytes, array_paths: set[str], id_field: str = DEFAULT_ID_PATH) -> list[dict]:
    """Один файл -> список заявок (обычно одна). У каждой заявки уже есть id по пути `id_field` (ID_PATH процедуры)."""
    if len(data) > MAX_FILE:
        raise BadFile(f"файл {name} больше {MAX_FILE // 1024 // 1024} МБ")
    if ext in EXTENSIONS:
        try:
            docs = {".json": lambda: _json_docs(name, data), ".xml": lambda: [_xml_doc(name, data, array_paths)],
                    ".csv": lambda: _csv_docs(name, data, id_field)}[ext]()
        except (RecursionError, ValueError, csv.Error) as e:  # вложенность, огромные числа, слишком длинные поля
            raise BadFile(f"файл {name} не разобрать: {type(e).__name__} (слишком глубокая вложенность или странные значения)") from None
    else:
        raise BadFile(f"файл {name}: формат {ext or 'без расширения'} не поддерживается (нужны .json, .xml, .csv, .zip)")
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for doc in docs:
        _ensure_app_id(name, doc, stem if len(docs) == 1 else None, id_field)
    return docs


def _ensure_app_id(name: str, doc: dict, stem: str | None, id_field: str = DEFAULT_ID_PATH) -> None:
    """Приводит id заявки (путь `id_field` — ID_PATH процедуры приведения) к строке.

    Нет id — берём имя файла (если заявка в файле одна).
    """
    *parents, leaf = id_field.split(".")
    holder = doc
    for i, part in enumerate(parents):
        child = holder.get(part)
        if child is None:
            child = holder[part] = {}
        if not isinstance(child, dict):
            raise BadFile(f"файл {name}: {'.'.join(parents[:i + 1])} должен быть объектом")
        holder = child
    app_id = holder.get(leaf)
    if app_id is None or app_id == "":
        if stem is None:
            raise BadFile(f"файл {name}: у заявки нет {id_field}")
        app_id = stem
    if isinstance(app_id, (dict, list, bool)):
        raise BadFile(f"файл {name}: {id_field} должен быть строкой или числом")
    app_id = str(app_id)
    if not _APP_ID.fullmatch(app_id) or not app_id.strip("."):
        raise BadFile(f"файл {name}: недопустимый id заявки {app_id!r} (буквы, цифры, _ - . и не длиннее 100 знаков)")
    holder[leaf] = app_id


def _text(name: str, data: bytes) -> str:
    """Текст файла: utf-8 (с BOM или без), для CSV из русского Excel — cp1251."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1251")
        except UnicodeDecodeError:
            raise BadFile(f"файл {name}: не удалось определить кодировку (нужна UTF-8)") from None


def typed(text: str):
    """Строка из XML/CSV -> значение JSON: число, true/false, пустое -> None. Остальное остаётся строкой."""
    value = text.strip()
    if value == "":
        return None
    if value in ("true", "false"):
        return value == "true"
    if _INT.fullmatch(value):
        return int(value)
    if _FLOAT.fullmatch(value):
        number = float(value)
        if not math.isfinite(number):
            raise BadFile(f"число {value[:30]!r} слишком большое")
        return number
    return value


# ─── JSON ────────────────────────────────────────────────────────────────────

def _no_constants(name: str):
    raise ValueError(f"{name} не допускается в JSON")


def _json_docs(name: str, data: bytes) -> list[dict]:
    try:
        parsed = json.loads(_text(name, data), parse_constant=_no_constants)
    except ValueError as e:
        raise BadFile(f"файл {name} не разобрать как JSON: {e}") from None
    items = parsed if isinstance(parsed, list) else [parsed]
    if not items or not all(isinstance(i, dict) for i in items):
        raise BadFile(f"файл {name}: ожидался JSON-объект заявки или список таких объектов")
    return items


# ─── XML ─────────────────────────────────────────────────────────────────────

def _xml_doc(name: str, data: bytes, array_paths: set[str]) -> dict:
    if b"\x00" in data or data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise BadFile(f"файл {name}: XML должен быть в UTF-8 или однобайтовой кодировке (не UTF-16/32)")
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise BadFile(f"файл {name}: DOCTYPE и сущности в XML запрещены")
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise BadFile(f"файл {name} не разобрать как XML: {e}") from None
    doc = _xml_children(root, "", array_paths)
    if not isinstance(doc, dict) or not doc:
        raise BadFile(f"файл {name}: в XML нет данных заявки")
    return doc


def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]  # без пространства имён


def _xml_value(el, path: str, array_paths: set[str]):
    """Элемент -> значение. Есть вложенные теги или атрибуты — объект, иначе скаляр."""
    if len(el) or el.attrib:
        node = _xml_children(el, path, array_paths)
        text = (el.text or "").strip()
        if text and not len(el):
            node["value"] = typed(text)  # <x a="1">текст</x> -> {"a": 1, "value": "текст"}
        return node
    return typed(el.text or "")


def _xml_children(el, path: str, array_paths: set[str]) -> dict:
    node = {_tag_attr(k): typed(v) for k, v in el.attrib.items()}
    groups: dict[str, list] = {}
    for child in el:
        groups.setdefault(_tag(child), []).append(child)
    for tag, items in groups.items():
        base = f"{path}.{tag}" if path else tag
        is_array = len(items) > 1 or f"{base}[]" in array_paths
        if is_array:
            only = items[0]
            empty = len(items) == 1 and not len(only) and not only.attrib and (only.text or "").strip() == ""
            # <available_offers/> — пустой массив, а не массив из одного null
            node[tag] = [] if empty else [_xml_value(i, f"{base}[]", array_paths) for i in items]
        else:
            node[tag] = _xml_value(items[0], base, array_paths)
    return node


def _tag_attr(key: str) -> str:
    return key.rsplit("}", 1)[-1]


# ─── CSV ─────────────────────────────────────────────────────────────────────

_PATH_ALIASES = ("path", "путь")
_VALUE_ALIASES = ("value", "значение")
_ID_ALIASES = ("application_id", "app_id", "заявка")


def _csv_docs(name: str, data: bytes, id_field: str = DEFAULT_ID_PATH) -> list[dict]:
    text = _text(name, data)
    first = text.lstrip().split("\n", 1)[0]
    delimiter = max(";,\t", key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise BadFile(f"файл {name}: пустой CSV") from None

    def column(aliases: tuple[str, ...]) -> int | None:
        return next((header.index(a) for a in aliases if a in header), None)

    path_col, value_col, id_col = column(_PATH_ALIASES), column(_VALUE_ALIASES), column(_ID_ALIASES)
    if path_col is None or value_col is None:
        raise BadFile(f"файл {name}: в CSV нужны колонки path и value (есть: {', '.join(header)})")

    docs: dict[str, dict] = {}
    for line, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) <= max(path_col, value_col, id_col or 0):
            raise BadFile(f"файл {name}, строка {line}: не хватает колонок")
        key = row[id_col].strip() if id_col is not None else ""
        if id_col is not None and not key:
            raise BadFile(f"файл {name}, строка {line}: пустой application_id")
        raw = row[value_col].strip()
        value = [] if raw == "[]" else {} if raw == "{}" else typed(raw)
        try:
            _put(docs.setdefault(key, {}), row[path_col].strip(), value)
        except BadFile as e:
            raise BadFile(f"файл {name}, строка {line}: {e.message}") from None
    if not docs:
        raise BadFile(f"файл {name}: в CSV нет строк с данными")
    for key, doc in docs.items():
        if key and get_by_path(doc, id_field) is None:  # id из колонки попадает в сам ответ, как в JSON
            _put(doc, id_field, key)
    return list(docs.values())


def _put(root: dict, path: str, value) -> None:
    """Кладёт значение по пути вида `a.b[0].c` в дерево, создавая объекты и списки."""
    if not _PATH.fullmatch(path):
        raise BadFile(f"путь {path!r} записан неверно (ожидается вид a.b[0].c)")
    tokens = [(m.group(1), m.group(2)) for m in _TOKEN.finditer(path)]
    node: dict | list = root
    for i, (key, index) in enumerate(tokens):
        last = i == len(tokens) - 1
        nxt = None if last else tokens[i + 1]
        make = (lambda: value) if last else (lambda: [] if nxt[1] is not None else {})
        if key is not None:
            if not isinstance(node, dict):
                raise BadFile(f"путь {path!r}: после индекса ожидался [номер]")
            if last:
                if key in node:
                    raise BadFile(f"путь {path!r} встречается дважды")
                node[key] = value
            else:
                node = _child(node, key, make(), path)
        else:
            if not isinstance(node, list):
                raise BadFile(f"путь {path!r}: индекс [{index}] у не-массива")
            n = int(index)
            if n > len(node):  # дыры не нужны, а индекс в миллион раздул бы память
                raise BadFile(f"путь {path!r}: индексы идут по порядку, перед [{n}] нет [{len(node)}]")
            if n == len(node):
                node.append(None)
            if last:
                if node[n] is not None:
                    raise BadFile(f"путь {path!r} встречается дважды")
                node[n] = value
            else:
                if node[n] is None:
                    node[n] = make()
                node = node[n]


def _child(node: dict, key: str, fresh, path: str):
    if key not in node:
        node[key] = fresh
        return fresh
    existing = node[key]
    if type(existing) is not type(fresh):
        raise BadFile(f"путь {path!r}: поле {key} уже занято значением другого вида")
    return existing
