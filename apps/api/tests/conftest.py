"""Shared fixtures for API tests.

These tests deliberately run without a database: the API must degrade cleanly
when Postgres is unavailable, and that behaviour is worth asserting directly.
Endpoints that genuinely need data get database-backed fixtures later, marked
with the `integration` marker.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_api_settings
from app.database.session import get_db_session, get_engine, get_session_factory
from app.main import create_app
from app.models import Base
from tests.seed import seed_database

# Settings are read lazily (through cached factories that the fixture below
# clears), so setting these at import time is early enough — no import-order
# gymnastics required.
#
# The short connect timeout keeps the failed-connection path fast: without it
# every health check would wait the full production timeout before reporting
# the database as down.
os.environ.setdefault("DB_CONNECT_TIMEOUT", "1")
os.environ.setdefault("API_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session", autouse=True)
def _reset_cached_singletons() -> Iterator[None]:
    """Drop cached settings and engine so the env vars above take effect."""
    for cached in (get_api_settings, get_engine, get_session_factory):
        cached.cache_clear()
    yield
    for cached in (get_api_settings, get_engine, get_session_factory):
        cached.cache_clear()


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Test client that surfaces server errors as real HTTP responses.

    `raise_server_exceptions=False` means an unhandled exception produces an
    actual 500 response, so the global error-shape contract can be asserted
    instead of the exception escaping into the test runner.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Database-backed fixtures
# ---------------------------------------------------------------------------
# SQLite in memory rather than a real PostgreSQL. The whole schema builds on
# SQLite (the PostgreSQL-only index options are dialect kwargs SQLAlchemy skips
# elsewhere), so these run in CI with no service container and no network.
#
# What this cannot cover: the trigram index, the partial index and the COPY
# bulk path are PostgreSQL-specific. Those are exercised against real
# PostgreSQL by the loader tests, which skip when it is unavailable.


@pytest.fixture
def seeded_session() -> Iterator[Session]:
    """A session against a fully-populated in-memory database."""
    engine = create_engine(
        "sqlite://",
        # One shared connection, so `:memory:` is the same database for the
        # fixture and the request handler. The default pool would give the app
        # a second, empty database and every assertion would see zero rows.
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        seed_database(session)
        session.commit()
        yield session

    Base.metadata.drop_all(engine)


@pytest.fixture
def seeded_client(app: FastAPI, seeded_session: Session) -> Iterator[TestClient]:
    """Client whose requests read the seeded database."""

    def _override() -> Iterator[Session]:
        yield seeded_session

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
