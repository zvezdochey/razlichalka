"""Конфигурации пользователя (docs/api.md п. 4). Чужие конфигурации не видны."""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app import store
from app.deps import current_user
from app.errors import ApiError
from app.services import datasets, procedures
from pipeline.buckets import make_adjuster

router = APIRouter()
KIND = "configs"
ARRAY_MODES = {"key", "value", "index"}


class ConfigIn(BaseModel):
    name: str
    dataset: str
    normalize: str = "builtin_normalize"
    compare: str = "builtin_compare"
    aggregate: str = "builtin_aggregate"
    checks: List[str] = []
    ignore_paths: Optional[List[str]] = None  # не задано — технические поля датасета
    array_modes: Dict[str, str] = {}
    array_rules: Dict[str, dict] = {}  # правило массива целиком: {"mode": "key", "key": [...]}
    buckets: Dict[str, List[float]] = {}


def _validate(body: ConfigIn, user: str) -> dict:
    """Проверяет тело и возвращает поля конфигурации с подставленными умолчаниями."""
    if not body.name.strip():
        raise ApiError("bad_code", "Название конфигурации не может быть пустым")
    ds = datasets.get_dataset(body.dataset)
    if ds is None:
        raise ApiError("not_found", f"Датасет «{body.dataset}» не найден")
    for stage in ("normalize", "compare", "aggregate"):
        # процедура этапа должна быть своего вида: иначе этап исполнит не то, что выбрано
        proc_id = getattr(body, stage)
        if procedures.find(proc_id, user)["kind"] != stage:
            raise ApiError("bad_code", f"Процедура «{proc_id}» не подходит для этапа {stage} (нужен kind={stage})")
    for proc_id in body.checks:
        # нет такой процедуры (или она чужая) — not_found; не проверка — bad_code
        if procedures.find(proc_id, user)["kind"] != "check":
            raise ApiError("bad_code", f"Процедура «{proc_id}» не проверка (kind=check)")
    for path, mode in body.array_modes.items():
        if mode not in ARRAY_MODES:
            raise ApiError("bad_code", f"array_modes[{path}]: режим «{mode}» не подходит, нужен key, value или index")
    for path, rule in body.array_rules.items():
        mode, key = rule.get("mode"), rule.get("key")
        if not isinstance(mode, str) or mode not in ARRAY_MODES:
            raise ApiError("bad_code", f"array_rules[{path}]: режим «{mode}» не подходит, нужен key, value или index")
        if key is not None and not (isinstance(key, list) and all(isinstance(k, str) and k for k in key)):
            raise ApiError("bad_code", f"array_rules[{path}]: key — список имён полей")
        if mode == "key" and not key:
            raise ApiError("bad_code", f"array_rules[{path}]: для режима key нужен key — список полей")
    try:
        # та же проверка, что сделает этап «Приведение ответов», — ошибка видна сразу, а не в запуске
        make_adjuster(body.buckets)
    except ValueError as exc:
        raise ApiError("bad_code", str(exc)) from None
    fields = body.model_dump()
    if body.ignore_paths is None:
        fields["ignore_paths"] = ds["technical_fields"]
    return fields


def own_config(config_id: str, user: str) -> dict:
    """Конфигурация пользователя; чужая или несуществующая — not_found (её же берёт POST /runs)."""
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
    mine.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return {"configs": [{k: c.get(k) for k in ("id", "name", "dataset", "updated_at")} for c in mine]}


@router.post("/configs", status_code=201)
def create_config(body: ConfigIn, user: str = Depends(current_user)):
    obj = {"id": "cfg_" + uuid.uuid4().hex[:8], "owner": user, **_validate(body, user), "updated_at": _now()}
    store.save(KIND, obj["id"], obj)
    return _public(obj)


@router.get("/configs/{config_id}")
def get_config(config_id: str, user: str = Depends(current_user)):
    return _public(own_config(config_id, user))


@router.put("/configs/{config_id}")
def update_config(config_id: str, body: ConfigIn, user: str = Depends(current_user)):
    old = own_config(config_id, user)
    obj = {"id": old["id"], "owner": user, **_validate(body, user), "updated_at": _now()}
    store.save(KIND, obj["id"], obj)
    return _public(obj)


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(config_id: str, user: str = Depends(current_user)):
    own_config(config_id, user)
    store.delete(KIND, config_id)
    return Response(status_code=204)
