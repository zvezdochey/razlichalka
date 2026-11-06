# S2. Docker и Docker Compose

**Кто:** Семён · **Ветка:** `semyon/docker` · **Файлы:** корень репозитория (`docker-compose.yml`, `.env.example`, `.dockerignore`), `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf` · **Зависит от:** S1 (часть A), F1 слит (часть Б)

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S2-docker.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

> Исключение из правила «работай в своей папке»: Dockerfile фронта лежит в `frontend/`. Один раз; скажи Сане, что файл появился.

## Зачем
Жюри и команда запускают проект одной командой. Датасет и `ПАКЕТ/` в Git не лежат, поэтому подключаем их томом.

## Часть А — бэк (после S1)
1. `backend/Dockerfile`: `python:3.12-slim`, ставит `requirements.txt` (слой кэшируется отдельно), копирует `backend/`, запускает **не от root** (`useradd`), `uvicorn app.main:app --host 0.0.0.0 --port 8000`. `HEALTHCHECK` через `/api/health`.
2. `docker-compose.yml` в корне, сервис `backend`:
   - порт `8000:8000`;
   - `environment`: `DATASETS_DIR=/data`, `DATA_DIR=/var/razlichalka`;
   - тома: `${DATASETS_PATH:-./ПАКЕТ/ЗАДАНИЕ/data}:/data:ro` и именованный том `razlichalka_var:/var/razlichalka` (результаты запусков переживают перезапуск);
   - `restart: unless-stopped`.
3. `.env.example`: `DATASETS_PATH=./ПАКЕТ/ЗАДАНИЕ/data` (реальный `.env` в Git не коммитим).
4. `.dockerignore`: `**/node_modules`, `**/__pycache__`, `**/.venv`, `ПАКЕТ`, `.git`, `backend/var`.
5. Проверь: `docker compose up --build`, `curl localhost:8000/api/health`; том с датасетом виден (`docker compose exec backend ls /data`); у процесса права писать в `/var/razlichalka`.

## Часть Б — фронт (после того как Саня слил F1)
1. `frontend/Dockerfile`: многоступенчатый — `node:20` собирает `npm ci && npm run build`, `nginx:alpine` отдаёт `dist/`.
2. `frontend/nginx.conf`: статика + SPA-фолбэк (`try_files $uri /index.html`), `location /api/ { proxy_pass http://backend:8000; }`. Таймауты побольше (`proxy_read_timeout 120s`). Ссылка отчёта `/runs/{id}` открывается как страница фронта, а `/api/runs/{id}/report` — это уже бэк.
3. В `docker-compose.yml` сервис `frontend`: порт `3000:80`, `depends_on: backend (healthy)`.
4. Проверка: `http://localhost:3000` открывает фронт, запросы `/api/...` идут через nginx на бэк (проверь в браузере или `curl localhost:3000/api/health`).

## Часть В — README
Раздел «Как запустить» в корневом `README.md`: требования (Docker), как положить датасет (путь по умолчанию и `.env`), `docker compose up --build`, адреса `http://localhost:3000` (интерфейс) и `http://localhost:8000/docs` (Swagger), как остановить и очистить (`docker compose down -v`), как запускать без Docker (бэк: `uvicorn`, фронт: `npm run dev`).

## Готово, когда
С чистого клона + положенных данных работает одна команда `docker compose up --build`; образ бэка не содержит датасета и `ПАКЕТ/`; `docker compose down && up` не теряет результаты прошлых запусков.

## Не делай
Не клади в образ секреты и данные организаторов. Не публикуй образы в registry.
