# S5. Подключить настоящий пайплайн Егора

**Кто:** Семён · **Ветка:** `semyon/real-pipeline` · **Папка:** `backend/app/` · **Зависит от:** S4 и слитые E3, E5, E6, E7

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S5-real-pipeline.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Заменяем заглушки S4 на вызовы функций из `backend/pipeline/` — запуск начинает реально считать.

## Что сделать
1. `app/services/stages.py`: реализации этапов с тем же интерфейсом `(ctx) -> None`, что и заглушки:
   - `normalize`: `normalize_dataset` дважды (`BEFORE`, `AFTER`), в `normalized_BEFORE.csv` / `normalized_AFTER.csv`. `parse_cfg` собирается из конфигурации запуска (CONTRACTS §5). Прогресс: `on_progress` второго среза складывать со смещением первого (общий `done` растёт от 0 до 4004);
   - `compare`: `compare_csv(...)` → `comparison.csv`;
   - `aggregate`: `build_segments(...)` → `segments.csv`, затем `build_summary(...)` → `summary.json`, `apps.csv`. (Логически «сегменты» — часть факта; в журнале этап один `aggregate`, но в `log` пиши обе подстадии);
   - `checks`: пока **пропуск** — этап `ready` с записью в лог «Проверки не подключены» (подключит S10).
2. Каждый этап прокидывает `log`/`is_cancelled` в функции Егора; `PipelineError` и его потомки превращаются в `{code,message}` ошибки этапа (S4 уже умеет).
3. `code_ref` этапов: для встроенных процедур `{"procedure_id":"builtin_normalize","source":"file","path":"backend/pipeline/normalize.py","line":1}` (аналогично compare/aggregate) — как в примере п. 6.
4. Переключатель `USE_STUB_PIPELINE=0` по умолчанию; заглушку оставь для тестов и разработки фронта (`USE_STUB_PIPELINE=1`).
5. Если в каталоге запуска нет нужных файлов этапа — понятная ошибка, а не `FileNotFoundError` наружу.

## Тесты
- На мини-фикстуре (`backend/tests/fixtures/dataset_mini/`, из E3): запуск доходит до `ready`, в каталоге запуска появляются все 6 файлов из CONTRACTS §3.
- На настоящем датасете (`skipif`): время каждого этапа в лог теста; `summary.json["decision_changed"] == 385`.
- Отмена посреди `normalize` — `error.code="cancelled"`, статус запуска `error`.

## Готово, когда
`POST /api/runs` на настоящем датасете проходит до `ready` в разумное время (цель — до 3 минут; если больше, скажи Егору, какой этап тормозит); `GET /stages` показывает 4 этапа с логами.

## Не делай
Чтение результатов — S6.
