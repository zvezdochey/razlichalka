"""Слой разрезов: одна строка на заявку -> segments.csv (CONTRACTS §2.3, §4).

Читает оба среза прямо из JSON (не из normalized-CSV).

Пути полей (откуда решение, продукты, выдача, модель PD, …) — не здесь, а в карте полей встроенной процедуры
`backend/procedures/builtin_segments.py` (FIELD_MAP). Ниже имена полей в объяснениях — по этой карте.

Правило «того же продукта» (от него берутся модель, порог, причина отказа, тип партнёра, способ маршрутизации):
    берём продукт на первой позиции выдачи (оффер с минимальным `rank` в `available_offers`);
    если выдачи нет — продукт с наименьшим `product_id` из `product_trials`.
Правило применяется к каждому срезу отдельно и одинаково для обоих.
`PARTNER_TYPE` и `ROUTING_METHOD` — одна колонка на два среза, а у продуктов внутри заявки они разные,
поэтому берём их у продукта из того среза, где у заявки есть выдача: есть в BEFORE (или в обоих) — из BEFORE,
есть только в AFTER — из AFTER (так у REJECT->APPROVE это одобренный продукт); выдачи нет нигде — у продукта
с наименьшим `product_id` (из BEFORE, а если там пусто — из AFTER).
`PRODUCTS` — продукты из обоих срезов вместе.

Нет поля -> пустая ячейка (не `None` и не ошибка).

`CHANGE_SOURCE` (E10, сценарий 4 ТЗ: «из-за логики или из-за входных данных?») — по витрине сравнения:
    data  — есть различие (DIFF_FLAG=1) во входе: путь начинается с префикса из INPUT_PREFIXES
            (`builtin_segments.py`: данные заявки и ответы внешних источников);
    logic — различия есть, но только в том, что посчитала СПР;
    none  — различий нет совсем.
`both` («вход поменялся, но решение поменялось сильнее, чем объясняет вход») пока не считаем: честного
критерия нет, а на этом датасете у всех заявок с другим входом смена решения ровно им и объясняется.
Технические поля (`ignore_paths`) в витрину не попадают, поэтому и здесь не считаются.

CLI для себя (из папки backend/):
    python -m pipeline.segments <папка_датасета> <out.csv> [comparison.csv]
"""

import json
import sys
import time
from pathlib import Path

from .csvio import read_csv, write_csv
from .dataset import list_source_files
from .errors import BadFile, Cancelled
from .procedures import load_builtin, load_builtin_value

COLUMNS = [
    "APP_ID", "DECISION_BEFORE", "DECISION_AFTER", "DECISION_CHANGED", "PRODUCTS",
    "TOP_OFFER_BEFORE", "TOP_OFFER_AFTER", "PARTNER_TYPE", "ROUTING_METHOD",
    "PD_MODEL_BEFORE", "PD_MODEL_AFTER", "CUTOFF_BEFORE", "CUTOFF_AFTER",
    "REJECT_REASON_BEFORE", "REJECT_REASON_AFTER", "SCORE_OKB_BEFORE", "SCORE_OKB_AFTER",
    "CHANGE_SOURCE",
]
# Словарь CHANGE_SOURCE (docs/api.md, «Общие словари»). `both` зарезервирован, сейчас не выдаём.
CHANGE_SOURCES = ("logic", "data", "both", "none")

PROGRESS_EVERY = 50

# Встроенная процедура с картой полей (backend/procedures/builtin_segments.py)
BUILTIN = "builtin_segments"
# Поля «того же продукта» — читаются у выбранного продукта, а не из ответа целиком
PRODUCT_FIELDS = ("PARTNER_TYPE", "ROUTING_METHOD", "PD_MODEL", "CUTOFF", "REJECT_REASON")


def _text(value) -> str:
    """Значение -> ячейка CSV: нет значения — пусто, true/false — в нижнем регистре."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return ""  # в разрезах нужны только скаляры
    return str(value)


def normalize_decision(raw: str) -> str:
    """APPROVE → approve, REJECT → reject, всё остальное (VERIFICATION, пусто...) → other.

    Одно правило на весь pipeline: по нему и DECISION_CHANGED в segments.csv, и decision_change
    в summary.json — иначе разрезы и итоги показали бы жюри разные цифры (VERIFICATION → MANUAL).
    """
    value = (raw or "").strip().lower()
    return value if value in ("approve", "reject") else "other"


def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _num(value):
    """Число для сортировки (rank/product_id могут прийти строкой); не число -> None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _min_key(value):
    """Ключ сортировки: числа по возрастанию, всё остальное — после них."""
    n = _num(value)
    return (0, n, "") if n is not None else (1, 0, _text(value))


def _walk(obj, path: str) -> list:
    """Все значения по пути `a.b[].c`: шаг с `[]` раскрывает массив. Нет поля или не тот тип — пропускаем."""
    values = [obj]
    for step in path.split("."):
        is_array = step.endswith("[]")
        key = step[:-2] if is_array else step
        nxt = []
        for v in values:
            v = v.get(key) if isinstance(v, dict) else None
            if is_array:
                nxt.extend(v if isinstance(v, list) else [])
            elif v is not None:
                nxt.append(v)
        values = nxt
    return [v for v in values if v is not None]


def segment_field_map(overrides: dict | None = None, procedures_dir=None) -> dict:
    """Карта полей встроенной процедуры `builtin_segments`, перекрытая `overrides` (то, что задано, — заменяет)."""
    return {**load_builtin(BUILTIN, procedures_dir), **(overrides or {})}


def read_field(doc: dict, name: str, fmap: dict | None = None):
    """Значение поля `name` из ответа СПР по карте полей (без карты — встроенная).

    Путь без `[]` — одно значение или None; путь с `[]` — список значений по всем элементам массива.
    Поля нет в карте или путь пустой — None.
    Нужна и карточке заявки (I3): те же пути, что у разрезов.
    """
    path = (fmap if fmap is not None else segment_field_map()).get(name) or ""
    if not path:
        return None
    values = _walk(doc, path)
    if "[]" in path:
        return values
    return values[0] if values else None


def input_prefixes(procedures_dir=None) -> list[str]:
    """Префиксы путей входа (INPUT_PREFIXES из `builtin_segments.py`), без `[]` на конце сегментов."""
    prefixes = load_builtin_value(BUILTIN, "INPUT_PREFIXES", procedures_dir)
    if not isinstance(prefixes, (list, tuple)) or not all(isinstance(x, str) and x for x in prefixes):
        raise BadFile(f"процедура {BUILTIN}: INPUT_PREFIXES должен быть списком непустых строк")
    return [x.replace("[]", "") for x in prefixes]


def is_input_path(path: str, prefixes: list[str]) -> bool:
    """Путь витрины — вход? `ext_data[].body.x` подходит к префиксу `ext_data`, `ext_database.x` — нет."""
    plain = path.replace("[]", "")
    return any(plain == p or plain.startswith(p + ".") for p in prefixes)


def _read_comparison(comparison_csv: Path):
    cmp_ = read_csv(Path(comparison_csv))
    missing = [c for c in ("APP_ID", "PATH", "DIFF_FLAG") if c not in cmp_.columns]
    if missing:
        raise BadFile(f"В файле {Path(comparison_csv).name} нет колонок: {', '.join(missing)}")
    return cmp_


def change_sources(comparison_csv: Path, prefixes: list[str]) -> dict[str, str]:
    """{APP_ID: "data" | "logic"} по витрине сравнения. Заявок без различий в ответе нет — у них `none`."""
    return _sources(_read_comparison(comparison_csv), prefixes)


def _sources(cmp_, prefixes: list[str]) -> dict[str, str]:
    diff = cmp_[cmp_["DIFF_FLAG"] == "1"]
    # для каждого разного PATH один раз решаем, вход это или нет
    inputs = {path for path in diff["PATH"].unique() if is_input_path(path, prefixes)}
    with_input = set(diff.loc[diff["PATH"].isin(inputs), "APP_ID"])
    return {app: ("data" if app in with_input else "logic") for app in diff["APP_ID"].unique()}


def _split_array(fmap: dict, name: str) -> tuple[str, str]:
    """`a.items[].id` -> ("a.items[]", "id"): массив и поле внутри элемента. Нет `[]` — понятная ошибка."""
    path = fmap.get(name) or ""
    head, sep, tail = path.partition("[].")
    if not sep or not tail:
        raise BadFile(f"карта полей разрезов: {name} должен указывать на поле элемента массива "
                      f"(вида «a.items[].id»), а сейчас {path!r}")
    return head + "[]", tail


def _check_map(fmap: dict) -> dict:
    """Разбирает карту один раз на весь срез: где массив продуктов, где выдача, какие поля у продукта."""
    products, product_id = _split_array(fmap, "PRODUCTS")
    offers, offer_id = _split_array(fmap, "TOP_OFFER")
    rank_arr, rank = _split_array(fmap, "OFFER_RANK")
    if rank_arr != offers:
        raise BadFile(f"карта полей разрезов: OFFER_RANK и TOP_OFFER должны быть в одном массиве "
                      f"({rank_arr} ≠ {offers})")
    product_fields = {}
    for name in PRODUCT_FIELDS:
        path = fmap.get(name) or ""
        # поле продукта — относительно элемента массива продуктов; иначе читаем из ответа целиком
        if path.startswith(products + "."):
            product_fields[name] = ("product", path[len(products) + 1:])
        elif "[]" in path:
            # массив, но не массив продуктов: «первый элемент» был бы чужим продуктом — молча врать нельзя
            raise BadFile(f"карта полей разрезов: {name} = {path!r} — поле продукта должно лежать "
                          f"в массиве продуктов {products} (как PRODUCTS) или вне массивов")
        else:
            product_fields[name] = ("doc", path)
    return {"products": products, "product_id": product_id, "offers": offers, "offer_id": offer_id,
            "rank": rank, "product_fields": product_fields, "fmap": fmap}


def _first(obj, path: str):
    values = _walk(obj, path) if path else []
    return values[0] if values else None


def _extract(doc: dict, plan: dict) -> dict:
    """Что нужно из одного ответа одного среза. Пути — из карты полей (`plan` = `_check_map`)."""
    pid, oid = plan["product_id"], plan["offer_id"]
    trials = _dicts(_walk(doc, plan["products"]))
    offers = [o for o in _dicts(_walk(doc, plan["offers"])) if _first(o, oid) is not None]

    rank = plan["rank"]
    top_offer = min(offers, key=lambda o: (_min_key(_first(o, rank)), _min_key(_first(o, oid)))) if offers else None
    top_id = _first(top_offer, oid) if top_offer else None

    # «тот же продукт»: первый в выдаче, иначе наименьший id из прогонов продуктов
    by_id = {}
    for t in trials:
        by_id.setdefault(_text(_first(t, pid)), t)
    if top_id is not None:
        product = by_id.get(_text(top_id))
    else:
        with_id = [t for t in trials if _first(t, pid) is not None]
        product = min(with_id, key=lambda t: _min_key(_first(t, pid))) if with_id else None

    def product_field(name: str) -> str:
        where, path = plan["product_fields"][name]
        return _text(_first(product, path) if where == "product" else _first(doc, path))

    ids = sorted({_first(t, pid) for t in trials if _first(t, pid) is not None}, key=_min_key)
    return {
        "decision": _text(read_field(doc, "DECISION", plan["fmap"])),
        "products": [_text(i) for i in ids],
        "top_offer": _text(top_id),
        "partner_type": product_field("PARTNER_TYPE"),
        "routing_method": product_field("ROUTING_METHOD"),
        "pd_model": product_field("PD_MODEL"),
        "cutoff": product_field("CUTOFF"),
        "reject_reason": product_field("REJECT_REASON"),
        "score_okb": _text(read_field(doc, "SCORE_OKB", plan["fmap"])),
    }


def _read(file: Path) -> dict:
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BadFile(f"файл {file.name} не разобрать: {e}") from None
    if not isinstance(doc, dict):
        raise BadFile(f"файл {file.name}: ожидался JSON-объект")
    return doc


def _row(app_id: str, before: dict, after: dict, change_source: str) -> dict:
    # по приведённым решениям, как в summary.json: VERIFICATION → MANUAL — это не смена (обе other)
    changed = normalize_decision(before["decision"]) != normalize_decision(after["decision"])
    # партнёр и маршрутизация — из среза, где есть выдача (в BEFORE приоритет)
    partner_src = after if (not before["top_offer"] and after["top_offer"]) else before
    partner_alt = before if partner_src is after else after
    return {
        "APP_ID": app_id,
        "DECISION_BEFORE": before["decision"],
        "DECISION_AFTER": after["decision"],
        "DECISION_CHANGED": "1" if changed else "0",
        "PRODUCTS": "|".join(sorted(set(before["products"]) | set(after["products"]), key=_min_key)),
        "TOP_OFFER_BEFORE": before["top_offer"],
        "TOP_OFFER_AFTER": after["top_offer"],
        "PARTNER_TYPE": partner_src["partner_type"] or partner_alt["partner_type"],
        "ROUTING_METHOD": partner_src["routing_method"] or partner_alt["routing_method"],
        "PD_MODEL_BEFORE": before["pd_model"],
        "PD_MODEL_AFTER": after["pd_model"],
        "CUTOFF_BEFORE": before["cutoff"],
        "CUTOFF_AFTER": after["cutoff"],
        "REJECT_REASON_BEFORE": before["reject_reason"],
        "REJECT_REASON_AFTER": after["reject_reason"],
        "SCORE_OKB_BEFORE": before["score_okb"],
        "SCORE_OKB_AFTER": after["score_okb"],
        "CHANGE_SOURCE": change_source,
    }


def build_segments(dataset_dir: Path, out_csv: Path, *, field_map: dict | None = None, procedures_dir=None,
                   comparison_csv: Path | None = None,
                   on_progress=None, log=None, is_cancelled=None) -> int:
    """Пишет segments.csv, по строке на заявку (заявки — файлы среза BEFORE). Возвращает число строк.

    Всё после `out_csv` — только по имени (`field_map=...`), чтобы новый параметр не сдвинул чужие вызовы.
    `field_map` — пути, которые заменяют пути встроенной карты полей (`builtin_segments`);
    без неё — встроенная карта целиком. `procedures_dir` — папка встроенных процедур (из app/settings.py).
    `comparison_csv` — витрина сравнения для колонки CHANGE_SOURCE; без неё колонка пустая.

    Заявки — только с парой (E15): с витриной — те, что есть в витрине (сравнение уже выкинуло заявки
    без пары и посчитало их в unpaired.json); без витрины (CLI) — те, у которых есть файл в обоих срезах,
    и битый файл тогда — ошибка BadFile (в запуске витрина есть всегда).
    """
    plan = _check_map(segment_field_map(field_map, procedures_dir))
    after_by_id = {f.stem: f for f in list_source_files(dataset_dir, "AFTER")}
    all_before = list_source_files(dataset_dir, "BEFORE")
    sources = None
    if comparison_csv is not None:
        cmp_ = _read_comparison(comparison_csv)
        sources = _sources(cmp_, input_prefixes(procedures_dir))
        paired = set(cmp_["APP_ID"])
    else:
        paired = {f.stem for f in all_before} & set(after_by_id)
    before_files = [f for f in all_before if f.stem in paired and f.stem in after_by_id]
    total = len(before_files)

    def say(level: str, message: str) -> None:
        if log:
            log(level, message)

    skipped = len({f.stem for f in all_before} | set(after_by_id)) - total  # заявки, а не файлы
    if skipped:
        say("warn", f"Заявок без пары в срезах: {skipped} — в разрезы не попали")

    # заявки, где решение изменилось, а различий в витрине нет; заполняет rows(), в журнал — одним сообщением
    no_diffs: list[str] = []

    def rows():
        for done, file in enumerate(before_files, start=1):
            if is_cancelled and is_cancelled():
                raise Cancelled()
            before = _extract(_read(file), plan)
            after = _extract(_read(after_by_id[file.stem]), plan)
            # заявки нет среди различий витрины (или нет в витрине совсем) — значит различий нет: none
            source = "" if sources is None else sources.get(file.stem, "none")
            row = _row(file.stem, before, after, source)
            if source == "none" and row["DECISION_CHANGED"] == "1":
                no_diffs.append(file.stem)  # так быть не должно: решение само есть в витрине
            yield row
            if done % PROGRESS_EVERY == 0 or done == total:
                if on_progress:
                    on_progress(done)
                say("info", f"Разрезы: обработано {done} из {total}")

    say("info", f"Разрезы: {total} заявок")
    n = write_csv(Path(out_csv), COLUMNS, rows())
    if no_diffs:
        # одно сообщение на весь этап, а не по строке на заявку
        say("warn", f"У {len(no_diffs)} заявок решение изменилось, а различий в витрине нет "
                    f"(путь решения в ignore_paths?): {', '.join(no_diffs[:5])}"
                    + (f" и ещё {len(no_diffs) - 5}" if len(no_diffs) > 5 else ""))
    return n


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("Использование: python -m pipeline.segments <папка_датасета> <out.csv> [comparison.csv]")
        return 1
    start = time.time()
    n = build_segments(Path(argv[0]), Path(argv[1]), comparison_csv=Path(argv[2]) if len(argv) == 3 else None,
                       log=lambda lvl, msg: print(f"[{lvl}] {msg}"))
    print(f"Готово: {n} строк за {time.time() - start:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
