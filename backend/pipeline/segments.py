"""Слой разрезов: одна строка на заявку -> segments.csv (CONTRACTS §2.3, §4).

Читает оба среза прямо из JSON (не из normalized-CSV).

Правило «того же продукта» (от него берутся модель, порог, причина отказа, тип партнёра, способ маршрутизации):
    берём продукт на первой позиции выдачи (оффер с минимальным `rank` в `available_offers`);
    если выдачи нет — продукт с наименьшим `product_id` из `product_trials`.
Правило применяется к каждому срезу отдельно и одинаково для обоих.
`PARTNER_TYPE` и `ROUTING_METHOD` — одна колонка на два среза: берём из BEFORE, а если там пусто — из AFTER.

Нет поля -> пустая ячейка (не `None` и не ошибка).

CLI для себя (из папки backend/):
    python -m pipeline.segments <папка_датасета> <out.csv>
"""

import json
import sys
import time
from pathlib import Path

from .csvio import write_csv
from .dataset import list_source_files
from .errors import BadFile, Cancelled

COLUMNS = [
    "APP_ID", "DECISION_BEFORE", "DECISION_AFTER", "DECISION_CHANGED", "PRODUCTS",
    "TOP_OFFER_BEFORE", "TOP_OFFER_AFTER", "PARTNER_TYPE", "ROUTING_METHOD",
    "PD_MODEL_BEFORE", "PD_MODEL_AFTER", "CUTOFF_BEFORE", "CUTOFF_AFTER",
    "REJECT_REASON_BEFORE", "REJECT_REASON_AFTER", "SCORE_OKB_BEFORE", "SCORE_OKB_AFTER",
]

PROGRESS_EVERY = 50


def _text(value) -> str:
    """Значение -> ячейка CSV: нет значения — пусто, true/false — в нижнем регистре."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return ""  # в разрезах нужны только скаляры
    return str(value)


def _get(obj, *path):
    """Достаёт вложенное поле; на любом шаге нет словаря или ключа -> None."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


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


def _extract(doc: dict) -> dict:
    """Что нужно из одного ответа одного среза."""
    result = doc.get("decisionResult") if isinstance(doc.get("decisionResult"), dict) else {}
    trials = _dicts(result.get("product_trials"))
    offers = [o for o in _dicts(result.get("available_offers")) if o.get("product_id") is not None]

    top_offer = min(offers, key=lambda o: (_min_key(o.get("rank")), _min_key(o.get("product_id")))) if offers else None
    top_id = top_offer.get("product_id") if top_offer else None

    # «тот же продукт»: первый в выдаче, иначе наименьший product_id из прогонов
    by_id = {}
    for t in trials:
        by_id.setdefault(_text(t.get("product_id")), t)
    if top_id is not None:
        product = by_id.get(_text(top_id))
    else:
        with_id = [t for t in trials if t.get("product_id") is not None]
        product = min(with_id, key=lambda t: _min_key(t["product_id"])) if with_id else None

    ids = sorted({t["product_id"] for t in trials if t.get("product_id") is not None}, key=_min_key)
    return {
        "decision": _text(result.get("decision")),
        "products": [_text(i) for i in ids],
        "top_offer": _text(top_id),
        "partner_type": _text(_get(product, "partner_type")),
        "routing_method": _text(_get(product, "routing_method")),
        "pd_model": _text(_get(product, "scoring", "pd", "modelName")),
        "cutoff": _text(_get(product, "cutOff", "name")),
        "reject_reason": _text(_get(product, "rejectReason")),
        "score_okb": _text(_get(doc, "characteristics", "score_okb")),
    }


def _read(file: Path) -> dict:
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BadFile(f"файл {file.name} не разобрать: {e}") from None
    if not isinstance(doc, dict):
        raise BadFile(f"файл {file.name}: ожидался JSON-объект")
    return doc


def _row(app_id: str, before: dict, after: dict) -> dict:
    changed = before["decision"] != after["decision"]
    return {
        "APP_ID": app_id,
        "DECISION_BEFORE": before["decision"],
        "DECISION_AFTER": after["decision"],
        "DECISION_CHANGED": "1" if changed else "0",
        "PRODUCTS": "|".join(sorted(set(before["products"]) | set(after["products"]), key=_min_key)),
        "TOP_OFFER_BEFORE": before["top_offer"],
        "TOP_OFFER_AFTER": after["top_offer"],
        "PARTNER_TYPE": before["partner_type"] or after["partner_type"],
        "ROUTING_METHOD": before["routing_method"] or after["routing_method"],
        "PD_MODEL_BEFORE": before["pd_model"],
        "PD_MODEL_AFTER": after["pd_model"],
        "CUTOFF_BEFORE": before["cutoff"],
        "CUTOFF_AFTER": after["cutoff"],
        "REJECT_REASON_BEFORE": before["reject_reason"],
        "REJECT_REASON_AFTER": after["reject_reason"],
        "SCORE_OKB_BEFORE": before["score_okb"],
        "SCORE_OKB_AFTER": after["score_okb"],
    }


def build_segments(dataset_dir: Path, out_csv: Path, on_progress=None, log=None, is_cancelled=None) -> int:
    """Пишет segments.csv, по строке на заявку (заявки — файлы среза BEFORE). Возвращает число строк."""
    before_files = list_source_files(dataset_dir, "BEFORE")
    after_by_id = {f.stem: f for f in list_source_files(dataset_dir, "AFTER")}
    total = len(before_files)

    def say(level: str, message: str) -> None:
        if log:
            log(level, message)

    missing = [f.stem for f in before_files if f.stem not in after_by_id]
    if missing:
        raise BadFile(f"заявки есть в BEFORE, но нет в AFTER: {', '.join(missing[:5])}"
                      + (f" и ещё {len(missing) - 5}" if len(missing) > 5 else ""))
    extra = len(after_by_id) - total
    if extra:
        say("warn", f"В AFTER лишних заявок, которых нет в BEFORE: {extra} — в разрезы не попали")

    def rows():
        for done, file in enumerate(before_files, start=1):
            if is_cancelled and is_cancelled():
                raise Cancelled()
            before = _extract(_read(file))
            after = _extract(_read(after_by_id[file.stem]))
            yield _row(file.stem, before, after)
            if done % PROGRESS_EVERY == 0 or done == total:
                if on_progress:
                    on_progress(done)
                say("info", f"Разрезы: обработано {done} из {total}")

    say("info", f"Разрезы: {total} заявок")
    return write_csv(Path(out_csv), COLUMNS, rows())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Использование: python -m pipeline.segments <папка_датасета> <out.csv>")
        return 1
    start = time.time()
    n = build_segments(Path(argv[0]), Path(argv[1]), log=lambda lvl, msg: print(f"[{lvl}] {msg}"))
    print(f"Готово: {n} строк за {time.time() - start:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
