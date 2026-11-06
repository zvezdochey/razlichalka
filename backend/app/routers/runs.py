"""Запуски и журнал этапов (docs/api.md п. 5–6). Чужие запуски не видны."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import current_user
from app.errors import ApiError
from app.routers.configs import own_config
from app.services import runs

router = APIRouter()


class RunIn(BaseModel):
    config_id: str


def _status(run: dict) -> dict:
    return {k: run[k] for k in (
        "id", "status", "config_id", "dataset", "created_at", "finished_at",
        "progress", "current_stage", "error",
    )}


def _stage(run: dict, name: str) -> dict:
    for st in run["stages"]:
        if st["name"] == name:
            return st
    raise ApiError("not_found", f"Этапа «{name}» нет")


@router.post("/runs", status_code=202)
def start_run(body: RunIn, user: str = Depends(current_user)):
    run = runs.create(own_config(body.config_id, user), user)
    return {"id": run["id"], "status": "pending", "config_id": run["config_id"]}


@router.get("/runs")
def list_runs(user: str = Depends(current_user)):
    return {"runs": [
        {k: r[k] for k in ("id", "status", "config_id", "created_at")} for r in runs.list_own(user)
    ]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: str = Depends(current_user)):
    return _status(runs.snapshot(runs.get_own(run_id, user)))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, user: str = Depends(current_user)):
    run = runs.snapshot(runs.cancel(run_id, user))
    return {"id": run["id"], "status": run["status"], "error": run["error"]}


@router.get("/runs/{run_id}/stages")
def get_stages(run_id: str, user: str = Depends(current_user)):
    run = runs.snapshot(runs.get_own(run_id, user))
    stages = []
    for st in run["stages"]:
        st = {k: v for k, v in st.items() if k != "error"}
        st["log"] = st["log"][-runs.LOG_TAIL:]
        stages.append(st)
    return {"stages": stages}


@router.get("/runs/{run_id}/stages/{name}/log")
def get_stage_log(run_id: str, name: str, after: int = 0, user: str = Depends(current_user)):
    run = runs.snapshot(runs.get_own(run_id, user))
    log = _stage(run, name)["log"]
    after = max(after, 0)
    return {"entries": log[after:], "next": max(len(log), after)}
