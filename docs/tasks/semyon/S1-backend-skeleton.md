# S1. Скелет бэка: FastAPI, ошибки, `/api/health`

**Кто:** Семён · **Ветка:** `semyon/skeleton` · **Папка:** `backend/` · **Зависит от:** ничего. **Делай первой — на ней стоят остальные.**

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S1-backend-skeleton.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Каркас, на который Семён и Егор вешают код, и ручка, которой проверяют «бэк жив».

## Что сделать
1. Структура (CONTRACTS §1):
   ```
   backend/app/__init__.py
   backend/app/main.py          # create_app(), подключение роутеров
   backend/app/settings.py      # DATASETS_DIR, DATA_DIR (CONTRACTS §3), значения по умолчанию для локального запуска
   backend/app/errors.py        # ApiError(code, message, status) + обработчики
   backend/app/routers/health.py
   backend/pipeline/__init__.py # пустой пакет — Егор наполнит (если Егор уже создал — не трогай)
   backend/tests/api/test_health.py
   backend/requirements.txt
   backend/pytest.ini           # pythonpath = .
   ```
2. `requirements.txt` (версии зафиксируй, посмотри свежие в Context7/PyPI): `fastapi`, `uvicorn[standard]`, `pandas`, `jinja2`, `pytest`, `httpx`, `python-multipart` не нужен.
3. `GET /api/health` → `{"status": "ok"}`.
4. **Формат ошибок** строго из `docs/api.md` («Ошибки»): `{"error": {"code": "...", "message": "..."}}`.
   - класс `ApiError(code, message)` с таблицей `code → HTTP` (`bad_file/bad_code/no_id_column`→400, `not_found`→404, `not_ready/conflict`→409, `internal`→500);
   - обработчики: `ApiError`, `RequestValidationError` (FastAPI по умолчанию отдаёт 422 — заменить на 400 с кодом `bad_file` и понятным `message`, в котором названо поле), любое необработанное исключение → 500 `internal` (без трассировки наружу, в лог — с трассировкой);
   - исключения `pipeline.errors.PipelineError` (когда появятся) → `ApiError` с тем же `code`.
5. Заголовок `X-User`: зависимость `current_user(request) -> str` (нет заголовка → `"anonymous"`).
6. CORS для `http://localhost:5173` и `http://localhost:3000` (dev-серверы фронта).
7. `backend/var/` в `.gitignore` (корневой).
8. Запуск: `cd backend && uvicorn app.main:app --reload --port 8000`. В `README.md` корня — раздел «Как запустить» (пока без Docker, только локально; S2 дополнит).

## Тесты (`httpx`/`TestClient`)
`/api/health` = 200; несуществующая ручка → ошибка в нашем формате (`not_found`, 404); `ApiError("conflict", ...)` отдаёт 409 в нужном виде; исключение внутри ручки → 500 `internal` без стектрейса в теле.

## Готово, когда
`pytest` зелёный, `curl localhost:8000/api/health` отвечает, в Swagger (`/docs`) видна ручка.

## Не делай
Ни одной другой ручки.
