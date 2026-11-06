from fastapi import APIRouter

from app.services import datasets

router = APIRouter()


@router.get("/datasets")
def get_datasets():
    return {"datasets": datasets.list_datasets()}
