# E3. Приведение всего среза в CSV

**Кто:** Егор · **Ветка:** `egor/normalize` · **Папка:** `backend/pipeline/` · **Зависит от:** E1, E2 (E4 — по возможности; без неё `adjust=None`)

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E3-normalize-dataset.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Это этап `normalize` из `docs/api.md` п. 6: 2002 JSON-файла среза → один `normalized_<СРЕЗ>.csv`. Эту функцию Семён вызывает из фонового запуска и показывает прогресс.

## Что прочитать
- `docs/tasks/CONTRACTS.md` — разделы 2, 4, 5
- `ПАКЕТ/ЗАДАНИЕ/data/RUN-20260827-0001/manifest.json` — как устроен датасет
- `backend/pipeline/flatten.py`, `array_rules.py`

## Что сделать
1. `backend/pipeline/csvio.py`:
   - `write_csv(path, fieldnames, rows_iterable)` — `;`, `utf-8-sig`, `newline=""`, пишет потоком (не держит всё в памяти);
   - `read_csv(path) -> pandas.DataFrame` — все колонки как строки (`dtype=str`, `keep_default_na=False`), чтобы `null`/`NA` не превращались в NaN.
2. `backend/pipeline/dataset.py`:
   - `read_manifest(dataset_dir: Path) -> dict` — читает `manifest.json`, ошибка `BadFile` с понятным текстом, если нет файла/поля;
   - `list_source_files(dataset_dir, source) -> list[Path]` — файлы среза (`srez.<SOURCE>.dir` из манифеста), отсортированные. Имя файла без `.json` = `APP_ID`.
3. `backend/pipeline/normalize.py`: `normalize_dataset(...)` ровно по сигнатуре из CONTRACTS §4:
   - собирает правила: `merge_array_rules(DEFAULT_ARRAY_RULES, parse_cfg["array_modes"])`;
   - бакеты: если E4 уже слита — `make_adjuster(parse_cfg["buckets"])`, иначе `None`;
   - идёт по файлам, на каждый вызывает `flatten_response`, пишет строки в CSV;
   - каждые ~50 файлов вызывает `on_progress(done)` и `log("info", "Обработано N из M")`; перед каждым файлом проверяет `is_cancelled()` → `raise Cancelled`;
   - битый JSON, а также `appData.application_id` не совпадает с именем файла → `BadFile` с именем файла в тексте; молча не пропускать;
   - возвращает число строк.
4. CLI для себя: `python -m pipeline.normalize <папка_датасета> <срез> <out.csv>`.

## Тесты
- `backend/tests/fixtures/dataset_mini/` — выдуманный датасет на 3 заявки × 2 среза с `manifest.json` (несколько строк JSON руками, **не** копия данных организаторов).
- `test_normalize.py`: CSV создаётся, колонки как в CONTRACTS §2.1, нет дублей ключа, `ignore_paths` вырезает тех. поля, `is_cancelled=lambda: True` → `Cancelled`, битый файл → `BadFile`.
- С `skipif`: на настоящем датасете оба среза за приемлемое время (замерь и напиши в PR; хорошо — до минуты на срез).

## Готово, когда
- Оба среза настоящего датасета превращаются в CSV, в каждом ~145 тысяч строк, `request_id`/`createDateTime` нет.
- Тесты зелёные, FastAPI не импортируется.

## Не делай
Сравнение срезов (E5), разрезы (E6).
