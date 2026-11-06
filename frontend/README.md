# Фронт «Различалки»

React + TypeScript на Vite. Сравнивает решения двух версий СПР: какие заявки поменяли
решение, кого это затронуло и почему.

## Запуск

```bash
npm install
npm run dev      # http://localhost:5173, /api проксируется на http://localhost:8000
npm run build    # сборка в dist/ (tsc + vite build)
npm run preview  # посмотреть собранный dist/
```

Бэк не обязателен: в деве запросы к `/api/...` перехватывают моки (msw) и отвечают
выдуманными данными ровно по `docs/api.md`. Чтобы пойти на настоящий бэк, создайте
`.env.development.local` со строкой `VITE_USE_MOCKS=0` — тогда запросы уйдут через
прокси из `vite.config.ts` на `http://localhost:8000`. Список переменных — в `.env.example`.
В прод-сборке моков нет никогда.

Готовый прогон в моках — `r_mock` (уже в статусе `ready`), его можно открывать сразу:
`/runs/r_mock/overview`.

## Структура

- `src/styles/` — `tokens.css` (цвета и размеры, единственный источник), `base.css` (типографика,
  таблицы, кнопки, чипы), `pages.css` (раскладка страниц)
- `src/layout/` — `AppLayout`: шапка 48 px, левое меню 180 px, область контента
- `src/pages/` — страницы по маршрутам, `pages/run/` — вкладки прогона
- `src/components/` — общие `Spinner`, `ErrorBox`, `EmptyState`
- `src/api/` — слой API: `types.ts` (типы по `docs/api.md`), `client.ts` (fetch, заголовок
  `X-User`, разбор ошибок), `endpoints.ts` (по функции на ручку). Экраны импортируют из `src/api`
- `src/mocks/` — моки на msw: `data.ts` (выдуманный датасет), `runs.ts` (жизненный цикл запуска),
  `handlers.ts` (ручки), `start.ts` (включение). Только для дева
- `src/hooks/` — `usePolling` для опроса статуса запуска
- `src/lib/` — вспомогательное: `user.ts` (имя пользователя для заголовка `X-User`)

## Маршруты

`/` → `/runs` · `/runs` список · `/runs/new` настройка · `/runs/:id/{overview,apps,log}` прогон.
Вкладки — вложенные маршруты, поэтому ссылкой на вкладку можно поделиться.

## Что читать перед правками

`frontend/CLAUDE.md` и `frontend/PLAN.md` — визуальный язык и порядок задач,
`docs/api.md` — договор по API, `frontend/DESIGN.md` — дизайн-концепция.
