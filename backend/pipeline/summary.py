"""Итоги и таблица заявок (E7): comparison.csv + segments.csv → summary.json + apps.csv.

Этап `aggregate`. Формат summary.json — `docs/api.md` п. 7.1, apps.csv — CONTRACTS §2.4.
Решения приводим к словарю `approve` / `reject` / `other` (регистр и пробелы не важны).
Заявка «с различием» — есть хотя бы одна строка витрины с DIFF_FLAG=1.
Список заявок берём из segments.csv (одна строка на заявку), поэтому заявки без строк
в витрине тоже попадают в apps.csv — с attributes_changed=0.
"""

import json
import os
from pathlib import Path

from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile

# Порядок колонок — CONTRACTS §2.4
APPS_COLUMNS = [
    "app_id", "decision_before", "decision_after", "decision_change", "attributes_changed",
    "pd_model_before", "pd_model_after", "cutoff_before", "cutoff_after",
    "reject_reason_before", "reject_reason_after",
]
CHANGE_TYPES = ["VALUE_CHANGED", "ATTRIBUTE_NEW", "ATTRIBUTE_LOST"]
DECISION_CHANGES = ["same", "approve_to_reject", "reject_to_approve", "decision_other"]
# колонка apps.csv ← колонка segments.csv (переносим как есть)
_COPY = {
    "pd_model_before": "PD_MODEL_BEFORE", "pd_model_after": "PD_MODEL_AFTER",
    "cutoff_before": "CUTOFF_BEFORE", "cutoff_after": "CUTOFF_AFTER",
    "reject_reason_before": "REJECT_REASON_BEFORE", "reject_reason_after": "REJECT_REASON_AFTER",
}


def normalize_decision(raw: str) -> str:
    """APPROVE → approve, REJECT → reject, всё остальное (VERIFICATION, пусто...) → other."""
    value = (raw or "").strip().lower()
    return value if value in ("approve", "reject") else "other"


def decision_change(before: str, after: str) -> str:
    """Что случилось с решением: same / approve_to_reject / reject_to_approve / decision_other.

    Принимает и сырые значения (`APPROVE`), и уже приведённые (`approve`).
    """
    b, a = normalize_decision(before), normalize_decision(after)
    if b == a:
        return "same"
    if (b, a) == ("approve", "reject"):
        return "approve_to_reject"
    if (b, a) == ("reject", "approve"):
        return "reject_to_approve"
    return "decision_other"


def _need(df, columns: list[str], name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise BadFile(f"В файле {name} нет колонок: {', '.join(missing)}")


def build_summary(comparison_csv: Path, segments_csv: Path, out_summary_json: Path,
                  out_apps_csv: Path, log=None) -> dict:
    """Пишет summary.json и apps.csv. Возвращает тот же словарь, что записан в summary.json."""
    comparison = read_csv(comparison_csv)
    segments = read_csv(segments_csv)
    _need(comparison, ["APP_ID", "DIFF_FLAG", "CHANGE_TYPE"], "comparison.csv")
    _need(segments, ["APP_ID", "DECISION_BEFORE", "DECISION_AFTER"] + list(_COPY.values()), "segments.csv")

    # Различия: по заявке — число строк DIFF_FLAG=1; по типам — для всего запуска
    diff = comparison[comparison["DIFF_FLAG"] == "1"]
    per_app = diff.groupby("APP_ID").size().to_dict()
    by_type = diff["CHANGE_TYPE"].value_counts().to_dict()

    changes = dict.fromkeys(DECISION_CHANGES, 0)

    def rows():
        for rec in segments.to_dict("records"):
            before = normalize_decision(rec["DECISION_BEFORE"])
            after = normalize_decision(rec["DECISION_AFTER"])
            change = decision_change(before, after)
            changes[change] += 1
            row = {
                "app_id": rec["APP_ID"], "decision_before": before, "decision_after": after,
                "decision_change": change,
                "attributes_changed": per_app.get(rec["APP_ID"], 0),
            }
            row.update({col: rec[src] for col, src in _COPY.items()})
            yield row

    write_csv(out_apps_csv, APPS_COLUMNS, rows())

    total = len(segments)
    changed = int(segments["APP_ID"].isin(per_app).sum())
    summary = {
        "applications": total,
        "applications_changed": changed,
        "applications_changed_share": round(changed / total, 3) if total else 0.0,
        "decision_changed": total - changes["same"],
        "decision_changes": changes,
        "attributes": {t: int(by_type.get(t, 0)) for t in CHANGE_TYPES},
    }
    # как и CSV: сначала во временный файл, потом подмена — обрыв не оставит половину JSON
    out_summary_json = Path(out_summary_json)
    tmp = out_summary_json.with_name(out_summary_json.name + ".tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out_summary_json)
    if log:
        log("info", f"Итоги: заявок {total}, с различиями {changed}, "
                    f"решение изменилось у {summary['decision_changed']}")
    return summary
