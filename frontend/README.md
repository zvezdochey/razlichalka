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

Бэк не обязателен, чтобы увидеть каркас, но все запросы к API идут по относительным
адресам `/api/...` — в деве их перебрасывает прокси из `vite.config.ts`.

## Структура

- `src/styles/` — `tokens.css` (цвета и размеры, единственный источник), `base.css` (типографика,
  таблицы, кнопки, чипы), `pages.css` (раскладка страниц)
- `src/layout/` — `AppLayout`: шапка 48 px, левое меню 180 px, область контента
- `src/pages/` — страницы по маршрутам, `pages/run/` — вкладки прогона
- `src/components/` — общие `Spinner`, `ErrorBox`, `EmptyState`
- `src/lib/` — вспомогательное: `user.ts` (имя пользователя для заголовка `X-User`)

## Маршруты

`/` → `/runs` · `/runs` список · `/runs/new` настройка · `/runs/:id/{overview,apps,log}` прогон.
Вкладки — вложенные маршруты, поэтому ссылкой на вкладку можно поделиться.

## Что читать перед правками

`frontend/CLAUDE.md` и `frontend/PLAN.md` — визуальный язык и порядок задач,
`docs/api.md` — договор по API, `frontend/DESIGN.md` — дизайн-концепция.
