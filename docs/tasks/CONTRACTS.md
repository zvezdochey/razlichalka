# Внутренние договорённости бэка (Семён ↔ Егор)

`docs/api.md` — договор между бэком и фронтом. Этот файл — договор **внутри бэка**: между
`backend/pipeline/` (Егор) и `backend/app/` (Семён). Хочешь поменять — сначала поправь здесь и скажи второму.

## 1. Кто что делает

```
backend/
  app/        ← Семён: FastAPI, ручки, запуски, хранение, отчёт
  pipeline/   ← Егор: чистые Python-функции «файлы → CSV», без FastAPI и без знания про HTTP
  tests/
    pipeline/ ← тесты Егора
    api/      ← тесты Семёна
  requirements.txt   ← создаёт Семён (S1)
```

`pipeline` не импортирует `app`. `app` вызывает `pipeline` (только функции из раздела 4).

## 2. Единый формат обмена — CSV

Все промежуточные результаты — CSV как в `ПАКЕТ/ЗАДАНИЕ/example/`: разделитель `;`, кодировка `utf-8-sig`
(UTF-8 с BOM), первая строка — заголовок, пустое значение — пустая ячейка. Читать/писать — через
`pipeline/csvio.py` (задача E3), руками `open()` не писать.

### 2.1. `normalized_BEFORE.csv`, `normalized_AFTER.csv` — результат приведения

Одна строка = один лист JSON-ответа одной заявки.

`APP_ID;SOURCE;PREFIX;CLASS;SUFFIX;ARRAY_KEY;KEY;PATH;VALUE;ADJUSTED_VALUE`

- `SOURCE` — `BEFORE` или `AFTER`.
- `PATH` — путь листа через точку, **вместо индекса массива стоит `[]`**:
  `decisionResult.product_trials[].scoring.pd.value`.
- `ARRAY_KEY` — ключи всех массивов на пути, слева направо, через `|`: `15210|AGELOW@21`.
  Нет массивов на пути — пусто.
- `PREFIX` — первый сегмент пути, `CLASS` — второй, `KEY` — последний, `SUFFIX` — всё, что между ними (через точку).
  Если сегментов мало — лишние поля пустые (правило Егор фиксирует в E1 и пишет в docstring).
- `VALUE` — всегда строка. Числа без лишних нулей (`0.694`, `20`), `true`/`false` в нижнем регистре,
  JSON `null` → строка `null`, пустой массив → `[]`, пустой объект → `{}`.
  **Пустая ячейка `VALUE` в normalized не бывает** (пустая строка из JSON `""` → тоже пустая ячейка, но это редкость).
- `ADJUSTED_VALUE` — после бакетизации (E4); для строк и нечисел совпадает с `VALUE`.

Ключ строки: (`APP_ID`, `PATH`, `ARRAY_KEY`) — уникален. Дубли = ошибка ключа массива.

### 2.2. `comparison.csv` — витрина сравнения

Ровно по `ПАКЕТ/ЗАДАНИЕ/docs/СХЕМА_ВИТРИНЫ.md`, раздел 1:

`APP_ID;PREFIX;CLASS;SUFFIX;ARRAY_KEY;KEY;PATH;VALUE_BEFORE;VALUE_AFTER;ADJUSTED_BEFORE;ADJUSTED_AFTER;DIFF_FLAG;CHANGE_TYPE`

- Атрибута нет в срезе → `VALUE_*` и `ADJUSTED_*` этой стороны **пустые**. Фронту бэк (Семён) отдаёт `null`.
- `DIFF_FLAG` считается по `VALUE`, не по `ADJUSTED`.
- `CHANGE_TYPE` — `SAME` / `VALUE_CHANGED` / `ATTRIBUTE_NEW` / `ATTRIBUTE_LOST`.

### 2.3. `segments.csv` — слой разрезов (одна строка на заявку)

Поля — раздел 2 `СХЕМА_ВИТРИНЫ.md`:

`APP_ID;DECISION_BEFORE;DECISION_AFTER;DECISION_CHANGED;PRODUCTS;TOP_OFFER_BEFORE;TOP_OFFER_AFTER;PARTNER_TYPE;ROUTING_METHOD;PD_MODEL_BEFORE;PD_MODEL_AFTER;CUTOFF_BEFORE;CUTOFF_AFTER;REJECT_REASON_BEFORE;REJECT_REASON_AFTER;SCORE_OKB_BEFORE;SCORE_OKB_AFTER;CHANGE_SOURCE`

`DECISION_*` — как в данных (`APPROVE`/`REJECT`), `DECISION_CHANGED` — `0`/`1`. Список `PRODUCTS` — id через `|`.
`CHANGE_SOURCE` (E10) — `logic` / `data` / `none` (словарь «Откуда смена» в api.md), у всех заявок. Считается по
`comparison.csv`: есть `DIFF_FLAG=1` в пути с префиксом из `INPUT_PREFIXES` (`builtin_segments.py`) → `data`,
иначе есть различия → `logic`, различий нет → `none`. Без витрины (`comparison_csv=None`) колонка пустая.

### 2.4. `apps.csv` — таблица заявок (то, что отдаёт `GET /api/runs/{id}/apps`, до фильтров)

`app_id;decision_before;decision_after;decision_change;attributes_changed;pd_model_before;pd_model_after;cutoff_before;cutoff_after;reject_reason_before;reject_reason_after;change_source`

Имена колонок = имена полей из `docs/api.md` п. 7.4. `decision_*` и `decision_change` — словари из api.md
(`approve`/`reject`/`other`, `same`/`approve_to_reject`/…). `attributes_changed` — число строк `DIFF_FLAG=1`. `change_source` — `CHANGE_SOURCE` из segments.csv как есть.

### 2.5. `summary.json` — ответ `GET /api/runs/{id}/summary` целиком, формат ровно как в `docs/api.md` п. 7.1.

## 3. Где лежат файлы

Переменные окружения (читает **только** `app/settings.py`, `pipeline` получает пути аргументами):

| Переменная | По умолчанию локально | В Docker | Что |
|---|---|---|---|
| `DATASETS_DIR` | `ПАКЕТ/ЗАДАНИЕ/data` | `/data` | папка с датасетами (`<DATASETS_DIR>/RUN-20260827-0001/manifest.json`) |
| `DATA_DIR` | `backend/var` | `/var/razlichalka` | то, что пишет бэк (`backend/var/` в `.gitignore`) |

```
$DATA_DIR/
  configs/<config_id>.json          # S3
  runs/<run_id>/
    run.json                        # S4: статус, этапы, логи
    normalized_BEFORE.csv           # E3
    normalized_AFTER.csv            # E3
    comparison.csv                  # E5
    segments.csv                    # E6
    apps.csv, summary.json          # E7
```

## 4. Функции pipeline, которые вызывает `app`

Все пути — `pathlib.Path`. `on_progress(n)` — «обработано файлов с начала этой функции».
`log(level, message)` — `level` из `"info" | "warn" | "error"`.
`is_cancelled()` — функция, которая вернёт `True`, если пользователь нажал «Стоп»; в цикле по файлам проверять.

```python
# pipeline/normalize.py (E3)
def normalize_dataset(dataset_dir: Path, source: str, out_csv: Path, parse_cfg: dict,
                      on_progress=None, log=None, is_cancelled=None) -> int:
    """source = "BEFORE" | "AFTER". Возвращает число записанных строк."""

# pipeline/compare.py (E5)
def compare_csv(before_csv: Path, after_csv: Path, out_csv: Path, log=None) -> int: ...

# pipeline/segments.py (E6)
def build_segments(dataset_dir: Path, out_csv: Path, *, field_map: dict | None = None, procedures_dir=None,
                   comparison_csv: Path | None = None,
                   on_progress=None, log=None, is_cancelled=None) -> int: ...
# всё после out_csv — только по имени (keyword-only)
# field_map — пути, которые заменяют пути встроенной карты полей (backend/procedures/builtin_segments.py);
# None — встроенная карта. Читать одно поле по той же карте: read_field(doc, name, fmap=None) из pipeline/segments.py
# comparison_csv — витрина для CHANGE_SOURCE (E10); этап aggregate передаёт comparison.csv запуска

# pipeline/summary.py (E7)
def build_summary(comparison_csv: Path, segments_csv: Path, out_summary_json: Path, out_apps_csv: Path, log=None) -> dict: ...
```

Функции кидают исключения из `pipeline/errors.py`:
`PipelineError(code, message)` — базовое; `BadFile` (`code="bad_file"`), `Cancelled` (`code="cancelled"`).
`app` превращает их в `{ "error": { "code", "message" } }` из `docs/api.md`.

## 5. Конфиг разбора (`parse_cfg`, dict)

Это поля конфигурации из `docs/api.md` п. 4.2, которые касаются разбора:

```python
parse_cfg = {
  "ignore_paths": ["appData.request_id", "appData.createDateTime"],   # PATH без [] тоже подходят
  "array_rules": {"limits[]": {"mode": "key", "key": ["kind"]}},     # правило целиком (можно новый массив)
  "array_modes": {"decisionResult.scoring[].value": "index"},         # только режим
  "buckets": {"decisionResult.product_trials[].scoring.pd.value": [0.3, 0.6]},
}
```

Правила массивов по умолчанию (режим и ключ) — таблица в `ПАКЕТ/ЗАДАНИЕ/docs/ФОРМАТ_ОТВЕТА.md` («Массивы: девять штук»).
Они не в коде, а во встроенной процедуре `backend/procedures/builtin_normalize.py` (`ARRAY_RULES`, E9).
Порядок перекрытия: правила процедуры → `array_rules` конфигурации (правило целиком) → `array_modes` (только режим).

Пути полей слоя разрезов (решение, продукты, выдача, модель PD, порог, причина отказа, скор) — тоже процедура:
`backend/procedures/builtin_segments.py` (`FIELD_MAP`). Загрузка обоих файлов — `pipeline/procedures.py`
(`load_builtin(name, folder)`). Папку задаёт `app/settings.py` (`PROCEDURES_DIR`, по умолчанию `backend/procedures`),
этапы передают её в `parse_cfg["procedures_dir"]` и `build_segments(procedures_dir=...)`; сам `pipeline` окружение не читает.
Карту полей разрезов из конфигурации пока не поменять — только правкой `builtin_segments.py`.

## 6. Данные организаторов

Датасет и `ПАКЕТ/` — в `.gitignore`, **не коммитим**. В тестах, которые идут в репозиторий, —
только маленькие выдуманные JSON/CSV внутри `backend/tests/fixtures/` (несколько заявок, руками).
Тесты на настоящем датасете помечай `@pytest.mark.skipif(not DATASET.exists(), ...)`.
