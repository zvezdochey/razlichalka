"""Правила массивов датасета: как сопоставлять элементы между версиями «до» и «после».

Массивы сопоставляются по ключу, а не по позиции: иначе вставка элемента в начало
даёт лавину ложных различий. Режимы: key / value / index (см. docstring flatten.py).

Правила взяты из таблицы «Массивы: девять штук» в ТЗ (ФОРМАТ_ОТВЕТА.md).
Пользователь через `parse_cfg["array_modes"]` может поменять только РЕЖИМ, ключи зашиты здесь.

Проверено на настоящем датасете RUN-20260827-0001 (python -m pipeline.tools.check_dataset <срез>):
все 9 правил из ТЗ подошли без правок — «нет правила» и «дубль ключа» дали 0 ошибок.
  BEFORE_MASTER: 2002 файла, 291 047 строк, листьев на заявку 132 / 139 / 178 (min / median / max), 54 разных PATH.
  AFTER_BETA:    2002 файла, 292 033 строки, листьев на заявку 132 / 139 / 194, 56 разных PATH.
Повторов (APP_ID, PATH, ARRAY_KEY) нет. В AFTER на 2 PATH больше — это новые атрибуты версии BETA.
"""

DEFAULT_ARRAY_RULES: dict[str, dict] = {
    "decisionResult.available_offers[]": {"mode": "key", "key": ["product_id", "type"]},
    "decisionResult.product_trials[]": {"mode": "key", "key": ["product_id"]},
    "decisionResult.product_trials[].rules[]": {"mode": "key", "key": ["name"]},
    "decisionResult.product_trials[].scoring.scoreModels[]": {"mode": "key", "key": ["modelName"]},
    "decisionResult.scoring[]": {"mode": "key", "key": ["modelName"]},
    "decisionResult.scoring[].value[]": {"mode": "index"},
    "ext_data[]": {"mode": "key", "key": ["body.action"]},
    "product_catalog[]": {"mode": "key", "key": ["mfo_id", "product_id"]},
    "tariff_matrix[]": {"mode": "key", "key": ["mfo_id", "product_id"]},
}


def merge_array_rules(defaults: dict, array_modes: dict) -> dict:
    """Копия правил, где режим переопределён по путям из `array_modes`. Ключи (`key`) не трогаем."""
    merged = {path: dict(rule) for path, rule in defaults.items()}
    for path, mode in (array_modes or {}).items():
        if path in merged:
            merged[path]["mode"] = mode
        else:
            merged[path] = {"mode": mode}
    return merged
