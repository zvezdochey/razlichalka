from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile  # form.getlist отдаёт класс Starlette (у FastAPI он наследник)

from app.errors import ApiError
from app.services import datasets, uploads
from pipeline.ingest import MAX_FILE

router = APIRouter()

MAX_UPLOAD = 100 * 1024 * 1024  # один присланный файл; архив может быть больше обычного файла заявки
MAX_TOTAL = 150 * 1024 * 1024   # все присланные файлы за запрос: разобранные заявки в памяти тяжелее в разы
MAX_PARTS = 100_000             # файлов в запросе. Starlette по умолчанию пускает только 1000, а в датасете их 2002 на срез


@router.get("/datasets")
def get_datasets():
    return {"datasets": datasets.list_datasets()}


async def _files(form, field: str, budget: list[int]) -> list[tuple[str, bytes]]:
    items = form.getlist(field)
    if not items:
        raise ApiError("bad_request", f"Неверный запрос — {field}: нужен хотя бы один файл")
    result = []
    for f in items:
        if not isinstance(f, UploadFile):
            raise ApiError("bad_request", f"Неверный запрос — {field}: ожидался файл, а пришёл текст")
        name = f.filename or ""
        data = await f.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise ApiError("bad_request", f"Файл {name} больше {MAX_UPLOAD // 1024 // 1024} МБ")
        if not name.lower().endswith(".zip") and len(data) > MAX_FILE:
            raise ApiError("bad_request", f"Файл {name} больше {MAX_FILE // 1024 // 1024} МБ")
        budget[0] -= len(data)
        if budget[0] < 0:
            raise ApiError("bad_request", f"Всего за один запрос можно прислать до {MAX_TOTAL // 1024 // 1024} МБ")
        result.append((name, data))
    return result


@router.post("/datasets/upload", status_code=201)
async def upload_dataset(request: Request):
    """Поля формы — в docs/api.md п. 2.2. Форму читаем сами, чтобы поднять лимит на число файлов."""
    try:
        form = await request.form(max_files=MAX_PARTS, max_fields=MAX_PARTS)
    except Exception:  # битый multipart, слишком много частей
        raise ApiError("bad_request", "Неверный запрос — тело не разобрать как multipart/form-data") from None
    budget = [MAX_TOTAL]
    before, after = await _files(form, "before", budget), await _files(form, "after", budget)
    # Разбор и запись — обычный блокирующий код: отдаём потоку, чтобы остальные ручки не замерзли
    return await run_in_threadpool(
        uploads.create_dataset, before, after,
        form.get("before_label") or None, form.get("after_label") or None, form.getlist("technical_fields"),
    )
