"""Единый формат ошибок из docs/api.md: {"error": {"code": "...", "message": "..."}}."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("razlichalka")

# code -> HTTP-статус (таблица «Ошибки» в docs/api.md)
HTTP_BY_CODE = {
    "bad_file": 400,
    "bad_request": 400,
    "bad_code": 400,
    "no_id_column": 400,
    "not_found": 404,
    "not_ready": 409,
    "conflict": 409,
    "internal": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = HTTP_BY_CODE.get(code, 500)


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError):
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        # FastAPI по умолчанию отдаёт 422, а у нас в договоре 400 bad_request
        parts = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"])
            parts.append(f"{field}: {err['msg']}")
        return error_response("bad_request", "Неверный запрос — " + "; ".join(parts), 400)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response("not_found", "Такой ручки или объекта нет", 404)
        if exc.status_code == 405:
            return error_response("internal", "Этот метод для ручки не поддерживается", 405)
        return error_response("internal", "Ошибка запроса", exc.status_code)

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, exc: Exception):
        # pipeline.errors.PipelineError (code, message) превращаем в ApiError с тем же code
        code = getattr(exc, "code", None)
        if type(exc).__module__.startswith("pipeline") and code in HTTP_BY_CODE:
            return error_response(code, getattr(exc, "message", str(exc)), HTTP_BY_CODE[code])
        log.exception("Необработанная ошибка в %s %s", request.method, request.url.path)
        return error_response("internal", "Внутренняя ошибка сервера", 500)
