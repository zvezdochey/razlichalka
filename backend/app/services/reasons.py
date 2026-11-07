"""Причины отказа по продуктам заявок со сменой решения на reject."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.services import app_card, facts, results

SOURCES = {"CUTOFF": "cutoff", "HARDCHECK": "rule"}
_lock = Lock()


@dataclass
class ReasonGroup:
    affected: int = 0
    app_ids: set[str] = field(default_factory=set)
    thresholds: set[float] = field(default_factory=set)


def _named_reason(product: dict) -> tuple[str, str] | None:
    kind = (product["reject_reason"] or "").upper()
    if kind not in SOURCES:
        return None
    name = product["reject_reason_code"]
    if name is None and kind == "CUTOFF":
        name = product["cutoff"]["name"]
    if name is None and kind == "HARDCHECK":
        hits = {rule["name"] for rule in product["rules"] if rule["hit"] is True}
        if len(hits) == 1:
            name = next(iter(hits))
    return (kind, name) if name else None


def _reason_text(kind: str, name: str, thresholds: set[float]) -> str:
    if kind == "HARDCHECK":
        return f"Стоп-фактор {name}"
    if len(thresholds) == 1:
        return f"Отсечка {name} (порог {next(iter(thresholds)):g})"
    return f"Отсечка {name}"


def reasons(run_dir: Path, dataset_dir: Path) -> dict:
    # Второй запрос проверяет кэш после того, как первый закончит расчёт.
    with _lock:
        return _cached_reasons(run_dir, dataset_dir)


@lru_cache(maxsize=8)
def _cached_reasons(run_dir: Path, dataset_dir: Path) -> dict:
    decisions = results.app_decisions(run_dir)
    counts = Counter(decisions.loc[decisions["decision_change"] != "same", "change_source"])
    by_source = {source: counts[source] for source in ("logic", "data", "both")}
    rejected = decisions.index[decisions["decision_change"] == "approve_to_reject"]
    if rejected.empty:
        return {"reasons": [], "unexplained": 0, "by_source": by_source}

    after_files = app_card.source_index(dataset_dir, "AFTER")
    fields = app_card.card_fields()
    groups: dict[tuple[str, str], ReasonGroup] = defaultdict(ReasonGroup)
    explained = set()
    for app_id in rejected:
        path = after_files.get(app_id)
        if path is None:
            continue
        for product in app_card.read_slice(path, fields)["products"]:
            key = _named_reason(product)
            if key is None:
                continue
            group = groups[key]
            group.affected += 1
            group.app_ids.add(app_id)
            explained.add(app_id)
            threshold = product["cutoff"]["value"]
            if key[0] == "CUTOFF" and threshold is not None:
                group.thresholds.add(threshold)

    total = sum(group.affected for group in groups.values())
    rows = []
    for (kind, name), group in sorted(groups.items(), key=lambda item: (-item[1].affected, item[0])):
        rows.append({
            "text": _reason_text(kind, name, group.thresholds),
            "source": SOURCES[kind],
            "rule": name,
            "affected": group.affected,
            "share": round(group.affected / total, 3),
            "app_ids_ref": facts.make_apps_ref(run_dir, sorted(group.app_ids)),
        })
    return {"reasons": rows, "unexplained": len(rejected) - len(explained), "by_source": by_source}
