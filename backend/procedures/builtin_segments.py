"""Встроенная процедура «Разрезы»: откуда в ответе СПР брать поля для segments.csv (CONTRACTS §2.3).

Что это. Для каждого поля разреза — путь в JSON-ответе. Путь пишется через точку, массив — с `[]`:
    "decisionResult.decision"                       — одно значение;
    "decisionResult.product_trials[].product_id"    — поле каждого элемента массива.

Поля продукта (PARTNER_TYPE, ROUTING_METHOD, PD_MODEL, CUTOFF, REJECT_REASON) читаются у «того же продукта»:
первого в выдаче (TOP_OFFER с наименьшим OFFER_RANK), а если выдачи нет — у продукта с наименьшим id из PRODUCTS.
Поэтому их пути начинаются с того же массива, что и PRODUCTS (или лежат вне массивов — тогда читаются
из ответа целиком). Путь продукта в другом массиве — ошибка этапа, а не «первый попавшийся элемент». Само правило выбора — в pipeline/segments.py,
пути оно берёт отсюда.

Откуда пути. Формат ответа из ТЗ (ПАКЕТ/ЗАДАНИЕ/docs/ФОРМАТ_ОТВЕТА.md), проверено на RUN-20260827-0001.

Как поменять. Если в другой версии СПР поле переехало — поправь путь ниже. Нет поля в ответе — ячейка пустая.
Пустая строка вместо пути — колонка всегда пустая. Код приложения трогать не нужно.

INPUT_PREFIXES — что в ответе СПР пришло на вход, а не посчитано логикой (колонка CHANGE_SOURCE, E10).
Если у заявки есть различие (DIFF_FLAG=1) в пути, который начинается с одного из этих префиксов, — входные
данные другие, и смена решения могла прийти снаружи (CHANGE_SOURCE=data). Иначе различия только в том, что
посчитала логика (CHANGE_SOURCE=logic). Префикс — начало пути до точки: "ext_data" подходит к
"ext_data[].body.params.data"; `[]` писать можно, но не обязательно. Технические поля из ignore_paths
сюда не попадут: их нет в витрине сравнения.
    appData   — данные заявки (технические поля request_id и createDateTime исключаются через ignore_paths);
    ext_data  — сырые ответы внешних источников (score_okb, score_equ).
characteristics — уже «этап 1» (готовые скоры, их заполняет СПР), поэтому это логика, не вход:
если ext_data тот же, а characteristics другие — значит СПР по-другому разложила те же ответы.
Справочники product_catalog и tariff_matrix — настройка самой СПР, тоже не вход.

Здесь только данные, логики нет: файл читает pipeline/procedures.py.
"""

FIELD_MAP = {
    "DECISION": "decisionResult.decision",
    "PRODUCTS": "decisionResult.product_trials[].product_id",
    "TOP_OFFER": "decisionResult.available_offers[].product_id",
    "OFFER_RANK": "decisionResult.available_offers[].rank",
    "PARTNER_TYPE": "decisionResult.product_trials[].partner_type",
    "ROUTING_METHOD": "decisionResult.product_trials[].routing_method",
    "PD_MODEL": "decisionResult.product_trials[].scoring.pd.modelName",
    "CUTOFF": "decisionResult.product_trials[].cutOff.name",
    "REJECT_REASON": "decisionResult.product_trials[].rejectReason",
    "SCORE_OKB": "characteristics.score_okb",
}

INPUT_PREFIXES = ["appData", "ext_data"]
