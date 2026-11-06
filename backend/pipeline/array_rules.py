"""Правила массивов: как сопоставлять элементы между версиями «до» и «после».

Сами правила — данные процедуры `backend/procedures/builtin_normalize.py` (ARRAY_RULES), а не код:
на другом формате ответа СПР правят файл процедуры или конфигурацию, а не этот модуль.
Режимы: key / value / index (см. docstring flatten.py).

Порядок перекрытия (CONTRACTS §5):
    правила процедуры → `array_rules` конфигурации (правило целиком) → `array_modes` конфигурации (только режим).

Проверено на настоящем датасете RUN-20260827-0001 (python -m pipeline.tools.check_dataset <срез>):
все 9 правил из ТЗ подошли без правок — «нет правила» и «дубль ключа» дали 0 ошибок.
  BEFORE_MASTER: 2002 файла, 291 047 строк, листьев на заявку 132 / 139 / 178 (min / median / max), 54 разных PATH.
  AFTER_BETA:    2002 файла, 292 033 строки, листьев на заявку 132 / 139 / 194, 56 разных PATH.
Повторов (APP_ID, PATH, ARRAY_KEY) нет. В AFTER на 2 PATH больше — это новые атрибуты версии BETA.
"""

from .procedures import load_builtin

BUILTIN = "builtin_normalize"


def default_array_rules() -> dict:
    """Правила встроенной процедуры «Приведение ответов» (свежая копия при каждом вызове)."""
    return {path: dict(rule) for path, rule in load_builtin(BUILTIN).items()}


def _rule_path(path: str, rules: dict) -> str:
    """Путь массива можно писать и без последних `[]`: `a.scoring[].value` — это правило `a.scoring[].value[]`.

    (так путь записан в примере конфига в docs/api.md). Новый массив без `[]` тоже приводим к виду с `[]`.
    """
    if path in rules or path.endswith("[]"):
        return path
    return path + "[]"


def merge_array_rules(defaults: dict, array_modes: dict, array_rules: dict | None = None) -> dict:
    """Копия правил `defaults`, перекрытая конфигурацией.

    `array_rules` — {путь: {"mode": ..., "key": [...]}} — заменяет правило целиком (можно добавить новый массив);
    `array_modes` — {путь: режим} — меняет только режим, ключ (`key`) остаётся.
    """
    merged = {path: dict(rule) for path, rule in defaults.items()}
    for path, rule in (array_rules or {}).items():
        merged[_rule_path(path, merged)] = dict(rule)
    for path, mode in (array_modes or {}).items():
        path = _rule_path(path, merged)
        merged.setdefault(path, {})["mode"] = mode
    return merged
