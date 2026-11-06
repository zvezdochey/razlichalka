# E6. Слой разрезов: одна строка на заявку → `segments.csv`

**Кто:** Егор · **Ветка:** `egor/segments` · **Папка:** `backend/pipeline/` · **Зависит от:** `dataset.py` из E3 (читать список файлов); можно начать параллельно, написав временный листинг

**Запуск в новом чате:** «Выполни задачу из `docs/tasks/egor/E6-segments.md`. Сначала прочитай `AGENTS.md` и `docs/tasks/CONTRACTS.md`.»

## Зачем
Витрина отвечает «что изменилось», разрезы — «у кого». Из них берутся решение до/после, модель, порог, причина отказа для списка заявок (`docs/api.md` п. 7.4) и счётчиков (п. 7.1).

## Что прочитать
- `docs/tasks/CONTRACTS.md` — §2.3, §4
- `ПАКЕТ/ЗАДАНИЕ/docs/СХЕМА_ВИТРИНЫ.md` — раздел 2
- `ПАКЕТ/ЗАДАНИЕ/docs/ФОРМАТ_ОТВЕТА.md` — «Что означают поля»
- 3–4 файла из датасета, в том числе заявка, где решение изменилось (`I32554354` — `REJECT → APPROVE`, `I32554362` — `APPROVE → REJECT`)

## Что сделать
`backend/pipeline/segments.py`: `build_segments(dataset_dir, out_csv, on_progress=None, log=None, is_cancelled=None) -> int`.

Читает **оба** среза напрямую из JSON (не из CSV), на каждую заявку одна строка:

| Поле | Откуда |
|---|---|
| `DECISION_BEFORE/AFTER` | `decisionResult.decision` |
| `DECISION_CHANGED` | `1`, если решения различаются |
| `PRODUCTS` | `product_id` из `product_trials[]`, через `|`, по возрастанию |
| `TOP_OFFER_BEFORE/AFTER` | `product_id` оффера с минимальным `rank` в `available_offers[]`; нет офферов — пусто |
| `PARTNER_TYPE` | `partner_type` продукта на первой позиции (если офферов нет — первый продукт из `product_trials`) |
| `ROUTING_METHOD` | `routing_method` того же продукта |
| `PD_MODEL_BEFORE/AFTER` | `scoring.pd.modelName` того же продукта в соответствующем срезе |
| `CUTOFF_BEFORE/AFTER` | `cutOff.name` того же продукта |
| `REJECT_REASON_BEFORE/AFTER` | `rejectReason` (`HARDCHECK`/`CUTOFF`) того же продукта; пусто, если продукт не отказан |
| `SCORE_OKB_BEFORE/AFTER` | `characteristics.score_okb` |

Выбор «того же продукта» — главная неоднозначность. Зафиксируй правило одной фразой в docstring
(рекомендация: продукт на первой позиции выдачи; если выдачи нет — продукт с наименьшим `product_id`
из `product_trials`) и **одинаково применяй к обоим срезам**. Если после проверки на данных видишь, что правило
плохо описывает реальность, — предложи другое в описании PR, не молчи.

Отсутствующие поля → пустая ячейка, не `None` и не ошибка.

## Тесты (`test_segments.py`)
Мини-датасет из `backend/tests/fixtures/dataset_mini/` (создаётся в E3; если его ещё нет — создай и положи, второй раз не создавай):
решение сменилось / не сменилось; нет офферов; нет `score_okb`; два оффера у одного продукта (`standard` и `manual`).
На настоящем датасете (`skipif`): 2002 строки, `DECISION_CHANGED=1` ровно у **385** заявок
(273 `APPROVE→REJECT` + 112 `REJECT→APPROVE` — цифры из `docs/api.md` п. 7.1).

## Готово, когда
`segments.csv` на настоящих данных: 2002 строки, 385 смен решения, уникальные `APP_ID`.

## Не делай
Сводки/счётчики — E7. Не меняй `docs/api.md` — если число не сошлось, скажи Семёну.
