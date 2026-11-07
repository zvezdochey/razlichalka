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
from app.services.labels import LABELS  # noqa: E402
templates.filters["ru"] = lambda code: LABELS.get(code, code)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """1 заявка, 2 заявки, 5 заявок."""
    if n % 100 in range(11, 15):
        return many
    return one if n % 10 == 1 else few if n % 10 in (2, 3, 4) else many


def headline(summary: dict) -> str:
    """Итоговая фраза наверху отчёта. Все числа берём из summary, ничего не считаем сами."""
    changed = summary.get("decision_changed", 0)
    if not changed:
        text = "Решение не сменила ни одна заявка"
    else:
        moves = summary.get("decision_changes", {})
        sources = summary.get("change_sources", {})
        word = _plural(changed, "заявка", "заявки", "заявок")
        verb = "сменила" if changed % 10 == 1 and changed % 100 != 11 else "сменили"
        text = (f"Решение {verb} {changed} {word}: {moves.get('approve_to_reject', 0)} потеряли одобрение, "
                f"{moves.get('reject_to_approve', 0)} получили")
        if moves.get("decision_other"):
            text += f", у {moves['decision_other']} другое решение"
        text += f"; логика {sources.get('logic', 0)} / данные {sources.get('data', 0)}"
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
