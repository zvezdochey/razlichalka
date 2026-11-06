from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings
from app.errors import register_error_handlers
from app.routers import configs, datasets, health, results, runs
from app.services import runs as runs_service


def create_app() -> FastAPI:
    app = FastAPI(title="Различалка")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    runs_service.recover()  # недоделанные запуски после перезапуска -> error
    app.include_router(health.router, prefix="/api")
    app.include_router(datasets.router, prefix="/api")
    app.include_router(configs.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    return app


app = create_app()
