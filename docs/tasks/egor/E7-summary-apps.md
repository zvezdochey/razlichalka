# E7. Итоги и таблица заявок → `summary.json`, `apps.csv`

**Кто:** Егор · **Ветка:** `egor/summary` · **Папка:** `backend/pipeline/` · **Зависит от:** форматы E5 и E6 (достаточно мини-CSV руками; на настоящих — после их слияния)

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E7-summary-apps.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Этап `aggregate` из `docs/api.md` п. 6. Готовим то, что Семён отдаёт фронту: счётчики сверху (п. 7.1) и таблицу заявок (п. 7.4).

## Что прочитать
- `docs/tasks/CONTRACTS.md` — §2.2–2.5, §4
- `docs/api.md` — п. 7.1 и 7.4 (формат и **словари** `decision`, `decision_change`)

## Что сделать
`backend/pipeline/summary.py`:

1. `normalize_decision(raw: str) -> str` — `APPROVE`→`approve`, `REJECT`→`reject`, всё остальное (в т.ч. `VERIFICATION`, пусто, другой регистр с пробелами) → `other`. Регистр и пробелы не важны.
2. `decision_change(before: str, after: str) -> str` — по таблице в `docs/api.md` («Решение изменилось»): `same` / `approve_to_reject` / `reject_to_approve` / `decision_other`.
3. `build_summary(comparison_csv, segments_csv, out_summary_json, out_apps_csv, log=None) -> dict`:
   - `apps.csv` — одна строка на заявку, колонки как CONTRACTS §2.4; `attributes_changed` = число строк `DIFF_FLAG=1` этой заявки; пустые значения разрезов остаются пустыми;
   - `summary.json` — ровно формат п. 7.1: `applications`, `applications_changed` (есть хотя бы одно различие), `applications_changed_share` (округлить до 3 знаков), `decision_changed`, `decision_changes{...4 ключа, нули тоже}`, `attributes{VALUE_CHANGED, ATTRIBUTE_NEW, ATTRIBUTE_LOST}`;
   - заявки без строк в витрине (если такие есть) всё равно попадают в `apps.csv` с `attributes_changed=0`;
   - возвращает тот же словарь, что записал.

## Тесты (`test_summary.py`)
- Мини-CSV руками (3–4 заявки): `normalize_decision` для разных написаний, `decision_change` для всех 4 значений, счётчики сходятся с вручную посчитанными.
- На настоящем датасете (`skipif`, нужны результаты E3/E5/E6): `applications=2002`, `decision_changed=385`, `decision_changes` = 1617 / 273 / 112 / 0.
  Числа `applications_changed` и `attributes` из `docs/api.md` помечены как ориентир (там сравнение было по позиции массивов) — **твои будут другими, это нормально**. Выведи свои числа в описание PR, Семён обновит `docs/api.md`.

## Готово, когда
Файлы созданы, `summary.json` проходит сравнение по набору ключей с примером из `docs/api.md`, тесты зелёные.

## Не делай
Фильтры, сортировка, пагинация — это в ручке у Семёна (S6). Факты для сводной (п. 7.2) — после MVP.
