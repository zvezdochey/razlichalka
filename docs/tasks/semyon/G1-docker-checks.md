# G1. Встроенные проверки работают в Docker

**Кто:** Семён · **Ветка:** `semyon/docker-checks` · **Папка:** корень (`docker-compose.yml`), `README.md` · **Зависит от:** — · **Время:** ~1 час, **первым делом**

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/G1-docker-checks.md`. Сначала прочитай `AGENTS.md`, `docs/tasks/GAPS-7nov.md` и `backend/app/settings.py`.»

## Зачем
ТЗ: «Проект поднимается по README на чистой машине». Сейчас в Docker выданные проверки из `ПАКЕТ/ЗАДАНИЕ/checks/` не видны бэку.
Конфигурация с `checks: ["builtin_attribute_new_loss"]` падает с `404 Процедура не найдена`, и пользователь не понимает почему.

Проверено: `curl -X POST /api/configs` с встроенной проверкой → 404. С примонтированной папкой `/checks` и `CHECKS_DIR=/checks`
`GET /api/procedures?kind=check` возвращает 5 проверок, прогон даёт строки FAIL/PASS.

## Что сделать
1. В `docker-compose.yml` для сервиса `backend` примонтировать папку проверок только на чтение и задать `CHECKS_DIR=/checks`.
   Путь по умолчанию — `./ПАКЕТ/ЗАДАНИЕ/checks`, переопределяется переменной `CHECKS_PATH` (по аналогии с `DATASETS_PATH`).
2. Порт фронта сделать настраиваемым (`FRONTEND_PORT`, по умолчанию `3000`). Сейчас порт 3000 занят другим стеком и `up` падает.
3. `.dockerignore` не трогать: `ПАКЕТ/` в образ не попадает, данные и проверки подключаются только томами.
4. В `README.md` — раздел «Запуск с нуля»: `cp .env.example .env`, что поправить (`DATASETS_PATH`, `CHECKS_PATH`, `FRONTEND_PORT`), команда `docker compose up -d --build`.
5. Коммит: `chore: проверки и датасет подключаются через Docker-тома, порт фронта настраивается`.

## Готово, когда
- На чистом клоне `main`: `cp .env.example .env` → `docker compose up -d --build` → `GET /api/health` = 200.
- `POST /api/configs` с `checks: ["builtin_attribute_new_loss"]` → 201, прогон до `ready`, `GET /api/runs/{id}/checks` содержит строки с `check_id: builtin_attribute_new_loss`.
- Саня получил список новых переменных окружения.
