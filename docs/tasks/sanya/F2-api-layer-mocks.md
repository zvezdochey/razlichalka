# F2. Типы, клиент API и моки

**Кто:** Саня · **Ветка:** `front/api-layer` · **Папка:** `frontend/` · **Зависит от:** F1

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/sanya/F2-api-layer-mocks.md`. Сначала прочитай `AGENTS.md` и `docs/api.md`.»

## Зачем
Бэк пишется параллельно. Чтобы не ждать, фронт сначала работает на моках, которые отдают ровно то, что в `docs/api.md`. Когда бэк готов, переключаем одной переменной.

## Что сделать
1. `src/api/types.ts` — типы TypeScript **один к одному** с `docs/api.md`: `Dataset`, `Config`, `RunStatus`, `Stage`, `Summary`, `AppRow`, `AttributeRow`, `ApiError`, словари `Decision`, `DecisionChange`, `ChangeType`, `Status` (литеральные union-типы).
2. `src/api/client.ts` — функция `request<T>(path, init)`:
   - добавляет `X-User` из `localStorage`;
   - если `!res.ok` — читает `{error:{code,message}}` и кидает `ApiRequestError` с `code` и `message`;
   - сетевая ошибка → ошибка с понятным текстом «Нет связи с сервером».
3. `src/api/endpoints.ts` — по функции на каждую MVP-ручку: `getDatasets`, `createConfig`, `createRun`, `getRun`, `listRuns`, `cancelRun`, `getStages`, `getSummary`, `getApps(params)`, `getAttributes(runId, appId, params)`. Параметры списков — типизированный объект, превращается в query-строку аккуратно (пропускает `undefined`).
4. Ссылки на отчёт: `reportUrl(id)` → `/api/runs/{id}/report`, `reportDownloadUrl(id)` → `/api/runs/{id}/report.html`.
5. Моки: добавь `msw` (свежую версию смотри в Context7), `src/mocks/handlers.ts` — ответы по примерам из `docs/api.md` (датасет `RUN-20260827-0001`; запуск идёт `pending → running → ready` за ~6 секунд с растущим `progress`; `summary` из п. 7.1; 20–30 заявок в списке с работающими `decision_change`, `search`, `sort`, пагинацией; для заявки — 30 атрибутов с разными `change_type`, включая `null` с одной стороны).
6. Включение моков: `VITE_USE_MOCKS=1` в `.env.development.local` (не в Git; положи `.env.example`). Без переменной — идём на настоящий бэк через прокси.
7. Хук `usePolling(fn, intervalMs, stopWhen)` для опроса запуска раз в секунду, останавливается на `ready`/`error` и при уходе со страницы.

## Готово, когда
Из консоли/временной страницы `getSummary('r_mock')` возвращает типизированный объект; ошибка `404` приходит как `ApiRequestError` с `message` из тела; `tsc --noEmit` без ошибок.

## Не делай
Экраны — F3 и дальше. Если нужно поменять формат ответа — не меняй его молча: правка идёт сначала в `docs/api.md` и сообщается Семёну.
