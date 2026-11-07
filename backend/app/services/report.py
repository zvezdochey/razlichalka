"""Самодостаточный HTML-отчёт по сохранённым результатам запуска."""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.errors import ApiError
from app.services import ai_review, datasets, results

templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(("html",)),
)


# Словарь перевода кодов для людей: в отчёте руководителя нет approve_to_reject и VALUE_CHANGED.
# Один на весь отчёт; в шаблоне используется как фильтр `ru`. Неизвестный код выводим как есть.
LABELS = {
    "approve_to_reject": "Одобрение → отказ",
    "reject_to_approve": "Отказ → одобрение",
    "VALUE_CHANGED": "Значение изменилось",
    "ATTRIBUTE_NEW": "Атрибут появился",
    "ATTRIBUTE_LOST": "Атрибут пропал",
    "same": "Без изменений",
    "decision_other": "Другое изменение",
    "approve": "Одобрение",
    "reject": "Отказ",
    "other": "Другое",
}
templates.filters["ru"] = lambda code: LABELS.get(code, code)


def headline(summary: dict) -> str:
    """Итоговая фраза наверху отчёта. Все числа берём из summary, ничего не считаем сами."""
    changed = summary["decision_changed"]
    if not changed:
        text = "Решение не сменила ни одна заявка"
    else:
        moves = summary["decision_changes"]
        sources = summary.get("change_sources", {})
        text = (f"Решение сменили {changed} заявок: {moves['approve_to_reject']} потеряли одобрение, "
                f"{moves['reject_to_approve']} получили; логика {sources.get('logic', 0)} / данные {sources.get('data', 0)}")
        if sources.get("both"):
            text += f" / вместе {sources['both']}"
    if "checks_fail" in summary:  # поля нет у запусков без этапа checks
        text += f"; проверки: {summary['checks_fail']} FAIL"
    return text


def render(run: dict, run_dir: Path, app_url: str) -> str:
    summary = json.loads(results.summary(run_dir))
    top_apps = results.apps(
        run_dir, decision_change="", has_attr_change=False, search="",
        sort="-attributes_changed", page=1, size=20,
    )["apps"]
    # FAIL выше PASS; запуски без этапа checks (старые) — просто без таблицы
    try:
        table = results.checks(run_dir, result="", page=1, size=None, include_refs=False)
        checks = sorted(table["rows"], key=lambda r: r["result"] != "FAIL")
        checks_total = table["total"]
    except ApiError:
        checks, checks_total = [], 0
    # метки срезов берём из манифеста: у загруженных датасетов они свои, не MASTER/BETA
    dataset = datasets.get_dataset(run["dataset"])
    sources = dataset["sources"] if dataset else None
    changed_share = f"{summary['applications_changed_share'] * 100:.1f}".replace(".", ",")

    return templates.get_template("report.html").render(
        run=run,
        summary=summary,
        headline=headline(summary),
        top_apps=top_apps,
        checks=checks,
        checks_total=checks_total,
        attributes_changed=sum(summary["attributes"].values()),
        changed_share=changed_share,
        app_url=app_url,
        sources=sources,
        ai=ai_review.peek(run_dir),  # только кэш: отчёт не ждёт модель
    )
