# E5. Сравнение двух срезов → `comparison.csv`

**Кто:** Егор · **Ветка:** `egor/compare` · **Папка:** `backend/pipeline/` · **Зависит от:** только формат CONTRACTS §2.1–2.2 (с E3 не связана, можно делать параллельно)

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E5-compare.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Этап `compare` из `docs/api.md` п. 6. Из двух `normalized_*.csv` строим витрину: что изменилось, что появилось, что пропало.

## Что прочитать
- `docs/tasks/CONTRACTS.md` — §2.1, §2.2, §4
- `ПАКЕТ/ЗАДАНИЕ/docs/СХЕМА_ВИТРИНЫ.md` — раздел 1 (ключ строки, `DIFF_FLAG`, `CHANGE_TYPE`)
- `ПАКЕТ/ЗАДАНИЕ/example/` — `03_normalized_BEFORE.csv`, `04_normalized_AFTER.csv`, `05_union.csv`, `06_comparison.csv`: готовый вход и **эталонный выход** для твоего теста

## Что сделать
`backend/pipeline/compare.py`: `compare_csv(before_csv, after_csv, out_csv, log=None) -> int` (возвращает число строк).

1. Читай через `csvio.read_csv` (если E3 ещё не слита — временно `pandas.read_csv(sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)`, потом замени).
2. Склей по ключу (`APP_ID`, `PATH`, `ARRAY_KEY`) полным внешним соединением (`merge(..., how="outer", indicator=True)`).
3. Для каждой строки:
   - есть с обеих сторон, `VALUE` равны → `SAME`, `DIFF_FLAG=0`;
   - есть с обеих сторон, разные → `VALUE_CHANGED`, `DIFF_FLAG=1`;
   - только в AFTER → `ATTRIBUTE_NEW`, `DIFF_FLAG=1`, `*_BEFORE` пустые;
   - только в BEFORE → `ATTRIBUTE_LOST`, `DIFF_FLAG=1`, `*_AFTER` пустые.
4. Сравнение **строго по `VALUE`**, а не по `ADJUSTED_VALUE`. Значения сравнивай как строки; `null` (строка) и «атрибута нет» — разные случаи, не путать.
5. `PREFIX/CLASS/SUFFIX/KEY` бери из той стороны, где строка есть.
6. Порядок колонок — как в CONTRACTS §2.2. Сортировка: `APP_ID`, `PATH`, `ARRAY_KEY`.
7. Оставь в `log` одну сводную строку: сколько `SAME / VALUE_CHANGED / ATTRIBUTE_NEW / ATTRIBUTE_LOST`.
8. Пустой вход (0 строк с одной из сторон) не должен падать.

## Тесты (`test_compare.py`)
- Эталон: `compare_csv(example/03_..., example/04_..., tmp)` даёт тот же набор строк, что `example/06_comparison.csv` (сравни как множество кортежей, порядок не важен). Тест с `skipif`, если `ПАКЕТ/` нет.
- Маленькие выдуманные CSV в `backend/tests/fixtures/`: по одному случаю на каждый из четырёх `CHANGE_TYPE`; изменение внутри одного бакета (`0.42 → 0.58`, одинаковый `ADJUSTED`) — всё равно `VALUE_CHANGED`.
- Производительность (`skipif`): два среза по ~145 тысяч строк — несколько секунд.

## Готово, когда
Тесты зелёные, на выходе только 4 значения `CHANGE_TYPE`, `DIFF_FLAG` ∈ {0,1}.

## Не делай
Сводки по заявкам — E7.
