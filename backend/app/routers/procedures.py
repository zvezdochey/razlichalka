"""Процедуры и проверки (docs/api.md п. 3). Свои процедуры видны только владельцу, встроенные — всем."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.deps import current_user
from app.services import procedures

MAX_CODE = 200_000  # знаков; больше для проверки не нужно

router = APIRouter()


class ProcedureIn(BaseModel):
    kind: Literal["normalize", "aggregate", "check"]
    name: str
    source: Literal["inline", "file"]
    code: Optional[str] = Field(None, max_length=MAX_CODE)
    path: Optional[str] = None


class ValidateIn(BaseModel):
    kind: str
    source: str = "inline"
    code: Optional[str] = Field(None, max_length=MAX_CODE)
    path: Optional[str] = None


@router.get("/procedures")
def list_procedures(kind: Optional[str] = None, user: str = Depends(current_user)):
    return {"procedures": procedures.list_all(kind, user)}


# /validate объявлена раньше /{id}, чтобы «validate» не приняли за id
@router.post("/procedures/validate")
def validate_procedure(body: ValidateIn):
    errors = procedures.validate(body.kind, body.source, body.code, body.path)
    return {"ok": not errors, "errors": errors}


@router.post("/procedures", status_code=201)
def create_procedure(body: ProcedureIn, user: str = Depends(current_user)):
    return procedures.create(body.model_dump(), user)


@router.get("/procedures/{proc_id}")
def get_procedure(proc_id: str, user: str = Depends(current_user)):
    return procedures.with_code(procedures.find(proc_id, user))


@router.put("/procedures/{proc_id}")
def update_procedure(proc_id: str, body: ProcedureIn, user: str = Depends(current_user)):
    return procedures.update(proc_id, body.model_dump(), user)


@router.delete("/procedures/{proc_id}", status_code=204)
def delete_procedure(proc_id: str, user: str = Depends(current_user)):
    procedures.delete(proc_id, user)
    return Response(status_code=204)
