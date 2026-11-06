# S6. Ручки результатов: итоги, заявки, атрибуты

**Кто:** Семён · **Ветка:** `semyon/results` · **Папка:** `backend/app/` · **Зависит от:** S4. Настоящих данных от Егора не ждёт — работает на мини-фикстуре

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S6-results-endpoints.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Три главные ручки, которые рисуют фронт: счётчики, таблица заявок, различия по заявке (`docs/api.md` п. 7.1, 7.4, 8.1).

## Что сделать
1. Фикстура `backend/tests/fixtures/run_mini/`: руками написанные `comparison.csv`, `segments.csv`, `apps.csv`, `summary.json` на 6–8 заявок в формате CONTRACTS §2 (есть `approve_to_reject`, `reject_to_approve`, `same`; у одной заявки есть `ATTRIBUTE_NEW` и `ATTRIBUTE_LOST`). Это не данные организаторов.
2. Заглушка S4 (`USE_STUB_PIPELINE=1`): при `aggregate` копирует эти файлы в каталог запуска — тогда фронт может работать на настоящем бэке без датасета.
3. `app/services/results.py`: загрузка CSV запуска в pandas с **кэшем по `run_id`** (`functools.lru_cache`/словарь; сбрасывать не нужно — файлы неизменны после `ready`). Загрузка идёт через `pipeline.csvio.read_csv`, а если Егор ещё не слил — через `pandas.read_csv(sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)`.
4. Общая проверка: запуск чужой → `not_found`; статус не `ready` → `not_ready` (409).
5. Ручки (`app/routers/results.py`):
   - `GET /api/runs/{id}/summary` — отдать `summary.json` как есть;
   - `GET /api/runs/{id}/apps` — п. 7.4. Параметры: `decision_change` (список через запятую), `has_attr_change=1`, `search` (подстрока в `app_id` и текстовых полях разреза, регистр не важен), `sort` (`-` = по убыванию; допустимы только известные колонки; иначе `bad_file`/400 с текстом), `page` с 1, `size` по умолчанию 50, максимум 500. Числа (`attributes_changed`) сортируются как числа, не как строки. Пустые значения → `null`;
   - `GET /api/runs/{id}/apps/{app_id}/attributes` — п. 8.1: поля `path, array_key, key, value_before, value_after, adjusted_before, adjusted_after, diff_flag (число), change_type`; пустое `VALUE_*`/`ADJUSTED_*` → `null`; `array_key` пустой → `null`; параметры `page,size` (до 500), плюс **добавь** `only_diff=1` (только `DIFF_FLAG=1`) и `search` по `path` — это нужно фронту; впиши в `docs/api.md` п. 8.1 и скажи Сане. Нет заявки в запуске → `not_found`. Сортировка: сначала `diff_flag=1`, потом по `path`.
6. Формат строго по `docs/api.md`, имена полей в нижнем регистре.

## Тесты
На `run_mini`: фильтры (по одному значению, по двум), поиск, сортировка по убыванию, пагинация (`total` не меняется от страницы), `has_attr_change`, `only_diff`, 409 для неготового запуска, 404 для чужой/неизвестной заявки.

## Готово, когда
Агент `api-tester` проходит эти три ручки на запуске-заглушке; ответ на `size=500` быстрый (< 200 мс).

## Не делай
Факты/сводную (S9), карточку «почему» (S9).
