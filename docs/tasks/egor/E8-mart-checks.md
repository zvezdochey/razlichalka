# E8. (после MVP) Витрина `mart` и запуск автопроверок

**Кто:** Егор · **Ветка:** `egor/checks` · **Папка:** `backend/pipeline/` · **Зависит от:** E5, E6 слиты в `main`

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E8-mart-checks.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Пользователь пишет проверки по контракту организаторов, мы их исполняем и показываем одной таблицей PASS/FAIL (этап `checks`, `docs/api.md` п. 10). Делаем **после** того, как заработал минимальный прототип.

## Что прочитать
- `ПАКЕТ/ЗАДАНИЕ/checks/README.md` — контракт проверки и `MartAPI`
- `ПАКЕТ/ЗАДАНИЕ/checks/*.py` — 5 готовых проверок, которые должны работать как есть
- `ПАКЕТ/ЗАДАНИЕ/docs/СХЕМА_ВИТРИНЫ.md` — раздел 3 (результат проверки)

## Что сделать
1. `backend/pipeline/mart.py`: класс `Mart(comparison_csv, segments_csv)` с методами `rows(**filters)`, `count`, `app_ids`, `segments`, `total_apps` и **всеми** фильтрами из `checks/README.md` (`path`, `path_prefix`, `key`, `array_key`, `diff_flag`, `change_type`, `value_before`, `value_after`, `app_ids`; можно списками). Поверх pandas, **с индексами** (например `groupby`-словари по `PATH`/`CHANGE_TYPE` заранее): вызовов много, ~290 тысяч строк. Строки отдавай как `dict` с ключами колонок витрины в верхнем регистре.
2. `backend/pipeline/checks_runner.py`:
   - `load_check(path_or_code, kind) -> CHECK` — загрузить проверку из файла `.py` либо из строки кода; объект `CHECK` с ключами `id/label/params/entrypoint`;
   - `run_checks(mart, checks, params_override=None, log=None) -> list[dict]` — вызвать `entrypoint(mart, params)` каждой, собрать строки, **не падать** от исключения одной проверки (залогировать `error` и вернуть служебную строку `FAIL`/`CONFIDENCE=LOW` с текстом ошибки в `ARGUMENT`);
   - `validate_check_code(code: str) -> list[{"line", "message"}]` — компилируется, есть `CHECK` и `run`/`entrypoint` (для `docs/api.md` п. 3.3);
   - `write_checks_csv(rows, out_csv)`: колонки `LABEL;SOURCE;ARGUMENT;CNT;TOTAL;METRIC;APP_IDS;RESULT;CONFIDENCE` (`APP_IDS` через `|`).
3. Исполнение пользовательского кода с таймаутом (`multiprocessing`/`signal`, хотя бы 60 с) — зависание не должно вешать запуск.

## Тесты
Пять готовых проверок из `ПАКЕТ/ЗАДАНИЕ/checks/` выполняются на `Mart` по настоящему датасету (`skipif`) за разумное время (замер — в описание PR); выдуманная проверка с исключением не роняет прогон; `validate_check_code` ловит синтаксическую ошибку и отсутствие `CHECK`.

## Готово, когда
Все 5 проверок отдают строки по схеме, `Mart` проходит собственные тесты фильтров.

## Безопасность
Пользовательский код исполняется на сервере. Для хакатона достаточно отдельного процесса с таймаутом; не давай ему путей к `.env`/секретам и не запускай от root (Семён настроит в Docker).
