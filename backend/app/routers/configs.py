"""Конфигурации пользователя (docs/api.md п. 4). Чужие конфигурации не видны."""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app import store
from app.deps import current_user
from app.errors import ApiError
from app.services import datasets

router = APIRouter()
KIND = "configs"
ARRAY_MODES = {"key", "value", "index"}


class ConfigIn(BaseModel):
    name: str
    dataset: str
    normalize: str = "builtin_normalize"
    aggregate: str = "builtin_aggregate"
    checks: List[str] = []
    ignore_paths: Optional[List[str]] = None  # не задано — технические поля датасета
    array_modes: Dict[str, str] = {}
    buckets: Dict[str, List[float]] = {}


def _validate(body: ConfigIn) -> dict:
    """Проверяет тело и возвращает поля конфигурации с подставленными умолчаниями."""
    if not body.name.strip():
        raise ApiError("bad_code", "Название конфигурации не может быть пустым")
    ds = datasets.get_dataset(body.dataset)
    if ds is None:
        raise ApiError("not_found", f"Датасет «{body.dataset}» не найден")
    for path, mode in body.array_modes.items():
        if mode not in ARRAY_MODES:
            raise ApiError("bad_code", f"array_modes[{path}]: режим «{mode}» не подходит, нужен key, value или index")
    for path, bounds in body.buckets.items():
        if any(a >= b for a, b in zip(bounds, bounds[1:])):
            raise ApiError("bad_code", f"buckets[{path}]: границы должны идти по возрастанию")
    fields = body.model_dump()
    if body.ignore_paths is None:
        fields["ignore_paths"] = ds["technical_fields"]
    return fields


def _own(config_id: str, user: str) -> dict:
    obj = store.load(KIND, config_id)
    if obj is None or obj.get("owner") != user:
        raise ApiError("not_found", "Конфигурация не найдена")
    return obj


def _public(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k != "owner"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/configs")
def list_configs(user: str = Depends(current_user)):
    mine = [c for c in store.list(KIND) if c.get("owner") == user]
    mine.sort(key=lambda c: c["updated_at"], reverse=True)
    return {"configs": [{k: c[k] for k in ("id", "name", "dataset", "updated_at")} for c in mine]}


@router.post("/configs", status_code=201)
def create_config(body: ConfigIn, user: str = Depends(current_user)):
    obj = {"id": "cfg_" + uuid.uuid4().hex[:8], "owner": user, **_validate(body), "updated_at": _now()}
    store.save(KIND, obj["id"], obj)
    return _public(obj)


@router.get("/configs/{config_id}")
def get_config(config_id: str, user: str = Depends(current_user)):
    return _public(_own(config_id, user))


@router.put("/configs/{config_id}")
def update_config(config_id: str, body: ConfigIn, user: str = Depends(current_user)):
    old = _own(config_id, user)
    obj = {"id": old["id"], "owner": user, **_validate(body), "updated_at": _now()}
    store.save(KIND, obj["id"], obj)
    return _public(obj)


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(config_id: str, user: str = Depends(current_user)):
    _own(config_id, user)
    store.delete(KIND, config_id)
    return Response(status_code=204)
