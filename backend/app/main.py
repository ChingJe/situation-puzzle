from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import AppError, app_error_handler
from app.health import get_health
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware
from app.routes import games_router, history_router


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    fastapi_app = FastAPI(title="Situation Puzzle API")

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    fastapi_app.add_middleware(RequestLoggingMiddleware)

    fastapi_app.add_exception_handler(AppError, app_error_handler)
    fastapi_app.include_router(games_router)
    fastapi_app.include_router(history_router)

    @fastapi_app.get("/api/health")
    def health_check() -> dict[str, object]:
        return get_health().model_dump(mode="json")

    return fastapi_app


app = create_app()
