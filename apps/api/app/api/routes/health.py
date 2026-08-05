"""Health endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app import __version__
from app.core.config import get_api_settings
from app.database.session import check_database_connection
from app.schemas.common import HealthCheck, HealthResponse
from pipelines.common.domain import PROCESSING_VERSION

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service and dependency health",
)
def health() -> HealthResponse:
    """Report liveness plus the status of each dependency.

    Always 200 while the process is up. Inspect `checks` to distinguish a
    healthy service from one whose database is unreachable.
    """
    db_ok, db_error = check_database_connection()

    checks = [
        HealthCheck(
            name="database",
            status="ok" if db_ok else "unavailable",
            detail=db_error,
        )
    ]

    settings = get_api_settings()
    return HealthResponse(
        status="ok" if all(c.status == "ok" for c in checks) else "degraded",
        version=__version__,
        environment=settings.api_env,
        processing_version=PROCESSING_VERSION,
        timestamp=datetime.now(UTC),
        checks=checks,
    )
