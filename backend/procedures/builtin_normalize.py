"""Встроенная процедура «Приведение ответов»: правила массивов (docs/api.md п. 3, CONTRACTS §5).

Что это. Массивы в ответе СПР сопоставляются между версиями «до» и «после» по ключу, а не по позиции:
иначе вставка элемента в начало даёт лавину ложных различий. Здесь для каждого массива записано,
как сопоставлять его элементы:
    "mode": "key"   — по значениям полей из "key" (поле можно писать через точку: "body.action");
    "mode": "value" — по самому значению элемента (массив скаляров как множество);
    "mode": "index" — по позиции (порядок значим, например вектор модели).

Откуда правила. Таблица «Массивы: девять штук» в ТЗ (ПАКЕТ/ЗАДАНИЕ/docs/ФОРМАТ_ОТВЕТА.md).
Проверено на RUN-20260827-0001: все 9 правил подошли, «нет правила» и «дубль ключа» — 0 ошибок.

Как поменять.
    - На один прогон — в конфигурации: поле `array_rules` (правило целиком, можно добавить новый массив)
      или `array_modes` (только режим). Порядок: этот файл → `array_rules` → `array_modes`.
    - Насовсем (другой формат ответа СПР) — поправить словарь ниже. Код приложения трогать не нужно.

Здесь только данные, логики нет: файл читает pipeline/procedures.py.
"""

ARRAY_RULES = {
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
