# S9. (после MVP) Факты сводной, карточка «почему», причины, экспорт

**Кто:** Семён · **Ветка:** `semyon/facts` · **Папка:** `backend/app/` · **Зависит от:** S6; E6 слит

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S9-facts-reasons-export.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` (п. 7.2–7.3, 8.2, 9, 13) и `docs/tasks/CONTRACTS.md`.»

## Зачем
Сводная таблица («факты») и объяснение причин — вторая половина ТЗ. Это делаем только когда MVP стоит на ногах.

## Что сделать (по порядку, можно остановиться на любом пункте)
1. **Факты** `GET /api/runs/{id}/facts` (п. 7.2): `dims` — любые колонки `segments.csv` или `comparison.csv` (`CHANGE_TYPE`, `PATH`, …), `filter=поле:значение;...`, `measure=counts|counts_distinct_apps`. Склей `comparison` с `segments` по `APP_ID`, `groupby(dims)`. `app_ids_ref` — короткий хеш (`f_<hex>`) от `dims+filter+значения`, соответствие хранится в `run.json`/кэше. Неизвестное измерение → 400.
2. **Заявки группы** `GET /api/runs/{id}/facts/{ref}/apps` (п. 7.3): пагинация, уникальные `APP_ID`.
3. **Экспорт** `GET /api/runs/{id}/export.csv` (п. 13): те же фильтры, что у `/apps`, `Content-Disposition: attachment`, `;` и BOM, чтобы открывался в Excel.
4. **Карточка заявки** `GET /api/runs/{id}/apps/{app_id}` (п. 8.2): читает два исходных JSON этой заявки из датасета и собирает `before/after` (решение, `offers`, продукты с `rules`, `pd`, `cutoff`). `reasons` — простые правила: стоп-фактор был `hit=true` в BEFORE и не в AFTER → `source: rule, confidence: high`; изменилась модель `pd.modelName` → `source: score`; изменился порог `cutOff.value` → `source: cutoff`; ничего не нашли → `unknown`/`low`. Формулировки — «Возможная причина…» там, где это догадка.
5. **Причины** `GET /api/runs/{id}/reasons` (п. 9): топ причин отказа по заявкам со сменой решения на `reject` (группировка по `REJECT_REASON_AFTER` + имени порога/правила); `unexplained` пока `null`.

## Тесты
На `run_mini` (расширь фикстуру при необходимости): `dims=CHANGE_TYPE`, фильтр по `DECISION_CHANGED:1`, ссылка `app_ids_ref` ведёт на правильные заявки, экспорт открывается `pandas`, карточка одной заявки.

## Готово, когда
Каждая сделанная ручка совпадает с примером из `docs/api.md`; сумма `counts` в фактах сходится с ручным `groupby` в тесте.

## ⚠ 7 ноября задача переехала к Илье
По плану [PLAN-day2.md](../PLAN-day2.md) S9 делает Илья:
- пункты 1–3 (факты, заявки группы, экспорт) → [ilya/I1-facts-export.md](../ilya/I1-facts-export.md);
- пункты 4–5 (карточка заявки, причины) → [ilya/I3-app-card-reasons.md](../ilya/I3-app-card-reasons.md).

Этот файл оставлен как исходная постановка; работать по файлам Ильи. Семёну отсюда нужна только функция
`make_apps_ref` из I1 — для `apps_ref` у проверок в S10.
