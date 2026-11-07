"""Карточка заявки по двум исходным ответам СПР."""
import json
import math
from functools import lru_cache
from pathlib import Path

from app import settings
from app.errors import ApiError
from app.services import results
from pipeline.dataset import list_source_files
from pipeline.procedures import DEFAULT_DIR
from pipeline.segments import BUILTIN, read_field, segment_field_map
from pipeline.summary import decision_change, normalize_decision


def card_fields() -> dict:
    procedures_dir = settings.PROCEDURES_DIR
    return _card_fields(procedures_dir, _procedure_stamp(DEFAULT_DIR), _procedure_stamp(procedures_dir))


def _procedure_stamp(folder: Path) -> tuple[int, int] | None:
    try:
        stat = (folder / f"{BUILTIN}.py").stat()
    except OSError:
        return None  # Загрузчик процедуры вернёт штатный bad_file.
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=8)
def _card_fields(
    procedures_dir: Path, default_stamp: tuple[int, int] | None, configured_stamp: tuple[int, int] | None,
) -> dict:
    # Отпечатки меняют ключ, если встроенную карту обновили на диске.
    defaults = segment_field_map()
    return {**defaults, **segment_field_map(procedures_dir=procedures_dir)}


@lru_cache(maxsize=16)
def source_index(dataset_dir: Path, source: str) -> dict[str, Path]:
    """Исходные датасеты доступны бэку только на чтение и не меняются в ходе его работы."""
    return {path.stem: path for path in list_source_files(dataset_dir, source)}


def _items(doc: dict, fields: dict, key: str) -> tuple[list[dict], dict]:
    path = fields.get(key) or ""
    parent, separator, _ = path.partition("[].")
    if not separator:
        return [], {}
    prefix = parent + "[]."
    local = {name: value.removeprefix(prefix) for name, value in fields.items() if (value or "").startswith(prefix)}
    records = read_field(doc, key, {key: parent + "[]"})
    return [record for record in records if isinstance(record, dict)], local


def _text(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _product_id(value) -> int | str | None:
    return value if type(value) is int else _text(value)


def _rules(product: dict, fields: dict) -> list[dict]:
    records, local = _items(product, fields, "RULE_NAME")
    rules = []
    for record in records:
        name = _text(read_field(record, "RULE_NAME", local))
        if name is not None:
            hit = read_field(record, "RULE_HIT", local)
            rules.append({"name": name, "hit": hit if isinstance(hit, bool) else None})
    return rules


def _products(doc: dict, fields: dict) -> list[dict]:
    records, local = _items(doc, fields, "PRODUCTS")
    global_fields = {name: path for name, path in fields.items() if "[]" not in (path or "")}
    products = []
    for record in records:
        product_id = _product_id(read_field(record, "PRODUCTS", local))
        if product_id is None:
            continue

        def value(name: str):
            return read_field(record, name, local) if name in local else read_field(doc, name, global_fields)

        products.append({
            "product_id": product_id,
            "decision": normalize_decision(_text(value("PRODUCT_DECISION"))),
            "reject_reason": _text(value("REJECT_REASON")),
            "reject_reason_code": _text(value("REJECT_REASON_CODE")),
            "pd_model": _text(value("PD_MODEL")),
            "pd": _number(value("PD_VALUE")),
            "cutoff": {"name": _text(value("CUTOFF")), "value": _number(value("CUTOFF_VALUE"))},
            "rules": _rules(record, local),
        })
    return products


def _offers(doc: dict, fields: dict) -> list[dict]:
    records, local = _items(doc, fields, "TOP_OFFER")
    offers = {}
    for record in records:
        product_id = _product_id(read_field(record, "TOP_OFFER", local))
        if product_id is not None:
            kind = _text(read_field(record, "OFFER_TYPE", local))
            offers[(str(product_id), kind)] = {"product_id": product_id, "type": kind}
    return list(offers.values())


def read_slice(path: Path, fields: dict) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ApiError("not_found", "Исходный ответ заявки не найден") from None
    except (OSError, ValueError):
        raise ApiError("bad_file", "Не удалось прочитать исходный ответ заявки") from None
    if not isinstance(doc, dict):
        raise ApiError("bad_file", "Исходный ответ заявки должен быть JSON-объектом")
    return {
        "decision": normalize_decision(_text(read_field(doc, "DECISION", fields))),
        "offers": _offers(doc, fields),
        "products": _products(doc, fields),
    }


def _rule_changes(before: dict, after: dict):
    left = {rule["name"]: rule["hit"] for rule in before["rules"]}
    right = {rule["name"]: rule["hit"] for rule in after["rules"]}
    for name in dict.fromkeys((*left, *right)):
        if (left.get(name) is True) == (right.get(name) is True):
            continue
        hit, other, other_rules = ("BEFORE", "AFTER", right) if left.get(name) is True else ("AFTER", "BEFORE", left)
        if name not in other_rules:
            suffix = "правило отсутствует"
        elif other_rules[name] is None:
            suffix = "правило не вычислялось"
        else:
            suffix = "не сработал"
        yield "rule", f"Стоп-фактор {name} сработал в {hit}, в {other} {suffix}"


def _show(value) -> str:
    return "—" if value is None else str(value)


def _product_changes(before: dict, after: dict):
    yield from _rule_changes(before, after)
    left, right = before["cutoff"], after["cutoff"]
    if left != right:
        yield "cutoff", (
            f"Порог {_show(left['name'])} → {_show(right['name'])} "
            f"({_show(left['value'])} → {_show(right['value'])})"
        )

    old_model, new_model = before["pd_model"], after["pd_model"]
    old_pd, new_pd, threshold = before["pd"], after["pd"], left["value"]
    if old_model is not None and new_model is not None and old_model != new_model:
        yield "score", f"Модель PD сменилась: {old_model} → {new_model}"
    elif (
        old_model is not None and old_model == new_model and old_pd is not None and new_pd is not None
        and threshold is not None and threshold == right["value"]
        and (old_pd > threshold) != (new_pd > threshold)
    ):
        yield "score", f"PD {old_pd} → {new_pd} при пороге {threshold}"


def _changes(before: dict, after: dict, change: str, source: str) -> list[dict]:
    left = {str(p["product_id"]): p for p in before["products"]}
    right = {str(p["product_id"]): p for p in after["products"]}
    observed = []
    for product_id in dict.fromkeys((*left, *right)):
        if product_id not in left:
            observed.append(("product", f"Продукт {product_id} появился в AFTER"))
        elif product_id not in right:
            observed.append(("product", f"Продукт {product_id} исчез в AFTER"))
        else:
            observed.extend(_product_changes(left[product_id], right[product_id]))

    reasons = [
        {"text": text, "source": kind, "confidence": "high"} for kind, text in dict.fromkeys(observed)
    ]
    if change != "same" and source in ("data", "both"):
        reasons.append({
            "text": "Возможная причина — изменились входные данные заявки",
            "source": "data",
            "confidence": "low",
        })
    return reasons or [{
        "text": "Причина не найдена в решающих полях", "source": "unknown", "confidence": "low",
    }]


def app_card(run_dir: Path, dataset_dir: Path, app_id: str) -> dict:
    decisions = results.app_decisions(run_dir)
    if app_id not in decisions.index:
        raise ApiError("not_found", "Заявка не найдена")

    before_path = source_index(dataset_dir, "BEFORE").get(app_id)
    after_path = source_index(dataset_dir, "AFTER").get(app_id)
    if before_path is None or after_path is None:
        raise ApiError("not_found", "Исходный ответ заявки не найден в одном из срезов")
    fields = card_fields()
    before, after = read_slice(before_path, fields), read_slice(after_path, fields)
    change = decision_change(before["decision"], after["decision"])
    return {
        "app_id": app_id,
        "decision_change": change,
        "before": before,
        "after": after,
        "reasons": _changes(before, after, change, decisions.at[app_id, "change_source"]),
    }
