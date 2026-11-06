# S3. Датасеты и конфигурации

**Кто:** Семён · **Ветка:** `semyon/configs` · **Папка:** `backend/app/` · **Зависит от:** S1

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/semyon/S3-datasets-configs.md`. Сначала прочитай `AGENTS.md`, `docs/api.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Чтобы запуск было из чего создавать: фронт выбирает датасет, сохраняет конфигурацию (`docs/api.md` п. 2, 4).

## Что сделать
1. `app/services/datasets.py`: читает `DATASETS_DIR`, каждая подпапка с `manifest.json` — датасет. Поля ответа п. 2.1: `id` (= `run_id` из манифеста), `applications`, `sources` (`{"BEFORE": label, "AFTER": label}`), `technical_fields` (= `technical_fields_always_differ`). Битый манифест — датасет пропускается и пишется в лог (ручка не падает).
2. `GET /api/datasets`. Нет папки датасетов → пустой список, не 500.
3. Хранилище `app/store.py`: JSON-файлы в `DATA_DIR`, запись атомарная (во временный файл + `os.replace`), блокировка `threading.Lock` на запись. Универсальные `save(kind, id, obj)`, `load`, `list`, `delete` — S4 использует тот же модуль.
4. Конфигурации (`app/routers/configs.py`), `X-User` из `current_user`; чужие конфигурации не видны и не открываются (`not_found`):
   - `GET /api/configs` — формат п. 4.1;
   - `POST /api/configs` → 201, тело п. 4.2. Валидация (pydantic): `name` непустое, `dataset` существует (иначе `not_found`), `ignore_paths` — по умолчанию технические поля датасета, `array_modes` значения только `key|value|index`, `buckets` — списки чисел по возрастанию (иначе `bad_code`/400 с понятным текстом);
   - `normalize`/`aggregate` по умолчанию `builtin_normalize`/`builtin_aggregate`, `checks` по умолчанию `[]` (процедуры появятся после MVP; пока принимаем любые строки);
   - `GET /api/configs/{id}`, `PUT /api/configs/{id}`, `DELETE /api/configs/{id}` → 204.
   - Ответ — объект конфигурации целиком: поля п. 4.2 плюс `id`, `updated_at`.
5. В `docs/api.md` нет `GET /api/configs/{id}` — добавь этот пункт одной строкой в п. 4.3 и скажи Сане.

## Тесты
Создать → получить → изменить → удалить; чужой пользователь не видит; неизвестный датасет → 404; плохие `buckets` → 400. Датасеты — на мини-фикстуре (папка с `manifest.json`), без данных организаторов.

## Готово, когда
`curl` по всем ручкам отдаёт ровно формат `docs/api.md`; перезапуск сервера не теряет конфигурации; `pytest` зелёный.

## Не делай
Запуски (S4), процедуры (S10).
