"""Application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.middleware import register_http_middleware
from app.api.v1.router import api_router
from app.api.v1.routes.ops import router as ops_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    logger = configure_logging(debug=settings.debug)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.logger = logger

    register_http_middleware(app)
    register_exception_handlers(app)
    app.include_router(ops_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
