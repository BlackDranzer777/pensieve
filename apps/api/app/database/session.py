"""Database engine and session management."""

from __future__ import annotations

import functools
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_api_settings
from pipelines.common.logging import get_logger

log = get_logger(__name__)


@functools.lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the process-wide SQLAlchemy engine.

    `pool_pre_ping` costs one cheap round trip per checkout and in exchange
    removes the "stale connection after the database restarted" class of
    errors entirely — a good trade for a dashboard backend.
    """
    settings = get_api_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=settings.db_connect_timeout,
        connect_args={"connect_timeout": settings.db_connect_timeout},
        echo=False,
    )


@functools.lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_connection() -> tuple[bool, str | None]:
    """Return `(is_reachable, error_message)` without raising.

    Used by the health endpoint, which must report a database outage rather
    than crash because of one.
    """
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health checks report, never raise
        log.warning("database_unreachable", error=str(exc), error_type=type(exc).__name__)
        return False, f"{type(exc).__name__}: {exc}"
    return True, None
