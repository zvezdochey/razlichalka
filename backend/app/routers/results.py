"""Итоги, список заявок и атрибуты (docs/api.md п. 7.1, 7.4 и 8.1)."""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.deps import current_user
from app.services import results, runs

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


@router.get("/checks")
def get_checks(run_dir: RunDir, result: str = "", page: Page = 1, size: Size = 50):
    return results.checks(run_dir, result=result, page=page, size=size)
