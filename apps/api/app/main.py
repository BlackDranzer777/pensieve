"""FastAPI application factory and ASGI entry point.

Run with:  uvicorn app.main:app --reload
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import API_V1_PREFIX, __version__
from app.api.routes import api_router
from app.core.config import get_api_settings
from app.core.errors import register_exception_handlers
from pipelines.common.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup and log a clean shutdown."""
    settings = get_api_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    log.info(
        "api_startup",
        version=__version__,
        environment=settings.api_env,
    )
    yield
    log.info("api_shutdown")


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton so tests can construct an
    isolated instance with overridden dependencies.
    """
    settings = get_api_settings()

    app = FastAPI(
        title="Pensieve API",
        description=(
            "Consumer intelligence and data analytics platform. Serves review "
            "analytics, sentiment and topic trends, statistical anomalies, data "
            "quality results and pipeline telemetry."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Emit one structured line per request, with server-side duration."""
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=API_V1_PREFIX)

    return app


app = create_app()
