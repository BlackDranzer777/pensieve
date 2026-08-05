"""A single, consistent error shape for the whole API.

Every failure — expected or not — reaches the client as the same JSON object,
so the frontend needs exactly one error parser:

    {
      "error": {
        "code": "not_found",
        "message": "Review 'abc' was not found.",
        "details": {...}      // optional, omitted when empty
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pipelines.common.logging import get_logger

log = get_logger(__name__)


class ApiError(Exception):
    """Base class for errors this API raises deliberately.

    Carrying the status code on the exception keeps route handlers free of
    HTTP plumbing: they raise a domain error and the handler maps it.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationFailedError(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_failed"


class UnsupportedFormatError(ApiError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_format"


class ServiceUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content={"error": payload})


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that normalise every error into the shape above."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default 422 body has a different shape; normalise it so the
        # frontend never has to special-case validation errors.
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            "Request parameters failed validation.",
            {"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback, but never leak internals to the client.
        # `exc_info=exc` is passed explicitly because this runs in a handler
        # callback rather than inside an `except` block, where the ambient
        # exception context is not available.
        log.error(
            "unhandled_exception",
            exc_info=exc,
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred. The incident has been logged.",
        )
