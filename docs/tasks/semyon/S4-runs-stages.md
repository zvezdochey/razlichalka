# S4. Запуски и этапы (пока с фейковым пайплайном)

**Кто:** Семён · **Ветка:** `semyon/runs` · **Папка:** `backend/app/` · **Зависит от:** S1, S3

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S4-runs-stages.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Фронту нужны ручки запуска и статуса сразу, не дожидаясь Егора. Делаем всю «обвязку» фонового запуска, а вместо настоящих вычислений пока кладём заглушку с `sleep`. Настоящий пайплайн подключит S5.

## Что сделать
1. Модель запуска в `app/services/runs.py` и файл `DATA_DIR/runs/<id>/run.json`:
   `id` (`r_` + 4–6 hex), `owner`, `config_id`, `config` (копия на момент запуска — чтобы правка конфигурации не ломала прошлые запуски), `dataset`, `status`, `created_at`, `finished_at`, `progress{done,total}`, `current_stage`, `error`, `stages[]` (по п. 6: `name,title,status,started_at,finished_at,procedure_id,code_ref,log[]`).
   Четыре этапа по порядку: `normalize` («Приведение ответов»), `compare` («Сравнение срезов»), `aggregate` («Факты counts»), `checks` («Проверки»). Времена — ISO-8601 UTC.
2. Реестр запусков в памяти + запись в `run.json` при каждом изменении (запись атомарная, как в S3). При старте сервера запуски, оставшиеся `running`/`pending`, помечаются `error` (`code="internal"`, «Сервер перезапускали во время запуска»). Список запусков читается с диска.
3. Ручки (`app/routers/runs.py`), всё в границах пользователя `X-User`:
   - `POST /api/runs` `{config_id}` → **202** `{id,status:"pending",config_id}` (п. 5.1); неизвестная конфигурация → `not_found`;
   - `GET /api/runs/{id}` — п. 5.2, поля ровно как в примере;
   - `GET /api/runs` — п. 5.3, новые сверху;
   - `POST /api/runs/{id}/cancel` — п. 5.4 (ставит флаг; запуск завершается сам; если уже `ready`/`error` — отдаёт текущий статус без ошибки);
   - `GET /api/runs/{id}/stages` — п. 6; `log` — последние 50 записей;
   - `GET /api/runs/{id}/stages/{name}/log?after=<индекс>` — все записи с индекса, `{ "entries": [...], "next": N }` (в `docs/api.md` формат не описан — добавь пример одной строкой в п. 6 и скажи Сане).
4. Фон: `concurrent.futures.ThreadPoolExecutor(max_workers=2)`; функция `execute(run, ctx)` вызывает **список этапов** `PIPELINE = [stage_normalize, stage_compare, ...]`. Каждый этап — функция `(ctx) -> None`, где `ctx` даёт `log(level,msg)`, `progress(done,total)`, `is_cancelled()`, пути к файлам запуска. Менеджер этапов: ставит `running/ready/error`, пишет `started_at/finished_at`, ловит исключения (в `error` запуска и этапа — `{code,message}`), `Cancelled` → `error.code="cancelled"`.
5. Заглушки этапов `app/pipeline_stub.py`: каждый этап «работает» 2–3 секунды, шлёт `progress`, пишет пару строк лога. Флаг в `settings`: `USE_STUB_PIPELINE=1` (по умолчанию 1 до S5).
6. Нарезка прогресса: `progress.total` = 2 × число заявок датасета (`4004`), `current_stage` = имя активного этапа, `null` когда закончили.

## Тесты
Создать запуск → быстро поллить статус → дойти до `ready`; `cancel` посередине → `error.code="cancelled"`; чужой пользователь получает `not_found`; после «перезапуска» (пересоздание `app`) запуск читается с диска; ошибка внутри этапа даёт `error` у этапа и запуска, дальнейшие этапы остаются `pending`.

## Готово, когда
Фронт может пройти весь путь «POST → поллинг → ready» на заглушке; формат совпадает с `docs/api.md` слово в слово (проверь агентом `api-tester`).

## Не делай
Настоящую обработку (S5), чтение результатов (S6).
