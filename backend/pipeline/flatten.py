"""Разворот одного JSON-ответа СПР в плоские строки: одна строка = один лист.

Формат строки — CONTRACTS §2.1:
APP_ID, SOURCE, PREFIX, CLASS, SUFFIX, ARRAY_KEY, KEY, PATH, VALUE, ADJUSTED_VALUE.

Как PATH делится на PREFIX / CLASS / SUFFIX / KEY (сегменты — части пути через точку,
«[]» остаётся в имени сегмента):
  - 1 сегмент:   заполнен только KEY;                 a    -> KEY=a
  - 2 сегмента:  PREFIX (первый) и KEY (последний);   a.b  -> PREFIX=a, KEY=b
  - 3+ сегмента: PREFIX — первый, CLASS — второй, KEY — последний,
                 SUFFIX — всё между ними через точку (при 3 сегментах пустой).
        decisionResult.product_trials[].scoring.pd.value
        -> PREFIX=decisionResult, CLASS=product_trials[], SUFFIX=scoring.pd, KEY=value
  KEY никогда не пустой и никогда не дублирует PREFIX/CLASS.

Правила массивов (`array_rules`): {путь_массива_с_[]: {"mode": "key"|"value"|"index", "key": [...]}}.
  - key   — ключ элемента собирается из полей `key` (вложенные через точку, составной — через «:»);
  - value — массив скаляров, ключ = само значение;
  - index — ключ = порядковый номер с нуля.
В PATH вместо индекса стоит «[]», ключи всех массивов на пути идут в ARRAY_KEY через «|».
"""

from decimal import Decimal
from typing import Callable, Iterable, Optional

from .errors import BadFile

COLUMNS = ["APP_ID", "SOURCE", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH", "VALUE", "ADJUSTED_VALUE"]


def format_value(value) -> str:
    """Лист JSON -> строка VALUE (CONTRACTS §2.1): true/false, null, числа без лишних нулей."""
    if value is None:
        return "null"
    if isinstance(value, bool):  # bool раньше int: True — это тоже int
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(Decimal(repr(value)), "f")  # без экспоненты: 1e-05 -> 0.00001
    return str(value)


def split_path(path: str) -> tuple[str, str, str, str]:
    """PATH -> (PREFIX, CLASS, SUFFIX, KEY). Правило — в docstring модуля."""
    parts = path.split(".")
    if len(parts) == 1:
        return "", "", "", parts[0]
    if len(parts) == 2:
        return parts[0], "", "", parts[1]
    return parts[0], parts[1], ".".join(parts[2:-1]), parts[-1]


def _is_ignored(path: str, ignore_paths: Iterable[str]) -> bool:
    """Путь (или его префикс по границе сегмента) в списке игнорируемых. Пути без [] тоже подходят."""
    candidates = (path, path.replace("[]", ""))
    for ign in ignore_paths:
        for cand in candidates:
            if cand == ign or cand.startswith(ign + "."):
                return True
    return False


def _get_by_dotted(element, dotted: str):
    """Достаёт поле по пути через точку (`body.action`). Нет поля -> KeyError."""
    cur = element
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def _is_scalar(value) -> bool:
    return not isinstance(value, (dict, list))


def _key_part(value, arr_path: str) -> str:
    """Кусок ключа элемента: только скаляр, без «:» и «|» (они склеивают ключи и ломают уникальность)."""
    if not _is_scalar(value):
        raise BadFile(f"в ключе массива {arr_path} лежит объект или массив, а нужен скаляр")
    text = format_value(value)
    if ":" in text or "|" in text:
        raise BadFile(f"в ключе массива {arr_path} значение {text!r} содержит «:» или «|»")
    return text


def flatten_response(
    doc: dict,
    app_id: str,
    source: str,
    array_rules: dict,
    ignore_paths: Iterable[str] = (),
    adjust: Optional[Callable[[str, str], str]] = None,
) -> list[dict]:
    """Возвращает строки с ключами COLUMNS. `adjust(path, value_str)` — бакетизация (E4)."""
    ignore_paths = list(ignore_paths)
    rows: list[dict] = []

    def emit(path: str, array_keys: list[str], value) -> None:
        value_str = format_value(value)
        prefix, cls, suffix, key = split_path(path)
        rows.append({
            "APP_ID": app_id,
            "SOURCE": source,
            "PREFIX": prefix,
            "CLASS": cls,
            "SUFFIX": suffix,
            "ARRAY_KEY": "|".join(array_keys),
            "KEY": key,
            "PATH": path,
            "VALUE": value_str,
            "ADJUSTED_VALUE": adjust(path, value_str) if adjust else value_str,
        })

    def walk(node, path: str, array_keys: list[str]) -> None:
        if path and _is_ignored(path, ignore_paths):
            return
        if isinstance(node, dict):
            if not node:
                if path:
                    emit(path, array_keys, "{}")
                return
            for name, child in node.items():
                walk(child, f"{path}.{name}" if path else name, array_keys)
        elif isinstance(node, list):
            walk_array(node, path + "[]", path, array_keys)
        else:
            emit(path, array_keys, node)

    def walk_array(items: list, arr_path: str, plain_path: str, array_keys: list[str]) -> None:
        # Пустой массив — один лист «[]», правило не нужно.
        if not items:
            emit(plain_path, array_keys, "[]")
            return
        rule = array_rules.get(arr_path)
        if rule is None:
            raise BadFile(f"нет правила для массива {arr_path}")
        mode = rule.get("mode")
        key_fields = rule.get("key") or []
        if isinstance(key_fields, str):
            key_fields = [key_fields]
        if mode not in ("key", "value", "index"):
            raise BadFile(f"неизвестный режим массива {arr_path}: {mode!r}")
        if mode == "key" and not key_fields:
            raise BadFile(f"для массива {arr_path} режим key, но не указаны поля ключа")

        seen: set[str] = set()
        for i, element in enumerate(items):
            if mode == "index":
                key = str(i)
            elif mode == "value":
                if not _is_scalar(element):
                    raise BadFile(f"массив {arr_path} в режиме value должен содержать скаляры")
                key = _key_part(element, arr_path)
            else:
                if not isinstance(element, dict):
                    raise BadFile(f"массив {arr_path} в режиме key должен содержать объекты")
                try:
                    key = ":".join(_key_part(_get_by_dotted(element, f), arr_path) for f in key_fields)
                except KeyError as e:
                    raise BadFile(f"в элементе массива {arr_path} нет поля ключа {e.args[0]}") from None
            if key in seen:
                raise BadFile(f"дубль ключа {key!r} в массиве {arr_path}")
            seen.add(key)

            keys = array_keys + [key]
            if isinstance(element, list):
                walk_array(element, arr_path + "[]", arr_path, keys)
            elif isinstance(element, dict):
                if not element:
                    emit(arr_path, keys, "{}")
                else:
                    for name, child in element.items():
                        walk(child, f"{arr_path}.{name}", keys)
            elif not _is_ignored(arr_path, ignore_paths):
                emit(arr_path, keys, element)

    walk(doc, "", [])
    return rows
