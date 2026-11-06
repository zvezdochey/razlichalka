# API: договорённость между бэком и фронтом

Это «розетка и вилка». Бэк отдаёт ровно такие ответы, фронт рассчитывает ровно на них.
Хочешь поменять формат — сначала договорись со второй стороной и поправь этот файл.

Версия 2 (6 ноября). Переписана под ТЗ: на вход — готовый датасет прогона, а не два файла.
Данные: `ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001/` — два среза по 2002 JSON-файла.

Адрес бэка: `http://localhost:8000`. Все ручки начинаются с `/api`.
Пользователь пока не авторизуется: передаём заголовок `X-User: <имя>`. Конфигурации и запуски принадлежат этому пользователю.

---

## Главная идея

1. Пользователь выбирает датасет, процедуры и проверки и **сохраняет конфигурацию**.
2. По конфигурации создаётся **запуск** (`run`). Бэк обрабатывает его в фоне.
3. Фронт опрашивает статус и этапы. Когда запуск `ready`, фронт открывает отчёт.
4. Запуск не пропадает после перезагрузки страницы: фронт берёт его по `id`.

Частичные результаты не показываем: витрину, факты и отчёт отдаём только у запуска в статусе `ready`.

---

## Общие словари

**Срез** (`source`): `BEFORE` (MASTER, прод) и `AFTER` (BETA, изменение).

**Решение** (`decision`): `approve`, `reject`, `other`.
Бэк сам переводит `APPROVE`/`REJECT` из данных (и любые другие написания) в эти значения.

**Решение изменилось** (`decision_change`):

| Значение | Что значит |
|---|---|
| `same` | решение то же |
| `approve_to_reject` | было approve → стало reject |
| `reject_to_approve` | было reject → стало approve |
| `decision_other` | решение изменилось иначе (например, на `other`) |

**Изменение атрибута** (`change_type`) — из ТЗ, ровно четыре значения:

| Значение | Что значит |
|---|---|
| `SAME` | атрибут есть в обоих срезах, значения совпадают |
| `VALUE_CHANGED` | атрибут есть в обоих срезах, значения разные |
| `ATTRIBUTE_NEW` | атрибута нет в BEFORE, есть в AFTER |
| `ATTRIBUTE_LOST` | атрибут есть в BEFORE, нет в AFTER |

**Статус** (`status`) у датасета, конфигурации этапа и запуска: `pending`, `running`, `ready`, `error`.

---

## 1. Проверка, что бэк жив

`GET /api/health`

```json
{ "status": "ok" }
```

---

## 2. Датасеты

### 2.1. Список доступных датасетов

`GET /api/datasets`

```json
{
  "datasets": [
    {
      "id": "RUN-20260827-0001",
      "applications": 2002,
      "sources": { "BEFORE": "MASTER", "AFTER": "BETA" },
      "technical_fields": ["appData.request_id", "appData.createDateTime"]
    }
  ]
}
```

Датасеты лежат на сервере, загружать их через фронт не нужно.

---

## 3. Процедуры и проверки (код пользователя)

Каждая процедура — это Python-код, который подчиняется контракту из `ПАКЕТ/ЗАДАНИЕ/docs/СХЕМА_ВИТРИНЫ.md` и `checks/README.md`.
Код может быть **из рабочей области** (`source: "inline"`, текст в поле `code`) или **файлом** на сервере (`source: "file"`, путь в поле `path`).

Виды процедур (`kind`):

| `kind` | Вход | Выход |
|---|---|---|
| `normalize` | JSON одного ответа | строки плоской таблицы (поля витрины) |
| `aggregate` | витрина сравнения | факты `counts` для сводного отчёта |
| `check` | факты и витрина | строки `PASS` / `FAIL` |

### 3.1. Список процедур

`GET /api/procedures?kind=check`

```json
{
  "procedures": [
    { "id": "p_1", "kind": "check", "name": "Approval Rate продукта <10%", "source": "inline", "builtin": false, "updated_at": "2026-11-06T12:00:00Z" },
    { "id": "builtin_missing_attrs", "kind": "check", "name": "Отсутствующие атрибуты", "source": "file", "path": "checks/check_attribute_new_loss.py", "builtin": true, "updated_at": null }
  ]
}
```

### 3.2. Создать процедуру

`POST /api/procedures`

```json
{ "kind": "check", "name": "Approval Rate продукта <10%", "source": "inline", "code": "def run(ctx):\n    ...\n" }
```

Или с файлом: `{ "kind": "normalize", "name": "...", "source": "file", "path": "procedures/my_norm.py" }`.

Ответ: объект процедуры (`201`). Если код не проходит проверку контракта, ответ — ошибка `bad_code` (см. «Ошибки»), в `message` — где именно.

### 3.3. Проверить код процедуры без запуска

`POST /api/procedures/validate`

```json
{ "kind": "check", "source": "inline", "code": "def run(ctx):\n    ...\n" }
```

```json
{ "ok": false, "errors": [ { "line": 3, "message": "Нет возврата PASS/FAIL" } ] }
```

Нужна, чтобы фронт показал ошибки до запуска.

### 3.4. Изменить и удалить

- `PUT /api/procedures/{id}` — то же тело, что при создании.
- `DELETE /api/procedures/{id}` — `204`. Встроенные (`builtin: true`) не удаляются, ответ `409` с кодом `conflict`.

### 3.5. Журнал исполнения процедуры

Запуск каждой процедуры пишет логи по этапам (см. раздел 6). Фронт получает их там же.

---

## 4. Конфигурации

Конфигурация — это «что запускаем»: датасет, процедуры приведения и сравнения, проверки, пути-исключения и режимы массивов.

### 4.1. Список конфигураций пользователя

`GET /api/configs`

```json
{
  "configs": [
    { "id": "cfg_1", "name": "Прогон на 06.11", "dataset": "RUN-20260827-0001", "updated_at": "2026-11-06T12:00:00Z" }
  ]
}
```

### 4.2. Создать конфигурацию

`POST /api/configs`

```json
{
  "name": "Прогон на 06.11",
  "dataset": "RUN-20260827-0001",
  "normalize": "builtin_normalize",
  "aggregate": "builtin_aggregate",
  "checks": ["builtin_missing_attrs", "p_1"],
  "ignore_paths": ["appData.request_id", "appData.createDateTime"],
  "array_modes": { "decisionResult.scoring[].value": "index" },
  "buckets": { "PD": [0.3, 0.6] }
}
```

- `normalize`, `aggregate` — id процедуры нужного `kind`.
- `checks` — список id проверок (`kind: "check"`).
- `ignore_paths` — пути, которые не сравниваем. По умолчанию — два технических поля из датасета.
- `array_modes` — режим сравнения массива по пути: `key`, `value`, `index`. Без записи — `key`.
- `buckets` — границы бакетов (для `ADJUSTED_VALUE`), одни и те же для обоих срезов.

Ответ: объект конфигурации (`201`).

### 4.3. Изменить, удалить

- `PUT /api/configs/{id}` — то же тело.
- `DELETE /api/configs/{id}` — `204`. Запуски, созданные по ней, остаются.

---

## 5. Запуски

### 5.1. Запустить прогон

`POST /api/runs`

```json
{ "config_id": "cfg_1" }
```

Ответ (`202`):

```json
{ "id": "r_7f3a", "status": "pending", "config_id": "cfg_1" }
```

Запуск выполняется в фоне. Ручка сразу возвращает `id`, интерфейс не ждёт.

### 5.2. Статус запуска

`GET /api/runs/{id}`

```json
{
  "id": "r_7f3a",
  "status": "running",
  "config_id": "cfg_1",
  "dataset": "RUN-20260827-0001",
  "created_at": "2026-11-06T12:00:00Z",
  "finished_at": null,
  "progress": { "done": 1200, "total": 4004 },
  "current_stage": "normalize",
  "error": null
}
```

- `progress` — количество обработанных файлов из общего числа.
- Фронт опрашивает раз в секунду, пока статус `pending` или `running`.
- При `error` в поле `error` лежит объект ошибки (см. «Ошибки»).

### 5.3. Список запусков пользователя

`GET /api/runs`

```json
{
  "runs": [
    { "id": "r_7f3a", "status": "ready", "config_id": "cfg_1", "created_at": "2026-11-06T12:00:00Z" }
  ]
}
```

### 5.4. Остановить запуск

`POST /api/runs/{id}/cancel` → `{ "id": "r_7f3a", "status": "error", "error": { "code": "cancelled", "message": "Остановлено пользователем" } }`

---

## 6. Журнал этапов

`GET /api/runs/{id}/stages`

```json
{
  "stages": [
    {
      "name": "normalize",
      "title": "Приведение ответов",
      "status": "ready",
      "started_at": "2026-11-06T12:00:01Z",
      "finished_at": "2026-11-06T12:01:10Z",
      "procedure_id": "builtin_normalize",
      "code_ref": { "procedure_id": "builtin_normalize", "source": "file", "path": "procedures/normalize.py", "line": 1 },
      "log": [ { "at": "2026-11-06T12:00:02Z", "level": "info", "message": "Обработано 500 из 4004" } ]
    },
    { "name": "compare", "title": "Сравнение срезов", "status": "running", "started_at": "2026-11-06T12:01:11Z", "finished_at": null, "procedure_id": null, "code_ref": null, "log": [] },
    { "name": "aggregate", "title": "Факты counts", "status": "pending", "started_at": null, "finished_at": null, "procedure_id": "builtin_aggregate", "code_ref": null, "log": [] },
    { "name": "checks", "title": "Проверки", "status": "pending", "started_at": null, "finished_at": null, "procedure_id": null, "code_ref": null, "log": [] }
  ]
}
```

- Этапы идут в порядке: `normalize`, `compare`, `aggregate`, `checks`.
- `code_ref` — куда перейти по клику: id процедуры, путь (для `file`) или `inline`, и номер строки.
- `log` — последние записи этапа. Полный журнал: `GET /api/runs/{id}/stages/{name}/log?after=<индекс>`.

---

## 7. Витрина и факты

### 7.1. Итоги (для счётчиков сверху)

`GET /api/runs/{id}/summary`

```json
{
  "applications": 2002,
  "applications_changed": 340,
  "applications_changed_share": 0.170,
  "decision_changed": 95,
  "decision_changes": {
    "same": 1907,
    "approve_to_reject": 210,
    "reject_to_approve": 95,
    "decision_other": 0
  },
  "attributes": { "SAME": 280000, "VALUE_CHANGED": 6000, "ATTRIBUTE_NEW": 2000, "ATTRIBUTE_LOST": 1200 }
}
```

Числа здесь — только пример формы, на реальных данных они будут другими.
Поле `applications_changed` — число заявок с хотя бы одним различием. Его сверяем с эталоном.

### 7.2. Факты для сводной таблицы

`GET /api/runs/{id}/facts?dims=PREFIX,PATH&measure=counts&filter=CHANGE_TYPE:VALUE_CHANGED`

Факты — это агрегат «заявки по измерениям». Пользователь сам выбирает измерения.

Параметры:
- `dims` — измерения через запятую: поля витрины или поля разреза (`PRODUCT`, `PARTNER_TYPE`, `PD_MODEL_BEFORE` и т.п.).
- `filter` — `поле:значение`, можно несколько через `;`.
- `measure` — `counts` (количество строк) или `counts_distinct_apps`.

```json
{
  "dims": ["PREFIX", "PATH"],
  "rows": [
    { "PREFIX": "decisionResult", "PATH": "decisionResult.scoring.pd", "counts": 210, "app_ids_ref": "f_9c1" }
  ]
}
```

`app_ids_ref` — ключ для списка заявок (ручка 7.3). Так список заявок не тянем в каждой строке.

### 7.3. Заявки по группе фактов

`GET /api/runs/{id}/facts/{app_ids_ref}/apps?page=1&size=50`

```json
{ "page": 1, "size": 50, "total": 210, "apps": [ "I32554355", "I32554354" ] }
```

### 7.4. Список заявок с различиями

`GET /api/runs/{id}/apps?decision_change=approve_to_reject&search=I325&sort=-applications_changed&page=1&size=50`

Параметры:
- `decision_change` — один или несколько значений через запятую (словарь «Решение изменилось»).
- `has_attr_change` — `1`: только заявки с хотя бы одним различием атрибута.
- `search` — поиск по `APP_ID` и текстовым полям разреза.
- `sort` — поле, минус = по убыванию.
- `page` с 1, `size` до 500.

```json
{
  "page": 1,
  "size": 50,
  "total": 210,
  "apps": [
    {
      "app_id": "I32554355",
      "decision_before": "approve",
      "decision_after": "reject",
      "decision_change": "approve_to_reject",
      "attributes_changed": 4,
      "pd_model_before": "PD_RETAIL_V2",
      "pd_model_after": "PD_RETAIL_V2",
      "cutoff_before": "PD_RETAIL",
      "cutoff_after": "PD_RETAIL",
      "reject_reason_before": null,
      "reject_reason_after": "HARDCHECK"
    }
  ]
}
```

---

## 8. Одна заявка подробно

### 8.1. Сравнение атрибутов заявки

`GET /api/runs/{id}/apps/{app_id}/attributes?change_type=VALUE_CHANGED,ATTRIBUTE_NEW&page=1&size=100`

Это строки витрины одной заявки.

```json
{
  "app_id": "I32554355",
  "page": 1,
  "size": 100,
  "total": 4,
  "attributes": [
    {
      "path": "decisionResult.scoring.pd.value",
      "array_key": "",
      "key": "value",
      "value_before": "0.42",
      "value_after": "0.58",
      "adjusted_before": "(0.3 – 0.6]",
      "adjusted_after": "(0.3 – 0.6]",
      "diff_flag": 1,
      "change_type": "VALUE_CHANGED"
    }
  ]
}
```

Атрибут с `ATTRIBUTE_NEW` или `ATTRIBUTE_LOST` имеет пустое значение с той стороны, где его нет: `value_before` или `value_after` равно `null`.

### 8.2. Карточка заявки (до и после)

`GET /api/runs/{id}/apps/{app_id}`

Для окна «почему»: решение, офферы, стоп-факторы, модели и пороги в каждом срезе. Формат — две колонки `before` и `after`. Это только для показа, не для технического хранения.

```json
{
  "app_id": "I32554355",
  "decision_change": "approve_to_reject",
  "before": { "decision": "approve", "products": [ { "product_id": "CASH_LOAN", "partner_type": "CURRENT", "decision": "approve", "reject_reason": null, "pd_model": "PD_RETAIL_V2", "pd": 0.42, "cutoff": { "name": "PD_RETAIL", "value": 0.55 }, "rules": [ { "name": "AGELOW@21", "hit": false } ] } ] },
  "after":  { "decision": "reject",  "products": [ { "product_id": "CASH_LOAN", "partner_type": "CURRENT", "decision": "reject",  "reject_reason": "HARDCHECK", "reject_reason_code": "AGELOW@21", "pd_model": "PD_RETAIL_V2", "pd": 0.58, "cutoff": { "name": "PD_RETAIL", "value": 0.55 }, "rules": [ { "name": "AGELOW@21", "hit": true } ] } ] },
  "reasons": [ { "text": "Сработал стоп-фактор AGELOW@21", "source": "rule", "confidence": "high" } ]
}
```

- `reasons[].source`: `rule` (стоп-фактор), `score` (сдвиг балла), `cutoff` (сдвиг порога), `product` (сменился продукт), `unknown`.
- `confidence`: `high` — причина видна в данных, `low` — наша догадка.

---

## 9. Что ломает решение (главные причины)

`GET /api/runs/{id}/reasons`

```json
{
  "reasons": [
    { "text": "Сработал стоп-фактор AGELOW@21", "source": "rule", "affected": 210, "share": 0.62 },
    { "text": "Сдвиг порога PD_RETAIL 0.55 → 0.58", "source": "cutoff", "affected": 128, "share": 0.38 }
  ],
  "unexplained": 35
}
```

`unexplained` — сколько изменённых заявок не удалось объяснить. Показываем жюри честно.

---

## 10. Проверки и отчёт проверок

### 10.1. Результат проверок одной таблицей

`GET /api/runs/{id}/checks?result=FAIL&page=1&size=50`

Строки всех проверок, сколько бы их ни было и кто бы их ни написал.

```json
{
  "page": 1,
  "size": 50,
  "total": 11,
  "rows": [
    {
      "check_id": "builtin_missing_attrs",
      "check_name": "Отсутствующие атрибуты",
      "source": "AFTER",
      "argument": null,
      "numbers": "0 / 500",
      "metric": null,
      "result": "PASS",
      "apps_ref": null,
      "faint": false
    },
    {
      "check_id": "p_1",
      "check_name": "Approval Rate продукта <10%",
      "source": "AFTER",
      "argument": "CASH_LOAN",
      "numbers": "214 / 500",
      "metric": "21.4%",
      "result": "FAIL",
      "apps_ref": "f_41a",
      "faint": false
    }
  ]
}
```

- `result` — `PASS` или `FAIL`.
- `apps_ref` — список заявок (ручка 7.3). `null`, если заявок нет.
- `faint` — `true`, если срабатываний мало и уверенности нет. Фронт показывает такую строку бледной, как в ТЗ.

### 10.2. Запуск проверок с новым кодом

Новая проверка добавляется через `POST /api/procedures` и подключается к конфигурации (`PUT /api/configs/{id}`). Затем нужен новый запуск: `POST /api/runs`.

---

## 11. Отчёт в браузере и HTML

- `GET /api/runs/{id}/report` — HTML-страница отчёта. Открывается по ссылке, пока запуск `ready`. Если нет — `409` с кодом `not_ready`.
- `GET /api/runs/{id}/report.html` — то же, с заголовком `Content-Disposition: attachment` (скачивание).
- В HTML есть ссылки на сводный отчёт приложения: `{origin}/runs/{id}`.

---

## 12. Мнение ИИ

`GET /api/runs/{id}/ai-review`

Отвечает только при `ready`. Модели передаём агрегаты, выборку различий и результаты проверок, но не всю витрину.

```json
{ "status": "ready", "text": "Решение изменилось у 95 заявок; главная причина — стоп-фактор AGELOW@21. Проверьте…", "generated_at": "2026-11-06T12:05:00Z" }
```

Если `status` равен `pending`, фронт показывает «Считаем…» и опрашивает ручку. Если `error`, показываем текст ошибки, отчёт остаётся доступен.

---

## 13. Экспорт

`GET /api/runs/{id}/export.csv?decision_change=approve_to_reject`

Отдаёт CSV по списку заявок (ручка 7.4) с теми же фильтрами.

---

## Ошибки

Любая ошибка — в одном виде:

```json
{ "error": { "code": "bad_file", "message": "Не получилось прочитать процедуру: нет функции run" } }
```

| `code` | HTTP | Когда |
|---|---|---|
| `bad_file` | 400 | файл или датасет не читается или не того формата |
| `bad_code` | 400 | код процедуры не проходит проверку контракта, в `message` — строка и причина |
| `no_id_column` | 400 | не нашли, по какому полю склеивать заявки |
| `not_found` | 404 | нет такого датасета, конфигурации, запуска, процедуры или заявки |
| `not_ready` | 409 | запрос к отчёту или фактам, а запуск ещё не `ready` |
| `conflict` | 409 | нельзя удалить встроенную процедуру |
| `cancelled` | — | запуск остановлен пользователем (в поле `error` статуса запуска) |
| `internal` | 500 | всё остальное |

Фронт показывает `message` пользователю как есть.
Ошибка этапа записывается в его журнал и в `error` запуска. У запуска `status` становится `error`, а у этапа — тоже.

---

## Порядок работы на хакатоне

1. **Сейчас:** бэк делает ручки с **выдуманными** ответами ровно как тут: датасеты, конфигурации, запуск, статус, этапы, итоги, заявки, атрибуты, отчёт. Фронт работает с ними.
2. **Дальше:** бэк заменяет выдумку на настоящий расчёт. Фронт ничего не замечает.
3. **Минимум для показа:** запуск и статус (5.1–5.2), этапы (6), итоги (7.1), список заявок (7.4), атрибуты заявки (8.1), отчёт (11). Остальное — по мере сил.
