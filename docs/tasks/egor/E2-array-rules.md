# E2. Правила массивов настоящего датасета

**Кто:** Егор · **Ветка:** `egor/array-rules` · **Папка:** `backend/pipeline/` · **Зависит от:** E1

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E2-array-rules.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Из ТЗ: массивы надо сопоставлять **по ключу**, а не по позиции, иначе вставка в начало даёт лавину ложных различий. Здесь зашиваем ключи всех девяти массивов датасета и проверяем, что на живых файлах не возникает дублей.

## Что прочитать
- `ПАКЕТ/ЗАДАНИЕ/docs/ФОРМАТ_ОТВЕТА.md` — таблица «Массивы: девять штук» и «На что смотреть внимательно»
- `backend/pipeline/flatten.py` (из E1)

## Что сделать
1. `backend/pipeline/array_rules.py`: константа `DEFAULT_ARRAY_RULES` — правила для **девяти** массивов:

   | Путь (с `[]`) | Режим | Ключ |
   |---|---|---|
   | `decisionResult.available_offers[]` | key | `product_id` + `type` |
   | `decisionResult.product_trials[]` | key | `product_id` |
   | `decisionResult.product_trials[].rules[]` | key | `name` |
   | `decisionResult.product_trials[].scoring.scoreModels[]` | key | `modelName` |
   | `decisionResult.scoring[]` | key | `modelName` |
   | `decisionResult.scoring[].value[]` | **index** | позиция |
   | `ext_data[]` | key | `body.action` |
   | `product_catalog[]` | key | `mfo_id` + `product_id` |
   | `tariff_matrix[]` | key | `mfo_id` + `product_id` |

   Проверь реальные имена полей в нескольких файлах — таблица из ТЗ может отличаться деталями.
2. `def merge_array_rules(defaults: dict, array_modes: dict) -> dict` — перекрывает **только режим** по путям из `parse_cfg["array_modes"]`.
3. Скрипт `backend/pipeline/tools/check_dataset.py` (запуск `python -m pipeline.tools.check_dataset <папка_датасета>`): прогоняет `flatten_response` по **всем** 4004 файлам и печатает:
   - сколько файлов, сколько строк всего (ожидание ~290 тысяч на оба среза вместе — порядок величины), min/median/max листьев на заявку (по ТЗ 131–178);
   - были ли ошибки «нет правила» / «дубль ключа» (должно быть 0);
   - сколько разных `PATH`.
4. Если нашлись массивы без правила или дубли — поправь правила, а не скрипт. Что нашёл и поменял — коротко в docstring `array_rules.py`.

## Тесты
`backend/tests/pipeline/test_array_rules.py`: `merge_array_rules` меняет режим; выдуманный мини-ответ с двумя офферами одного продукта (`standard` и `manual`) даёт две разные строки. Тест на настоящих файлах — с `skipif` на отсутствие датасета.

## Готово, когда
- Скрипт на настоящем датасете: 0 ошибок, `PATH` без дублей по ключу (`APP_ID`, `PATH`, `ARRAY_KEY`).
- Результат скрипта (числа) вставь в описание Pull Request.

## Не делай
Запись CSV и прогресс — это E3.
