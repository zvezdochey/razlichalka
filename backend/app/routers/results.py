"""Итоги, список заявок и атрибуты (docs/api.md п. 7.1, 7.4 и 8.1)."""
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.deps import current_user
from app.services import facts, results, runs

router = APIRouter(prefix="/runs/{run_id}")

Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=500)]


def _ready_dir(run_id: str, user: str = Depends(current_user)) -> Path:
    return runs.ready_dir(run_id, user)


RunDir = Annotated[Path, Depends(_ready_dir)]


@router.get("/summary")
def get_summary(run_dir: RunDir):
    return Response(content=results.summary(run_dir), media_type="application/json")


@router.get("/apps")
def get_apps(
    run_dir: RunDir, decision_change: str = "", has_attr_change: bool = False,
    search: str = "", sort: str = "", page: Page = 1, size: Size = 50,
):
    return results.apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change,
        search=search, sort=sort, page=page, size=size,
    )


@router.get("/apps/{app_id}/attributes")
def get_attributes(
    run_dir: RunDir, app_id: str, only_diff: bool = False, search: str = "",
    page: Page = 1, size: Size = 100,
):
    return results.attributes(run_dir, app_id, only_diff=only_diff, search=search, page=page, size=size)


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
    search: str = "", sort: str = "",
):
    content = results.export_apps(
        run_dir, decision_change=decision_change, has_attr_change=has_attr_change, search=search, sort=sort,
    )
    filename = f"apps-{quote(run_id, safe='')}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"},
    )
