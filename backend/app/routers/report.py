"""Просмотр и скачивание HTML-отчёта (docs/api.md п. 11)."""
import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.deps import current_user
from app.errors import ApiError
from app.services import report, runs

router = APIRouter(prefix="/runs/{run_id}")
HOST = re.compile(r"(?:[a-zA-Z0-9.-]+|\[[a-fA-F0-9:.]+\])(?::[0-9]{1,5})?")


def _app_url(request: Request, run_id: str) -> str:
    # Берём первый адрес в заголовках прокси. В ссылке допустим только HTTP(S).
    forwarded_scheme = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    scheme = forwarded_scheme if forwarded_scheme in ("http", "https") else request.url.scheme
    if scheme not in ("http", "https"):
        scheme = "http"

    forwarded_host = request.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
    host = forwarded_host if HOST.fullmatch(forwarded_host) else request.headers.get("Host", "")
    if not HOST.fullmatch(host):
        raise ApiError("bad_file", "Некорректный адрес приложения")

    return f"{scheme}://{host}/runs/{quote(run_id, safe='')}"


@router.get("/report", response_class=HTMLResponse)
@router.get("/report.html", response_class=HTMLResponse)
def get_report(run_id: str, request: Request, user: Annotated[str, Depends(current_user)]):
    run_dir = runs.ready_dir(run_id, user)
    run = runs.get_own(run_id, user)
    html = report.render(run, run_dir, _app_url(request, run_id))

    headers = {"Cache-Control": "private, no-store"}
    if request.url.path.endswith("/report.html"):
        headers["Content-Disposition"] = f'attachment; filename="report-{quote(run_id, safe="")}.html"'
    return HTMLResponse(html, headers=headers)
