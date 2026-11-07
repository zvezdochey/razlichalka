import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings
from app.errors import register_error_handlers
from app.routers import configs, datasets, health, procedures, report, results, runs
from app.services import runs as runs_service

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Различалка")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    if not any(settings.CHECKS_DIR.glob("check_*.py")):
        log.warning("В %s нет check_*.py: встроенные проверки будут отвечать 404. Проверь CHECKS_PATH в .env", settings.CHECKS_DIR)
    runs_service.recover()  # недоделанные запуски после перезапуска -> error
    app.include_router(health.router, prefix="/api")
    app.include_router(datasets.router, prefix="/api")
    app.include_router(configs.router, prefix="/api")
    app.include_router(procedures.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    app.include_router(report.router, prefix="/api")
    return app


app = create_app()
