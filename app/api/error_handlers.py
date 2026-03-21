"""HTTP error handlers shared across the API."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import CaseFlowError
from app.core.request_context import get_request_id


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CaseFlowError)
    async def handle_caseflow_error(
        request: Request, exc: CaseFlowError
    ) -> JSONResponse:  # pragma: no cover - exercised through integration tests
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:  # pragma: no cover - exercised through integration tests
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "request_id": request.state.request_id,
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:  # pragma: no cover - exercised through integration tests
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": detail.lower().replace(" ", "_"),
                    "message": detail,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:  # pragma: no cover - exercised through integration tests
        request.app.state.logger.exception(
            "request_unhandled_error",
            error_type=exc.__class__.__name__,
            request_id=get_request_id(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error.",
                    "request_id": request.state.request_id,
                }
            },
        )
