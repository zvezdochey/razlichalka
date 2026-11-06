"""Самодостаточный HTML-отчёт по сохранённым результатам запуска."""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services import results

templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(("html",)),
)


def render(run: dict, run_dir: Path, app_url: str) -> str:
    summary = json.loads(results.summary(run_dir))
    top_apps = results.apps(
        run_dir, decision_change="", has_attr_change=False, search="",
        sort="-attributes_changed", page=1, size=20,
    )["apps"]
    changed_share = f"{summary['applications_changed_share'] * 100:.1f}".replace(".", ",")

    return templates.get_template("report.html").render(
        run=run,
        summary=summary,
        top_apps=top_apps,
        attributes_changed=sum(summary["attributes"].values()),
        changed_share=changed_share,
        app_url=app_url,
    )
