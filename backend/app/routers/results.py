"""Итоги, список заявок и атрибуты (docs/api.md п. 7.1, 7.4 и 8.1)."""
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.deps import current_user
from app.services import ai_review, app_card, facts, reasons, results, runs

router = APIRouter(prefix="/runs/{run_id}")

Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=500)]


def _ready_dir(run_id: str, user: str = Depends(current_user)) -> Path:
    return runs.ready_dir(run_id, user)


RunDir = Annotated[Path, Depends(_ready_dir)]


def _dataset_path(run_id: str, user: str = Depends(current_user)) -> Path:
    return runs.dataset_path(runs.get_own(run_id, user))


RunDataset = Annotated[Path, Depends(_dataset_path)]


@router.get("/summary")
def get_summary(run_dir: RunDir):
    return Response(content=results.summary(run_dir), media_type="application/json")


@router.get("/apps")
def get_apps(
    run_dir: RunDir, decision_change: str = "", has_attr_change: bool = False,
    search: str = "", sort: str = "", page: Page = 1, size: Size = 50, change_source: str = "", ref: str = "",
):
    # ref — группа из сводной или проверки: список заявок сужается до неё
    return results.apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change,
        search=search, sort=sort, page=page, size=size, change_source=change_source,
        app_ids=set(facts.group_app_ids(run_dir, ref)) if ref else None,
    )


@router.get("/apps/{app_id}")
def get_app_card(run_dir: RunDir, dataset_dir: RunDataset, app_id: str):
    return app_card.app_card(run_dir, dataset_dir, app_id)


@router.get("/reasons")
def get_reasons(run_dir: RunDir, dataset_dir: RunDataset):
    return reasons.reasons(run_dir, dataset_dir)


@router.get("/ai-review")
def get_ai_review(run_dir: RunDir, dataset_dir: RunDataset):
    return ai_review.get(run_dir, dataset_dir)


@router.get("/apps/{app_id}/attributes")
def get_attributes(
    run_dir: RunDir, app_id: str, only_diff: bool = False, search: str = "",
    page: Page = 1, size: Size = 100,
):
    return results.attributes(run_dir, app_id, only_diff=only_diff, search=search, page=page, size=size)


@router.get("/checks")
def get_checks(run_dir: RunDir, result: str = "", page: Page = 1, size: Size = 50):
    return results.checks(run_dir, result=result, page=page, size=size)


@router.get("/facts")
def get_facts(
    run_dir: RunDir, dims: str, filter_: Annotated[str, Query(alias="filter")] = "",
    measure: str = "counts", limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
):
    return facts.facts(run_dir, dims=dims, filter_=filter_, measure=measure, limit=limit)


@router.get("/facts/{ref}/apps")
def get_fact_apps(run_dir: RunDir, ref: str, page: Page = 1, size: Size = 50):
    return facts.fact_apps(run_dir, ref, page=page, size=size)


@router.get("/export.csv")
def export_apps(
    run_dir: RunDir, run_id: str, decision_change: str = "", has_attr_change: bool = False,
    search: str = "", sort: str = "", change_source: str = "", ref: str = "",
):
    content = results.export_apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change, search=search, sort=sort,
        change_source=change_source, app_ids=set(facts.group_app_ids(run_dir, ref)) if ref else None,
    )
    filename = f"apps-{quote(run_id, safe='')}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"},
    )
